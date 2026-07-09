"""
RAG Pipeline — Document Ingestion Layer
Handles: chunking, embedding generation, vector store upsert
"""

import os, time, hashlib, logging, re
from pathlib import Path
from dataclasses import dataclass, field

import tiktoken
from openai import OpenAI
import psycopg2, psycopg2.extras
from pgvector.psycopg2 import register_vector

log = logging.getLogger(__name__)

_SAFE_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validate_identifier(name: str) -> str:
    """
    table_name is interpolated into DDL/DML below since psycopg2 can't
    parameterize identifiers (only values). Whitelist-validate it here
    so a misconfigured or malicious table_name can't be used for SQL
    injection via CREATE TABLE / INSERT statements.
    """
    if not _SAFE_IDENTIFIER.match(name):
        raise ValueError(f"Unsafe table name: {name!r}")
    return name


@dataclass
class IngestConfig:
    # Chunking
    chunk_size: int = 512          # tokens per chunk
    chunk_overlap: int = 64        # overlap to preserve context at boundaries

    # Embedding
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 3072
    embedding_batch_size: int = 100

    # Vector store
    db_conn_str: str = field(default_factory=lambda: os.environ["DATABASE_URL"])
    table_name: str = "document_chunks"


class SemanticChunker:
    """
    Splits on paragraph/sentence boundaries, respects chunk_size in tokens.

    Why semantic over fixed-size:
      Fixed-size cuts mid-sentence, losing context at boundaries.
      Semantic chunks preserve complete thoughts -> better retrieval precision.
      Tradeoff: variable chunk sizes (acceptable, avg deviation ~10%).
    """

    def __init__(self, config: IngestConfig):
        self.config = config
        self.enc = tiktoken.encoding_for_model("gpt-4")

    def _tok(self, t): return len(self.enc.encode(t))

    def chunk(self, text: str, doc_id: str) -> list[dict]:
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks, buf, buf_tok, idx = [], [], 0, 0

        def flush():
            nonlocal buf, buf_tok, idx
            if buf:
                chunks.append(self._make(doc_id, idx, " ".join(buf)))
                idx += 1
                buf = self._overlap(buf)
                buf_tok = self._tok(" ".join(buf))

        for para in paragraphs:
            pt = self._tok(para)
            if pt > self.config.chunk_size:
                for sent in para.replace(". ", ".\n").split("\n"):
                    st = self._tok(sent)
                    if buf_tok + st > self.config.chunk_size: flush()
                    buf.append(sent); buf_tok += st
            elif buf_tok + pt > self.config.chunk_size:
                flush(); buf.append(para); buf_tok += pt
            else:
                buf.append(para); buf_tok += pt
        flush()
        log.info(f"doc={doc_id} chunks={len(chunks)}")
        return chunks

    def _make(self, doc_id, idx, text):
        return {
            "chunk_id": hashlib.md5(f"{doc_id}:{idx}:{text[:40]}".encode()).hexdigest(),
            "doc_id": doc_id, "chunk_index": idx,
            "text": text, "token_count": self._tok(text),
        }

    def _overlap(self, sentences):
        window, tokens = [], 0
        for s in reversed(sentences):
            t = self._tok(s)
            if tokens + t > self.config.chunk_overlap: break
            window.insert(0, s); tokens += t
        return window


class EmbeddingGenerator:
    """
    Batch embedding with cost tracking.

    Model comparison (retrieval quality vs cost):
      text-embedding-3-large  best quality   $0.13/1M tokens  <- default
      text-embedding-3-small  ~85% quality   $0.02/1M tokens  <- high volume
      text-embedding-ada-002  legacy, worse  $0.10/1M tokens  <- avoid
    """
    _PRICE = {"text-embedding-3-large": 0.13e-6, "text-embedding-3-small": 0.02e-6}

    def __init__(self, config: IngestConfig):
        self.config = config
        self.client = OpenAI()
        self.tokens_used = 0
        self.cost_usd = 0.0

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        t0 = time.time()
        r = self.client.embeddings.create(
            model=self.config.embedding_model, input=texts,
            dimensions=self.config.embedding_dimensions,
        )
        tok = r.usage.total_tokens
        cost = tok * self._PRICE.get(self.config.embedding_model, 0.13e-6)
        self.tokens_used += tok; self.cost_usd += cost
        log.info(f"embed n={len(texts)} tok={tok} cost=${cost:.5f} {(time.time()-t0)*1000:.0f}ms")
        return [e.embedding for e in r.data]

    def embed_chunks(self, chunks: list[dict]) -> list[dict]:
        texts = [c["text"] for c in chunks]
        embs = []
        for i in range(0, len(texts), self.config.embedding_batch_size):
            embs.extend(self.embed_batch(texts[i:i+self.config.embedding_batch_size]))
        for c, e in zip(chunks, embs): c["embedding"] = e
        return chunks

    @property
    def cost_summary(self):
        return {"total_tokens": self.tokens_used, "total_cost_usd": round(self.cost_usd, 6)}


class VectorStore:
    """
    pgvector — runs in your VPC, zero data egress. Idempotent upserts.

    When to use alternatives:
      Pinecone  -> managed scale, data leaves infra, $70+/mo
      Weaviate  -> hybrid search (BM25 + vector), more ops
      qdrant    -> fast, open source, good Docker experience
    """

    def __init__(self, config: IngestConfig):
        self.config = config
        _validate_identifier(config.table_name)
        self.conn = psycopg2.connect(config.db_conn_str)
        register_vector(self.conn)
        self._setup()

    def _setup(self):
        with self.conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.config.table_name} (
                    chunk_id    TEXT PRIMARY KEY,
                    doc_id      TEXT NOT NULL,
                    chunk_index INT NOT NULL,
                    text        TEXT NOT NULL,
                    token_count INT,
                    embedding   vector({self.config.embedding_dimensions}),
                    metadata    JSONB DEFAULT '{{}}',
                    ingested_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_{self.config.table_name}_emb
                    ON {self.config.table_name}
                    USING ivfflat (embedding vector_cosine_ops) WITH (lists=100);
                CREATE INDEX IF NOT EXISTS idx_{self.config.table_name}_doc
                    ON {self.config.table_name} (doc_id);
            """)
        self.conn.commit()
        log.info(f"Vector store ready: table={self.config.table_name}")

    def upsert(self, chunks: list[dict], metadata: dict = None):
        """Idempotent — safe to re-run on the same doc_id."""
        with self.conn.cursor() as cur:
            for c in chunks:
                cur.execute(f"""
                    INSERT INTO {self.config.table_name}
                        (chunk_id, doc_id, chunk_index, text, token_count, embedding, metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        text=EXCLUDED.text, embedding=EXCLUDED.embedding,
                        metadata=EXCLUDED.metadata, ingested_at=NOW();
                """, (c["chunk_id"], c["doc_id"], c["chunk_index"],
                      c["text"], c["token_count"], c["embedding"],
                      psycopg2.extras.Json(metadata or {})))
        self.conn.commit()
        log.info(f"Upserted {len(chunks)} chunks")


class RAGIngestionPipeline:
    """End-to-end: document -> chunks -> embeddings -> vector store. Idempotent."""

    def __init__(self, config: IngestConfig = None):
        self.config = config or IngestConfig()
        self.chunker = SemanticChunker(self.config)
        self.embedder = EmbeddingGenerator(self.config)
        self.store = VectorStore(self.config)

    def ingest_text(self, text: str, doc_id: str, metadata: dict = None) -> dict:
        t0 = time.time()
        chunks = self.chunker.chunk(text, doc_id)
        chunks = self.embedder.embed_chunks(chunks)
        self.store.upsert(chunks, metadata)
        return {"doc_id": doc_id, "chunks": len(chunks),
                "elapsed_sec": round(time.time()-t0, 2), **self.embedder.cost_summary}

    def ingest_file(self, path, metadata: dict = None) -> dict:
        p = Path(path)
        return self.ingest_text(
            p.read_text(encoding="utf-8", errors="ignore"),
            doc_id=hashlib.md5(str(p).encode()).hexdigest()[:16],
            metadata={"filename": p.name, "file_type": p.suffix, **(metadata or {})},
        )

    def ingest_directory(self, directory) -> list[dict]:
        files = list(Path(directory).rglob("*.txt")) + list(Path(directory).rglob("*.md"))
        results = []
        for f in files:
            try: results.append(self.ingest_file(f))
            except Exception as e: log.error(f"Failed {f}: {e}")
        return results
