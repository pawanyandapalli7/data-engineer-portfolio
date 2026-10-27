"""
RAG Pipeline — Unit Tests
Tests chunking logic, embedding batching, idempotency, and retrieval quality.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.ingest import IngestConfig, RAGIngestionPipeline, SemanticChunker  # noqa: F401

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def config():
    return IngestConfig(
        chunk_size=100,
        chunk_overlap=20,
        embedding_model="text-embedding-3-small",
        db_conn_str="postgresql://test:test@localhost/test",
    )


@pytest.fixture
def chunker(config):
    return SemanticChunker(config)


SAMPLE_TEXT = """
Data engineering is the practice of designing and building systems for collecting,
storing, and analyzing data at scale.

Modern data engineers work with distributed systems, cloud platforms, and streaming
pipelines. They build the infrastructure that data scientists and analysts rely on.

Change Data Capture (CDC) is a technique for capturing row-level changes in a database
and streaming them downstream in real time. It replaces expensive full-table scans
with incremental updates.

Apache Kafka is a distributed event streaming platform capable of handling trillions
of events per day. It is used for building real-time data pipelines and streaming
applications.
"""


# ── Chunking Tests ────────────────────────────────────────────────────────────


class TestSemanticChunker:
    def test_produces_chunks(self, chunker):
        chunks = chunker.chunk(SAMPLE_TEXT, "doc_test")
        assert len(chunks) >= 1

    def test_chunk_ids_are_unique(self, chunker):
        chunks = chunker.chunk(SAMPLE_TEXT, "doc_test")
        ids = [c["chunk_id"] for c in chunks]
        assert len(ids) == len(set(ids)), "Chunk IDs must be unique"

    def test_all_text_preserved(self, chunker):
        chunks = chunker.chunk(SAMPLE_TEXT, "doc_test")
        combined = " ".join(c["text"] for c in chunks)
        # All key terms should appear in the combined output
        for term in ["CDC", "Kafka", "Data engineering", "Apache", "trillions"]:
            assert term in combined, f"Term '{term}' lost during chunking"

    def test_no_chunk_exceeds_limit(self, chunker):
        chunks = chunker.chunk(SAMPLE_TEXT, "doc_test")
        for c in chunks:
            assert c["token_count"] <= chunker.config.chunk_size + 20, (
                f"Chunk {c['chunk_index']} exceeds token limit: {c['token_count']}"
            )

    def test_chunk_index_sequential(self, chunker):
        chunks = chunker.chunk(SAMPLE_TEXT, "doc_test")
        indices = [c["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_idempotent_chunk_ids(self, chunker):
        """Same text + doc_id must always produce same chunk IDs."""
        chunks1 = chunker.chunk(SAMPLE_TEXT, "doc_abc")
        chunks2 = chunker.chunk(SAMPLE_TEXT, "doc_abc")
        assert [c["chunk_id"] for c in chunks1] == [c["chunk_id"] for c in chunks2]

    def test_empty_text_returns_empty(self, chunker):
        chunks = chunker.chunk("", "doc_empty")
        assert chunks == []

    def test_single_paragraph(self, chunker):
        text = "This is a single paragraph with no breaks."
        chunks = chunker.chunk(text, "doc_single")
        assert len(chunks) == 1
        assert chunks[0]["text"] == text

    def test_different_doc_ids_different_chunk_ids(self, chunker):
        chunks1 = chunker.chunk(SAMPLE_TEXT, "doc_1")
        chunks2 = chunker.chunk(SAMPLE_TEXT, "doc_2")
        ids1 = set(c["chunk_id"] for c in chunks1)
        ids2 = set(c["chunk_id"] for c in chunks2)
        assert ids1.isdisjoint(ids2), "Different doc_ids must produce different chunk_ids"


# ── Embedding Tests ───────────────────────────────────────────────────────────


class TestEmbeddingGenerator:
    def test_batch_embedding_called_correctly(self, config):
        from src.ingest import EmbeddingGenerator

        with patch("src.ingest.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client

            mock_response = MagicMock()
            mock_response.data = [MagicMock(embedding=[0.1] * 10) for _ in range(3)]
            mock_response.usage.total_tokens = 300
            mock_client.embeddings.create.return_value = mock_response

            gen = EmbeddingGenerator(config)
            embeddings = gen.embed_batch(["text1", "text2", "text3"])

        assert len(embeddings) == 3
        assert mock_client.embeddings.create.called

    def test_cost_accumulates(self, config):
        from src.ingest import EmbeddingGenerator

        with patch("src.ingest.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_response = MagicMock()
            mock_response.data = [MagicMock(embedding=[0.1] * 10)]
            mock_response.usage.total_tokens = 1000
            mock_client.embeddings.create.return_value = mock_response

            gen = EmbeddingGenerator(config)
            gen.embed_batch(["text"])
            gen.embed_batch(["text"])

        assert gen.tokens_used == 2000
        assert gen.cost_usd > 0


# ── Pipeline Integration Tests ────────────────────────────────────────────────


class TestRAGIngestionPipeline:
    def test_ingest_returns_correct_shape(self, config):
        with patch("src.ingest.VectorStore") as mock_vs, patch("src.ingest.EmbeddingGenerator") as mock_eg:
            mock_vs.return_value.upsert = MagicMock()
            mock_eg_instance = MagicMock()
            mock_eg_instance.embed_chunks.side_effect = lambda chunks: [{**c, "embedding": [0.1] * 10} for c in chunks]
            mock_eg_instance.cost_summary = {"total_tokens": 100, "total_cost_usd": 0.001}
            mock_eg.return_value = mock_eg_instance

            pipe = RAGIngestionPipeline(config)
            result = pipe.ingest_text(SAMPLE_TEXT, "doc_test")

        assert "doc_id" in result
        assert "chunks" in result
        assert result["chunks"] >= 1
        assert "elapsed_sec" in result

    def test_ingest_is_idempotent(self, config):
        """Second ingest of same doc_id should not raise."""
        with patch("src.ingest.VectorStore") as mock_vs, patch("src.ingest.EmbeddingGenerator") as mock_eg:
            mock_vs.return_value.upsert = MagicMock()
            mock_eg_instance = MagicMock()
            mock_eg_instance.embed_chunks.side_effect = lambda chunks: [{**c, "embedding": [0.1] * 10} for c in chunks]
            mock_eg_instance.cost_summary = {"total_tokens": 100, "total_cost_usd": 0.001}
            mock_eg.return_value = mock_eg_instance

            pipe = RAGIngestionPipeline(config)
            r1 = pipe.ingest_text(SAMPLE_TEXT, "doc_same")
            r2 = pipe.ingest_text(SAMPLE_TEXT, "doc_same")

        # Both should succeed and produce same chunk count
        assert r1["chunks"] == r2["chunks"]


# ── Lexical Reranker Tests ────────────────────────────────────────────────────


class TestLexicalRerank:
    def test_reranks_by_term_overlap(self):
        from src.query import Retriever

        query = "HIPAA breach notification deadline"
        candidates = [
            {
                "chunk_id": "a",
                "similarity": 0.70,
                "text": "General privacy overview with no specific deadlines mentioned.",
            },
            {
                "chunk_id": "b",
                "similarity": 0.68,
                "text": "HIPAA breach notification must occur within 60 days of discovery.",
            },
        ]

        result = Retriever._lexical_rerank(query, candidates, top_n=2)

        assert result[0]["chunk_id"] == "b"  # higher lexical overlap should win despite lower raw similarity

    def test_respects_top_n(self):
        from src.query import Retriever

        candidates = [{"chunk_id": str(i), "similarity": 0.5, "text": "some generic text"} for i in range(10)]
        result = Retriever._lexical_rerank("generic", candidates, top_n=3)

        assert len(result) == 3

    def test_empty_query_terms_falls_back_to_original_order(self):
        from src.query import Retriever

        candidates = [
            {"chunk_id": "a", "similarity": 0.9, "text": "text one"},
            {"chunk_id": "b", "similarity": 0.5, "text": "text two"},
        ]
        # Query with only short/stopword-like tokens that tokenize to nothing
        result = Retriever._lexical_rerank("a to", candidates, top_n=2)

        assert [c["chunk_id"] for c in result] == ["a", "b"]

    def test_tokenize_strips_punctuation_and_short_tokens(self):
        from src.query import Retriever

        tokens = Retriever._tokenize("HIPAA's 60-day rule, Section 3.2!")
        assert "hipaa" in tokens or "s" not in tokens  # punctuation split, no bare "s"
        assert "60" not in tokens  # numeric tokens under length 3 dropped
        assert "day" in tokens
        assert "rule" in tokens
        assert "section" in tokens


# ── Correctness fixes ─────────────────────────────────────────────────────────


class TestConfigAndIds:
    def test_rejects_unindexable_dimensions(self):
        with pytest.raises(ValueError, match="2,000"):
            IngestConfig(embedding_dimensions=3072, db_conn_str="x")

    def test_chunk_ids_are_sha256(self, chunker):
        chunk = chunker.chunk("One short paragraph.", "doc_x")[0]
        assert len(chunk["chunk_id"]) == 64 and int(chunk["chunk_id"], 16) >= 0

    def test_edit_late_in_chunk_changes_its_id(self, chunker):
        a = chunker.chunk("Same opening words here. Ending A.", "doc_x")[0]["chunk_id"]
        b = chunker.chunk("Same opening words here. Ending B.", "doc_x")[0]["chunk_id"]
        assert a != b


class TestReplaceDocument:
    def test_deletes_stale_chunks_then_upserts_in_one_transaction(self, config):
        from src.ingest import VectorStore

        pool = MagicMock()
        conn = pool.getconn.return_value
        cur = conn.cursor.return_value.__enter__.return_value
        with patch("src.ingest.register_vector"), patch("src.ingest.psycopg2.extras.execute_values") as ev:
            store = VectorStore(config, pool=pool)
            cur.reset_mock()
            store.replace_document(
                "doc_1", [{"chunk_id": "a", "chunk_index": 0, "text": "t", "token_count": 1, "embedding": [0.0]}]
            )
        delete_sql, delete_params = cur.execute.call_args[0]
        assert delete_sql.startswith("DELETE") and delete_params == ("doc_1", ["a"])
        assert ev.call_count == 1
        assert pool.putconn.called


class TestContextAndCitations:
    def _chunks(self, n, words=50):
        return [{"chunk_id": f"id{i}", "doc_id": f"doc{i}", "text": " ".join(["word"] * words)} for i in range(n)]

    def test_context_respects_token_budget(self):
        from src.query import build_context

        context, used = build_context(self._chunks(10), max_tokens=200)
        assert 1 <= len(used) < 10
        import tiktoken

        assert len(tiktoken.get_encoding("cl100k_base").encode(context)) <= 200

    def test_first_chunk_always_included(self):
        from src.query import build_context

        _, used = build_context(self._chunks(2, words=500), max_tokens=10)
        assert len(used) == 1

    def test_only_cited_chunks_are_returned(self):
        from src.query import cited_chunks

        chunks = self._chunks(3)
        cited = cited_chunks("Per [Chunk 3] and [Chunk 1], also [Chunk 3]. Not [Chunk 9].", chunks)
        assert [c["chunk_id"] for c in cited] == ["id2", "id0"]


class TestPricing:
    def test_chat_cost_uses_input_and_output_rates(self):
        from src.pricing import cost_usd

        assert cost_usd("gpt-4o-mini", 1_000_000, 1_000_000) == pytest.approx(0.75)

    def test_unknown_model_costs_zero_not_a_guess(self):
        from src.pricing import cost_usd

        assert cost_usd("some-new-model", 1000, 1000) == 0.0
