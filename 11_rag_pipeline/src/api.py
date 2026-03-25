"""
RAG Pipeline — FastAPI Service
Endpoints: /ingest, /query, /health, /metrics
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from ingest import RAGIngestionPipeline, IngestConfig
from query import RAGQueryEngine, RetrievalConfig

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ── Singleton pipeline instances ──────────────────────────────────────────────
ingest_config = IngestConfig()
retrieval_config = RetrievalConfig()
pipeline: RAGIngestionPipeline = None
engine: RAGQueryEngine = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline, engine
    log.info("Initializing RAG pipeline...")
    pipeline = RAGIngestionPipeline(ingest_config)
    engine = RAGQueryEngine(ingest_config, retrieval_config)
    log.info("RAG pipeline ready")
    yield
    log.info("Shutting down")


app = FastAPI(
    title="RAG Pipeline API",
    description="Enterprise document Q&A with semantic search and citations",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Request / Response models ─────────────────────────────────────────────────

class IngestTextRequest(BaseModel):
    text: str
    doc_id: str
    metadata: Optional[dict] = None


class QueryRequest(BaseModel):
    question: str
    doc_ids: Optional[list[str]] = None
    top_k: Optional[int] = 5


class IngestResponse(BaseModel):
    doc_id: str
    chunks: int
    elapsed_sec: float
    total_tokens: int
    total_cost_usd: float


class QueryResponse(BaseModel):
    question: str
    answer: str
    chunks_retrieved: int
    citations: list[str]
    total_latency_ms: int
    cost_usd: float


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "model": ingest_config.embedding_model}


@app.post("/ingest/text", response_model=IngestResponse)
def ingest_text(req: IngestTextRequest):
    try:
        result = pipeline.ingest_text(req.text, req.doc_id, req.metadata)
        return result
    except Exception as e:
        log.error(f"Ingest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/file", response_model=IngestResponse)
async def ingest_file(file: UploadFile = File(...)):
    try:
        text = (await file.read()).decode("utf-8", errors="ignore")
        import hashlib
        doc_id = hashlib.md5(file.filename.encode()).hexdigest()[:16]
        result = pipeline.ingest_text(text, doc_id, {"filename": file.filename})
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    try:
        retrieval_config.top_k = req.top_k
        result = engine.query(req.question, req.doc_ids)
        return result
    except Exception as e:
        log.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics")
def metrics():
    """Cost and usage tracking across session."""
    return {
        "embedding": pipeline.embedder.cost_summary,
        "config": {
            "embedding_model": ingest_config.embedding_model,
            "chat_model": retrieval_config.chat_model,
            "chunk_size": ingest_config.chunk_size,
            "top_k": retrieval_config.top_k,
        },
    }


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
