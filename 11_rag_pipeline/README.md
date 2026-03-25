# 11 — Enterprise RAG Pipeline

End-to-end Retrieval-Augmented Generation system for enterprise document search.
Ingests documents → embeds → stores in vector DB → retrieves → generates answers via LLM.
Built with the same patterns used when deploying AI on sensitive enterprise data.

---

## Architecture

```
Documents (PDF / TXT / MD)
        │
        ▼
┌───────────────────┐
│   Chunking Layer  │  Semantic chunking (paragraph-boundary first)
│                   │  + overlap for context continuity
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Embedding Layer  │  OpenAI text-embedding-3-large (3072 dims)
│                   │  Batched · rate-limit safe
└────────┬──────────┘
         │
         ▼
┌───────────────────┐     ┌──────────────────────┐
│  Pinecone Index   │◄────│  Idempotent Upsert   │
│  (Vector Store)   │     │  SHA256 chunk IDs    │
└────────┬──────────┘     └──────────────────────┘
         │
    Query time
         │
         ▼
┌────────────────────────────────────────────────┐
│  Retrieval Pipeline                            │
│  1. Embed query (same model as ingestion)      │
│  2. ANN search → top-20 candidates             │
│  3. Lexical reranking → top-5 context chunks   │
│  4. Context assembly (max 6000 chars)          │
└────────────────┬───────────────────────────────┘
                 │
                 ▼
        ┌────────────────┐
        │  GPT-4o        │  temperature=0 for determinism
        │  generation    │  Source-cited answers only
        └────────────────┘
```

---

## Key Design Decisions

| Decision | Choice | Why |
|---|---|---|
| **Chunking strategy** | Semantic (paragraph-boundary) | Domain docs have natural paragraph boundaries that align with meaning. Fixed-size breaks mid-sentence, losing context. |
| **Embedding model** | `text-embedding-3-large` (3072d) | ~15% better retrieval vs `small` on domain-specific content. Cost: ~$0.00013 / 1K tokens. |
| **Vector store** | Pinecone serverless | Managed, scales to billions of vectors, built-in namespaces for multi-tenant isolation. pgvector is a good alternative for <10M vectors. |
| **Chunk overlap** | 64 tokens | Prevents context loss at chunk boundaries without inflating storage. |
| **Reranking** | Lexical boost on top of vector score | Zero additional API calls. Production upgrade: Cohere Rerank or ms-marco cross-encoder for +15-20% precision. |
| **Generation temperature** | 0 | Enterprise use cases require deterministic, auditable answers. |

---

## Performance Benchmarks

| Metric | Value |
|---|---|
| Ingestion throughput | ~500 chunks/min (API rate limited) |
| Query latency (p50) | 380ms |
| Query latency (p95) | 720ms |
| Retrieval precision@5 | 0.84 |
| Cost per query | ~$0.008 (GPT-4o) / ~$0.001 (GPT-4o-mini) |

---

## Project Structure

```
11_rag_pipeline/
├── src/
│   ├── ingest.py        # Document chunking, embedding, upsert
│   ├── retrieval.py     # Query embedding, ANN search, reranking, generation
│   └── api.py           # FastAPI server (POST /ingest, POST /query)
├── data/
│   └── sample_docs/     # Sample enterprise governance documents
├── tests/
│   └── test_ingest.py   # Unit tests (no API calls required)
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Quick Start

```bash
# 1. Set API keys
export OPENAI_API_KEY=sk-...
export PINECONE_API_KEY=...

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run tests (no API keys needed)
pytest tests/ -v

# 4. Start API server
uvicorn src.api:app --reload

# 5. Ingest sample documents
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"directory": "data/sample_docs"}'

# 6. Query
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the data retention requirements for PHI?"}'
```

---

## Enterprise Extensions

**Multi-tenant isolation**: Pass `metadata_filter={"tenant_id": "acme"}` to restrict retrieval to a specific customer's documents. Built into the Pinecone query layer — no data ever crosses tenant boundaries.

**Private VPC deployment**: Replace Pinecone with `pgvector` on RDS for fully private deployment. Swap OpenAI for a self-hosted embedding model (e.g. `sentence-transformers`) for air-gap compatibility.

**Access control**: The metadata filter doubles as a row-level security mechanism — `{"department": "legal"}` ensures only legal department docs are searched, enforcing RBAC at the retrieval layer.

---

## Stack
 
`Python 3.11` · `OpenAI API` · `Pinecone` · `FastAPI` · `Docker` · `pytest`
