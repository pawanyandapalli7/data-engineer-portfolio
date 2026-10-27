"""RAG pipeline: FastAPI service (POST /ingest/text, POST /ingest/file, POST /query, GET /health, GET /metrics)."""

import hashlib
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ingest import IngestConfig, RAGIngestionPipeline, make_pool
from query import RAGQueryEngine, RetrievalConfig

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

ingest_config = IngestConfig()
retrieval_config = RetrievalConfig(chat_model=os.environ.get("CHAT_MODEL", "gpt-4o-mini"))
state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = make_pool(ingest_config.db_conn_str)
    state["pipeline"] = RAGIngestionPipeline(ingest_config, pool)
    state["engine"] = RAGQueryEngine(ingest_config, retrieval_config, pool)
    log.info("RAG service ready")
    yield
    pool.closeall()


app = FastAPI(title="RAG Pipeline API", version="1.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class IngestTextRequest(BaseModel):
    text: str = Field(min_length=1)
    doc_id: str = Field(min_length=1, max_length=200)
    metadata: Optional[dict] = None


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    doc_ids: Optional[list[str]] = None
    top_k: int = Field(default=5, ge=1, le=20)


@app.get("/health")
def health():
    return {"status": "ok", "embedding_model": ingest_config.embedding_model, "chat_model": retrieval_config.chat_model}


@app.post("/ingest/text")
def ingest_text(req: IngestTextRequest):
    try:
        return state["pipeline"].ingest_text(req.text, req.doc_id, req.metadata)
    except Exception:
        log.exception("Ingest failed for doc_id=%s", req.doc_id)
        raise HTTPException(500, "Ingestion failed. Check server logs.") from None


@app.post("/ingest/file")
async def ingest_file(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith((".txt", ".md")):
        raise HTTPException(415, "Only .txt and .md files are supported.")
    try:
        text = (await file.read()).decode("utf-8", errors="ignore")
        doc_id = hashlib.sha256(file.filename.encode()).hexdigest()[:16]
        return state["pipeline"].ingest_text(text, doc_id, {"filename": file.filename})
    except Exception:
        log.exception("File ingest failed for %s", file.filename)
        raise HTTPException(500, "File ingestion failed. Check server logs.") from None


@app.post("/query")
def query(req: QueryRequest):
    try:
        return state["engine"].query(req.question, req.doc_ids, top_k=req.top_k)
    except Exception:
        log.exception("Query failed")
        raise HTTPException(500, "Query failed. Check server logs.") from None


@app.get("/metrics")
def metrics():
    return {
        "embedding": state["pipeline"].embedder.cost_summary,
        "config": {
            "embedding_model": ingest_config.embedding_model,
            "dimensions": ingest_config.embedding_dimensions,
            "chat_model": retrieval_config.chat_model,
            "chunk_size": ingest_config.chunk_size,
        },
    }


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000)
