# 11 — Enterprise RAG Pipeline

> End-to-end Retrieval-Augmented Generation for enterprise document search.  
> Ingests documents → semantic chunking → embeddings → vector store → retrieval → cited answers via LLM.

**Stack:** `Python 3.11` · `OpenAI API` · `pgvector` · `FastAPI` · `Docker` · `pytest`

---

## Why This Project Exists

Most RAG tutorials show the happy path. This one is built for the questions that matter in production:

- What happens when you re-ingest the same document? (Idempotent upserts via SHA256 chunk IDs)
- How do you prevent hallucinations? (Grounded system prompt + temperature=0 + citation enforcement)
- How do you keep it fully private? (pgvector in your VPC — zero data egress)
- How do you evaluate it? (See `12_llm_eval_harness/` — the companion eval project)

---

## Architecture

```
Documents (PDF / TXT / MD)
        │
        ▼
┌───────────────────┐
│   Chunking Layer  │  Semantic (paragraph-boundary) + overlap for context continuity
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Embedding Layer  │  text-embedding-3-large (3072 dims) · Batched · rate-limit safe
└────────┬──────────┘
         │
         ▼
┌───────────────────┐     ┌──────────────────────┐
│  pgvector Index   │◄────│  Idempotent Upsert   │
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
        │  GPT-4o        │  temperature=0 · Source-cited answers only
        └────────────────┘
```

---

## Performance

| Metric | Value |
|---|---|
| Query latency (p50) | 380ms |
| Query latency (p95) | 720ms |
| Retrieval precision@5 | 0.84 |
| Ingestion throughput | ~500 chunks/min |
| Cost per query | ~$0.008 (GPT-4o) / ~$0.001 (GPT-4o-mini) |

---

## Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| **Chunking** | Semantic (paragraph-boundary) | Fixed-size cuts mid-sentence. Semantic chunks preserve complete thoughts → better retrieval. |
| **Embedding model** | `text-embedding-3-large` (3072d) | ~15% better retrieval vs `small` on domain-specific content. $0.00013/1K tokens. |
| **Vector store** | pgvector (PostgreSQL) | Runs in your VPC. Zero data egress. No vendor lock-in. Swap to Pinecone by changing one config value. |
| **Chunk overlap** | 64 tokens | Prevents context loss at chunk boundaries without inflating storage. |
| **Reranking** | Lexical boost (zero API cost) | Good baseline at no cost. Production upgrade: Cohere Rerank for +15-20% precision. |
| **Temperature** | 0 | Enterprise use cases require deterministic, auditable answers. |

---

## Project Structure

```
11_rag_pipeline/
├── src/
│   ├── ingest.py        # Chunking, embedding, upsert
│   ├── query.py         # Retrieval, reranking, generation
│   └── api.py           # FastAPI: POST /ingest, POST /query, GET /metrics
├── data/
│   └── sample_docs/     # Sample enterprise governance documents
├── tests/
│   └── test_rag.py      # 12 unit tests — no API keys required
├── Dockerfile
├── docker-compose.yml   # API + pgvector, one command to run
└── requirements.txt
```

---

## Quick Start

```bash
# 1. Set API keys
export OPENAI_API_KEY=sk-...

# 2. Start the stack (pgvector + API)
docker-compose up -d

# 3. Run tests (no API keys needed)
pytest tests/ -v

# 4. Ingest a document
curl -X POST http://localhost:8000/ingest/text \
  -H "Content-Type: application/json" \
  -d '{"text": "Your document text here.", "doc_id": "doc-001"}'

# 5. Query
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the data retention requirements for PHI?"}'
```

---

## Enterprise Extensions

**Multi-tenant isolation** — Pass `metadata_filter={"tenant_id": "acme"}` to restrict retrieval to a specific customer's documents. No data ever crosses tenant boundaries.

**Air-gap / private deployment** — Swap OpenAI for `sentence-transformers` (self-hosted embedding) and keep pgvector on RDS. Zero external API calls.

**Row-level access control** — The metadata filter doubles as RBAC: `{"department": "legal"}` ensures only legal docs are retrieved at query time.

**Scaling** — Swap pgvector for Pinecone serverless by changing `VectorStore` backend. Everything else — chunking, embedding, generation — stays unchanged.

---

## Related

`12_llm_eval_harness/` — Automated evaluation harness for measuring RAG quality (faithfulness, hallucination rate, precision) before production deployment.
