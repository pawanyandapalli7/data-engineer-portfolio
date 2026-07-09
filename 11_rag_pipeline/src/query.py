"""
RAG Pipeline — Retrieval + Query Engine
Handles: semantic search, reranking, answer generation with citations
"""

import time, logging
from dataclasses import dataclass

from openai import OpenAI
import psycopg2
from pgvector.psycopg2 import register_vector

from ingest import IngestConfig, EmbeddingGenerator, _validate_identifier

log = logging.getLogger(__name__)


@dataclass
class RetrievalConfig:
    top_k: int = 5                    # final chunks returned when reranking is off
    rerank_candidates: int = 20       # candidates pulled from vector search when reranking is on
    rerank_top_n: int = 5             # after reranking, keep top N
    similarity_threshold: float = 0.3 # discard chunks below this cosine score
    use_reranker: bool = False        # lexical (zero-cost) reranking over a wider candidate set
    chat_model: str = "gpt-4o-mini"
    max_context_tokens: int = 3000
    temperature: float = 0.0          # deterministic answers for enterprise use


class Retriever:
    """
    Vector similarity search with optional lexical reranking.

    Reranking tradeoff:
      Without: single-stage top-k vector search. Fast, good for most queries.
      With:    pulls a wider candidate set (rerank_candidates) from vector search,
               then rescoring by lexical term overlap against the query — no extra
               model call, adds negligible latency, improves precision when the
               query has specific terms the embedding alone under-weights.
               Use when accuracy > raw latency (e.g. medical, legal, compliance).
    """

    def __init__(self, ingest_config: IngestConfig, retrieval_config: RetrievalConfig = None):
        self.ic = ingest_config
        _validate_identifier(ingest_config.table_name)
        self.rc = retrieval_config or RetrievalConfig()
        self.conn = psycopg2.connect(ingest_config.db_conn_str)
        register_vector(self.conn)
        self.embedder = EmbeddingGenerator(ingest_config)

    def search(self, query: str, doc_ids: list[str] = None) -> list[dict]:
        """
        Semantic search. Optionally filter to specific documents.

        When rc.use_reranker is False (default): single-stage vector search,
        returns top rc.top_k chunks by cosine similarity.

        When True: pulls rc.rerank_candidates chunks from vector search, then
        rescoring by lexical term overlap against the query, returns the top
        rc.rerank_top_n by that combined ranking.
        """
        t0 = time.time()
        query_embedding = self.embedder.embed_batch([query])[0]
        fetch_n = self.rc.rerank_candidates if self.rc.use_reranker else self.rc.top_k

        doc_filter = ""
        params = [query_embedding, query_embedding, self.rc.similarity_threshold]
        if doc_ids:
            doc_filter = "AND doc_id = ANY(%s)"
            params.append(doc_ids)
        params.extend([query_embedding, fetch_n])

        with self.conn.cursor() as cur:
            cur.execute(f"""
                SELECT
                    chunk_id, doc_id, chunk_index, text, token_count, metadata,
                    1 - (embedding <=> %s::vector) AS similarity
                FROM {self.ic.table_name}
                WHERE 1 - (embedding <=> %s::vector) >= %s
                {doc_filter}
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
            """, params)

            rows = cur.fetchall()

        results = [{
            "chunk_id": r[0], "doc_id": r[1], "chunk_index": r[2],
            "text": r[3], "token_count": r[4], "metadata": r[5],
            "similarity": round(float(r[6]), 4),
        } for r in rows]

        if self.rc.use_reranker and results:
            results = self._lexical_rerank(query, results, self.rc.rerank_top_n)

        log.info(f"search hits={len(results)} latency={int((time.time()-t0)*1000)}ms "
                 f"query_cost=${self.embedder.cost_usd:.5f}")
        return results

    @staticmethod
    def _lexical_rerank(query: str, candidates: list[dict], top_n: int) -> list[dict]:
        """
        Zero-cost lexical reranker: rescore vector-search candidates by term
        overlap with the query, blended with the original cosine similarity.

        This is intentionally simple (no external model call) — it corrects
        cases where the embedding buries a chunk that shares the query's
        specific terms (a code, a name, a section number) under semantically
        similar-but-less-relevant chunks.
        """
        query_terms = Retriever._tokenize(query)
        if not query_terms:
            return candidates[:top_n]

        rescored = []
        for c in candidates:
            chunk_terms = Retriever._tokenize(c["text"])
            overlap = len(query_terms & chunk_terms)
            lexical_score = overlap / len(query_terms)
            # Blend: cosine similarity still dominates, lexical overlap breaks
            # ties and corrects for embedding blind spots on specific terms.
            combined = 0.7 * c["similarity"] + 0.3 * lexical_score
            rescored.append({**c, "lexical_score": round(lexical_score, 4), "combined_score": round(combined, 4)})

        rescored.sort(key=lambda c: c["combined_score"], reverse=True)
        return rescored[:top_n]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split() if len(t) > 2}


class RAGQueryEngine:
    """
    Full RAG pipeline: query -> retrieve -> generate answer with citations.

    System prompt is tuned for:
    - Grounded answers (only what's in context)
    - Citation of source chunks
    - Explicit "I don't know" when context is insufficient
    """

    SYSTEM_PROMPT = """You are a precise, enterprise-grade question-answering assistant.
Answer ONLY based on the provided context chunks. Do not use outside knowledge.
Rules:
1. Always cite which chunk(s) you used: [Chunk 1], [Chunk 2], etc.
2. If the context doesn't contain enough information, say: "The provided documents don't contain enough information to answer this question."
3. Be concise. Prefer bullet points for multi-part answers.
4. Never hallucinate facts not present in the context."""

    def __init__(self, ingest_config: IngestConfig, retrieval_config: RetrievalConfig = None):
        self.retriever = Retriever(ingest_config, retrieval_config)
        self.rc = retrieval_config or RetrievalConfig()
        self.client = OpenAI()

    def query(self, question: str, doc_ids: list[str] = None) -> dict:
        """
        End-to-end RAG query.
        Returns answer, citations, retrieved chunks, and latency metrics.
        """
        t0 = time.time()

        # Retrieve
        chunks = self.retriever.search(question, doc_ids)
        if not chunks:
            return {
                "question": question, "answer": "No relevant documents found.",
                "chunks_retrieved": 0, "citations": [], "latency_ms": int((time.time()-t0)*1000),
            }

        # Build context — enumerate chunks for citation
        context = "\n\n".join(
            f"[Chunk {i+1}] (doc: {c['doc_id']}, similarity: {c['similarity']})\n{c['text']}"
            for i, c in enumerate(chunks)
        )

        # Generate
        t1 = time.time()
        response = self.client.chat.completions.create(
            model=self.rc.chat_model,
            temperature=self.rc.temperature,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
            ],
        )
        gen_latency = int((time.time()-t1)*1000)
        answer = response.choices[0].message.content

        result = {
            "question": question,
            "answer": answer,
            "chunks_retrieved": len(chunks),
            "chunks": chunks,
            "citations": [c["doc_id"] for c in chunks],
            "model": self.rc.chat_model,
            "tokens_used": response.usage.total_tokens,
            "cost_usd": round(response.usage.total_tokens * 15e-6, 6),  # gpt-4o-mini
            "retrieval_latency_ms": int((t1-t0)*1000),
            "generation_latency_ms": gen_latency,
            "total_latency_ms": int((time.time()-t0)*1000),
        }
        log.info(f"query latency={result['total_latency_ms']}ms "
                 f"chunks={len(chunks)} cost=${result['cost_usd']:.5f}")
        return result
