"""
RAG pipeline: ingestion layer.

document text -> paragraph-aware chunks -> embeddings -> pgvector (idempotent)
"""

import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import psycopg2
import psycopg2.extras
import psycopg2.pool
import tiktoken
from openai import OpenAI
from pgvector.psycopg2 import register_vector

from pricing import cost_usd

log = logging.getLogger(__name__)

_SAFE_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validate_identifier(name: str) -> str:
    """Table names are interpolated into SQL (psycopg2 can't bind identifiers), so whitelist them."""
    if not _SAFE_IDENTIFIER.match(name):
        raise ValueError(f"Unsafe table name: {name!r}")
    return name


@dataclass
class IngestConfig:
    # Chunking
    chunk_size: int = 512  # max tokens per chunk
    chunk_overlap: int = 64  # tokens carried into the next chunk

    # Embedding. text-embedding-3-* models can return shortened vectors; 1536
    # keeps us under pgvector's 2,000-dimension limit for HNSW/IVFFlat indexes.
    embedding_model: str = field(default_factory=lambda: os.environ.get("EMBEDDING_MODEL", "text-embedding-3-large"))
    embedding_dimensions: int = 1536
    embedding_batch_size: int = 100

    # Vector store
    db_conn_str: str = field(default_factory=lambda: os.environ.get("DATABASE_URL", ""))
    table_name: str = "document_chunks"

    def __post_init__(self):
        if self.embedding_dimensions > 2000:
            raise ValueError("pgvector can't index more than 2,000 dimensions; lower embedding_dimensions")


def make_pool(conn_str: str, maxconn: int = 10) -> psycopg2.pool.ThreadedConnectionPool:
    if not conn_str:
        raise ValueError("DATABASE_URL is not set")
    return psycopg2.pool.ThreadedConnectionPool(1, maxconn, conn_str)


class SemanticChunker:
    """
    Splits on paragraph boundaries (falling back to sentences for long
    paragraphs) and packs them into chunks of at most `chunk_size` tokens, with a
    sentence-aligned overlap carried into the next chunk.
    """

    def __init__(self, config: IngestConfig):
        self.config = config
        self.enc = tiktoken.get_encoding("cl100k_base")

    def _tok(self, text: str) -> int:
        return len(self.enc.encode(text))

    def chunk(self, text: str, doc_id: str) -> list[dict]:
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: list[dict] = []
        buf: list[str] = []
        buf_tok = 0

        def flush():
            nonlocal buf, buf_tok
            if buf:
                chunks.append(self._make(doc_id, len(chunks), " ".join(buf)))
                buf = self._overlap(buf)
                buf_tok = self._tok(" ".join(buf))

        for para in paragraphs:
            pieces = [para] if self._tok(para) <= self.config.chunk_size else re.split(r"(?<=[.!?])\s+", para)
            for piece in pieces:
                n = self._tok(piece)
                if buf and buf_tok + n > self.config.chunk_size:
                    flush()
                buf.append(piece)
                buf_tok += n
        flush()
        log.info("doc=%s chunks=%d", doc_id, len(chunks))
        return chunks

    def _make(self, doc_id: str, idx: int, text: str) -> dict:
        digest = hashlib.sha256(f"{doc_id}\x1f{idx}\x1f{text}".encode()).hexdigest()
        return {"chunk_id": digest, "doc_id": doc_id, "chunk_index": idx, "text": text, "token_count": self._tok(text)}

    def _overlap(self, pieces: list[str]) -> list[str]:
        window, tokens = [], 0
        for piece in reversed(pieces):
            t = self._tok(piece)
            if tokens + t > self.config.chunk_overlap:
                break
            window.insert(0, piece)
            tokens += t
        return window


class EmbeddingGenerator:
    """Batched embeddings with token and cost tracking."""

    def __init__(self, config: IngestConfig):
        self.config = config
        self.client = OpenAI(max_retries=5)  # SDK retries 429/5xx with exponential backoff
        self.tokens_used = 0
        self.cost_usd = 0.0

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        t0 = time.time()
        r = self.client.embeddings.create(
            model=self.config.embedding_model, input=texts, dimensions=self.config.embedding_dimensions
        )
        tok = r.usage.total_tokens
        self.tokens_used += tok
        self.cost_usd += cost_usd(self.config.embedding_model, tok)
        log.info("embed n=%d tok=%d %.0fms", len(texts), tok, (time.time() - t0) * 1000)
        return [e.embedding for e in r.data]

    def embed_chunks(self, chunks: list[dict]) -> list[dict]:
        size = self.config.embedding_batch_size
        embeddings: list[list[float]] = []
        for i in range(0, len(chunks), size):
            embeddings.extend(self.embed_batch([c["text"] for c in chunks[i : i + size]]))
        return [{**c, "embedding": e} for c, e in zip(chunks, embeddings)]

    @property
    def cost_summary(self) -> dict:
        return {"total_tokens": self.tokens_used, "total_cost_usd": round(self.cost_usd, 6)}


class VectorStore:
    """pgvector table with an HNSW cosine index. Re-ingesting a document replaces its chunks atomically."""

    def __init__(self, config: IngestConfig, pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None):
        self.config = config
        self.table = _validate_identifier(config.table_name)
        self.pool = pool or make_pool(config.db_conn_str)
        self._setup()

    def _conn(self):
        conn = self.pool.getconn()
        register_vector(conn)
        return conn

    def _setup(self):
        conn = self.pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            register_vector(conn)
            with conn, conn.cursor() as cur:
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.table} (
                        chunk_id    TEXT PRIMARY KEY,
                        doc_id      TEXT NOT NULL,
                        chunk_index INT  NOT NULL,
                        text        TEXT NOT NULL,
                        token_count INT,
                        embedding   vector({self.config.embedding_dimensions}),
                        metadata    JSONB DEFAULT '{{}}',
                        ingested_at TIMESTAMPTZ DEFAULT NOW()
                    );
                    -- HNSW builds incrementally, so it is correct on an empty table (IVFFlat is not).
                    CREATE INDEX IF NOT EXISTS idx_{self.table}_emb
                        ON {self.table} USING hnsw (embedding vector_cosine_ops);
                    CREATE INDEX IF NOT EXISTS idx_{self.table}_doc ON {self.table} (doc_id);
                """)
        finally:
            self.pool.putconn(conn)

    def replace_document(self, doc_id: str, chunks: list[dict], metadata: Optional[dict] = None) -> None:
        """Upsert this document's chunks and delete any it no longer has, in one transaction."""
        rows = [
            (
                c["chunk_id"],
                doc_id,
                c["chunk_index"],
                c["text"],
                c["token_count"],
                c["embedding"],
                psycopg2.extras.Json(metadata or {}),
            )
            for c in chunks
        ]
        conn = self._conn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    f"DELETE FROM {self.table} WHERE doc_id = %s AND NOT (chunk_id = ANY(%s))",
                    (doc_id, [c["chunk_id"] for c in chunks]),
                )
                psycopg2.extras.execute_values(
                    cur,
                    f"""
                    INSERT INTO {self.table} (chunk_id, doc_id, chunk_index, text, token_count, embedding, metadata)
                    VALUES %s
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        chunk_index = EXCLUDED.chunk_index, metadata = EXCLUDED.metadata, ingested_at = NOW();
                """,
                    rows,
                )
        finally:
            self.pool.putconn(conn)
        log.info("doc=%s stored %d chunks", doc_id, len(chunks))

    # Backwards-compatible name
    def upsert(self, chunks: list[dict], metadata: Optional[dict] = None) -> None:
        if chunks:
            self.replace_document(chunks[0]["doc_id"], chunks, metadata)


class RAGIngestionPipeline:
    """document -> chunks -> embeddings -> vector store. Re-running on the same doc_id is safe."""

    def __init__(self, config: Optional[IngestConfig] = None, pool=None):
        self.config = config or IngestConfig()
        self.chunker = SemanticChunker(self.config)
        self.embedder = EmbeddingGenerator(self.config)
        self.store = VectorStore(self.config, pool) if pool is not None else VectorStore(self.config)

    def ingest_text(self, text: str, doc_id: str, metadata: Optional[dict] = None) -> dict:
        t0 = time.time()
        chunks = self.embedder.embed_chunks(self.chunker.chunk(text, doc_id))
        self.store.replace_document(doc_id, chunks, metadata)
        return {
            "doc_id": doc_id,
            "chunks": len(chunks),
            "elapsed_sec": round(time.time() - t0, 2),
            **self.embedder.cost_summary,
        }

    def ingest_file(self, path, metadata: Optional[dict] = None) -> dict:
        """Plain-text formats only (.txt, .md). PDFs need a text-extraction step first."""
        p = Path(path)
        return self.ingest_text(
            p.read_text(encoding="utf-8", errors="ignore"),
            doc_id=hashlib.sha256(p.name.encode()).hexdigest()[:16],
            metadata={"filename": p.name, "file_type": p.suffix, **(metadata or {})},
        )
