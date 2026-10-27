"""
RAG pipeline: retrieval and answer generation.

question -> embed -> pgvector top-k (optionally widened + lexically reranked)
         -> token-budgeted context -> grounded answer with [Chunk n] citations
"""

import logging
import re
import time
from dataclasses import dataclass, replace
from typing import Optional

import tiktoken
from openai import OpenAI
from pgvector.psycopg2 import register_vector

from ingest import EmbeddingGenerator, IngestConfig, _validate_identifier, make_pool
from pricing import cost_usd

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievalConfig:
    top_k: int = 5  # chunks returned without reranking
    rerank_candidates: int = 20  # candidates pulled when reranking
    rerank_top_n: int = 5  # chunks kept after reranking
    similarity_threshold: float = 0.3  # drop chunks below this cosine similarity
    use_reranker: bool = False
    chat_model: str = "gpt-4o-mini"
    max_context_tokens: int = 3000  # hard budget for retrieved text sent to the model
    temperature: float = 0.0


class Retriever:
    """Vector search with optional lexical reranking over a wider candidate set."""

    def __init__(self, ingest_config: IngestConfig, retrieval_config: Optional[RetrievalConfig] = None, pool=None):
        self.ic = ingest_config
        self.table = _validate_identifier(ingest_config.table_name)
        self.rc = retrieval_config or RetrievalConfig()
        self.pool = pool or make_pool(ingest_config.db_conn_str)
        self.embedder = EmbeddingGenerator(ingest_config)

    def search(self, query: str, doc_ids: Optional[list[str]] = None, top_k: Optional[int] = None) -> list[dict]:
        rc = self.rc if top_k is None else replace(self.rc, top_k=top_k, rerank_top_n=top_k)
        t0 = time.time()
        q = self.embedder.embed_batch([query])[0]
        fetch_n = rc.rerank_candidates if rc.use_reranker else rc.top_k

        doc_filter, params = "", [q, q, rc.similarity_threshold]
        if doc_ids:
            doc_filter = "AND doc_id = ANY(%s)"
            params.append(doc_ids)
        params.extend([q, fetch_n])

        conn = self.pool.getconn()
        try:
            register_vector(conn)
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT chunk_id, doc_id, chunk_index, text, token_count, metadata,
                           1 - (embedding <=> %s::vector) AS similarity
                    FROM {self.table}
                    WHERE 1 - (embedding <=> %s::vector) >= %s {doc_filter}
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s;
                """,
                    params,
                )
                rows = cur.fetchall()
            conn.rollback()  # read-only; end the transaction before returning the connection
        finally:
            self.pool.putconn(conn)

        results = [
            {
                "chunk_id": r[0],
                "doc_id": r[1],
                "chunk_index": r[2],
                "text": r[3],
                "token_count": r[4],
                "metadata": r[5],
                "similarity": round(float(r[6]), 4),
            }
            for r in rows
        ]
        if rc.use_reranker and results:
            results = self._lexical_rerank(query, results, rc.rerank_top_n)
        log.info("search hits=%d %dms", len(results), (time.time() - t0) * 1000)
        return results

    @staticmethod
    def _lexical_rerank(query: str, candidates: list[dict], top_n: int) -> list[dict]:
        """Blend cosine similarity (70%) with query-term overlap (30%). No extra model call."""
        query_terms = Retriever._tokenize(query)
        if not query_terms:
            return candidates[:top_n]
        rescored = []
        for c in candidates:
            lexical = len(query_terms & Retriever._tokenize(c["text"])) / len(query_terms)
            rescored.append(
                {
                    **c,
                    "lexical_score": round(lexical, 4),
                    "combined_score": round(0.7 * c["similarity"] + 0.3 * lexical, 4),
                }
            )
        rescored.sort(key=lambda c: c["combined_score"], reverse=True)
        return rescored[:top_n]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split() if len(t) > 2}


def build_context(chunks: list[dict], max_tokens: int, enc=None) -> tuple[str, list[dict]]:
    """Number chunks for citation and stop before the token budget is exceeded."""
    enc = enc or tiktoken.get_encoding("cl100k_base")
    parts, used, total = [], [], 0
    for c in chunks:
        block = f"[Chunk {len(used) + 1}] (doc: {c['doc_id']})\n{c['text']}"
        n = len(enc.encode(block))
        if used and total + n > max_tokens:
            break
        parts.append(block)
        used.append(c)
        total += n
    return "\n\n".join(parts), used


def cited_chunks(answer: str, chunks: list[dict]) -> list[dict]:
    """The chunks the answer actually cites, in citation order, without duplicates."""
    seen, out = set(), []
    for n in (int(m) for m in re.findall(r"\[Chunk (\d+)\]", answer)):
        if 1 <= n <= len(chunks) and n not in seen:
            seen.add(n)
            out.append(chunks[n - 1])
    return out


class RAGQueryEngine:
    SYSTEM_PROMPT = """You answer questions using only the context chunks provided.
Rules:
1. Cite every chunk you use as [Chunk N].
2. If the context does not contain the answer, reply exactly:
   "The provided documents don't contain enough information to answer this question."
3. Be concise. Use bullet points for multi-part answers.
4. Do not add facts that are not in the context."""

    def __init__(self, ingest_config: IngestConfig, retrieval_config: Optional[RetrievalConfig] = None, pool=None):
        self.rc = retrieval_config or RetrievalConfig()
        self.retriever = Retriever(ingest_config, self.rc, pool)
        self.client = OpenAI(max_retries=5)

    def query(self, question: str, doc_ids: Optional[list[str]] = None, top_k: Optional[int] = None) -> dict:
        t0 = time.time()
        chunks = self.retriever.search(question, doc_ids, top_k)
        if not chunks:
            return {
                "question": question,
                "answer": "No relevant documents found.",
                "chunks_retrieved": 0,
                "citations": [],
                "cost_usd": 0.0,
                "total_latency_ms": int((time.time() - t0) * 1000),
            }

        context, used = build_context(chunks, self.rc.max_context_tokens)
        t1 = time.time()
        response = self.client.chat.completions.create(
            model=self.rc.chat_model,
            temperature=self.rc.temperature,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
            ],
        )
        answer = response.choices[0].message.content
        usage = response.usage
        cited = cited_chunks(answer, used)
        return {
            "question": question,
            "answer": answer,
            "chunks_retrieved": len(chunks),
            "chunks_in_context": len(used),
            "citations": sorted({c["doc_id"] for c in cited}),
            "cited_chunk_ids": [c["chunk_id"] for c in cited],
            "model": self.rc.chat_model,
            "tokens_used": usage.total_tokens,
            "cost_usd": round(cost_usd(self.rc.chat_model, usage.prompt_tokens, usage.completion_tokens), 6),
            "retrieval_latency_ms": int((t1 - t0) * 1000),
            "generation_latency_ms": int((time.time() - t1) * 1000),
            "total_latency_ms": int((time.time() - t0) * 1000),
        }
