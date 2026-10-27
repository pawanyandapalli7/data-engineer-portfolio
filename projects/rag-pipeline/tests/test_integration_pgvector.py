"""
Integration test against a real PostgreSQL + pgvector.

Skipped unless RAG_TEST_DATABASE_URL is set (CI starts a pgvector service for
it). OpenAI is replaced by a deterministic bag-of-words embedder so the test is
free, offline and repeatable, while every SQL statement runs for real.
"""

import hashlib
import math
import os
import re
from unittest.mock import patch

import pytest

DB = os.environ.get("RAG_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB, reason="RAG_TEST_DATABASE_URL not set")

DIMS = 64


def fake_embed(texts):
    """Hash each word into one of DIMS buckets, then L2-normalise."""
    out = []
    for t in texts:
        v = [0.0] * DIMS
        for w in re.findall(r"[a-z0-9]+", t.lower()):
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % DIMS] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / n for x in v])
    return out


@pytest.fixture
def stack():
    from src.ingest import IngestConfig, RAGIngestionPipeline, make_pool
    from src.query import RetrievalConfig, Retriever

    table = "it_chunks_" + hashlib.md5(os.urandom(8)).hexdigest()[:8]
    cfg = IngestConfig(db_conn_str=DB, table_name=table, embedding_dimensions=DIMS, chunk_size=15, chunk_overlap=0)
    pool = make_pool(DB)
    with patch("src.ingest.OpenAI"), patch("ingest.OpenAI"):
        pipe = RAGIngestionPipeline(cfg, pool)
        retriever = Retriever(cfg, RetrievalConfig(similarity_threshold=0.0, top_k=2), pool)
    pipe.embedder.embed_batch = fake_embed
    retriever.embedder.embed_batch = fake_embed
    yield pipe, retriever, pool, table
    conn = pool.getconn()
    with conn, conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {table}")
    pool.putconn(conn)
    pool.closeall()


def count(pool, table, doc_id):
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {table} WHERE doc_id = %s", (doc_id,))
            return cur.fetchone()[0]
    finally:
        conn.rollback()
        pool.putconn(conn)


DOC = """HIPAA breach notifications must be sent within sixty days of discovery.

Claims are adjudicated within thirty business days of receipt.

Prior authorization is required for elective MRI imaging."""


def test_ingest_search_and_reingest(stack):
    pipe, retriever, pool, table = stack
    result = pipe.ingest_text(DOC, "policy")
    assert result["chunks"] >= 2

    hits = retriever.search("when must breach notifications be sent")
    assert hits and "breach" in hits[0]["text"].lower()

    # Same text again: same rows, no duplicates
    pipe.ingest_text(DOC, "policy")
    assert count(pool, table, "policy") == result["chunks"]

    # Document shrinks: stale chunks are removed
    pipe.ingest_text("Only one short paragraph remains.", "policy")
    assert count(pool, table, "policy") == 1


def test_doc_filter(stack):
    pipe, retriever, pool, table = stack
    pipe.ingest_text("Kafka topics and partitions.", "a")
    pipe.ingest_text("Kafka consumer groups.", "b")
    hits = retriever.search("kafka", doc_ids=["b"])
    assert {h["doc_id"] for h in hits} == {"b"}
