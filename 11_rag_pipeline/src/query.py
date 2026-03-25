"""
RAG Pipeline — Retrieval + Query Engine
Handles: semantic search, reranking, answer generation with citations
"""

import time, logging
from dataclasses import dataclass

from openai import OpenAI
import psycopg2
from pgvector.psycopg2 import register_vector

from ingest import IngestConfig, EmbeddingGenerator

log = logging.getLogger(__name__)


@dataclass
class RetrievalConfig:
    top_k: int = 5                    # candidates from vector search
    rerank_top_n: int = 3             # after reranking, keep top N
    similarity_threshold: float = 0.3 # discard chunks below this cosine score
    use_reranker: bool = False         # cross-encoder reranking (improves precision)
    chat_model: str = "gpt-4o-mini"
    max_context_tokens: int = 3000
    temperature: float = 0.0          # deterministic answers for enterprise use


class Retriever:
    """
    Vector similarity search with optional reranking.

    Reranking tradeoff:
      Without: fast, single-model, good for P50 queries
      With:    adds ~100-200ms, cross-encoder scores full query-chunk pairs
               significantly improves precision for ambiguous queries
              Use when accuracy > latency (e.g. medical, legal, compliance)
    """

    def __init__(self, ingest_config: IngestConfig, retrieval_config: RetrievalConfig = None):
        self.ic = ingest_config
        self.rc = retrieval_config or RetrievalConfig()
        self.conn = psycopg2.connect(ingest_config.db_conn_str)
        register_vector(self.conn)
        self.embedder = EmbeddingGenerator(ingest_config)

    def search(self, query: str, doc_ids: list[str] = None) -> list[dict]:
        """
        Semantic search. Optionally filter to specific documents.
        Returns chunks sorted by cosine similarity (descending).
        """
        t0 = time.time()
        query_embedding = self.embedder.embed_batch([query])[0]

        doc_filter = ""
        params = [query_embedding, self.rc.top_k]
        if doc_ids:
            doc_filter = "AND doc_id = ANY(%s)"
            params.append(doc_ids)

        with self.conn.cursor() as cur:
            cur.execute(f"""
                SELECT
                    chunk_id, doc_id, chunk_index, text, token_count, metadata,
                    1 - (embedding <=> %s::vector) AS similarity
                FROM {self.ic.table_name}
                WHERE 1 - (embedding <=> %s::vector) >= {self.rc.similarity_threshold}
                {doc_filter}
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
            """, [query_embedding, query_embedding] + ([doc_ids] if doc_ids else []) + [self.rc.top_k])

            rows = cur.fetchall()

        results = [{
            "chunk_id": r[0], "doc_id": r[1], "chunk_index": r[2],
            "text": r[3], "token_count": r[4], "metadata": r[5],
            "similarity": round(float(r[6]), 4),
        } for r in rows]

        log.info(f"search hits={len(results)} latency={int((time.time()-t0)*1000)}ms "
                 f"query_cost=${self.embedder.cost_usd:.5f}")
        return results


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
