"""
Real-Time Feature Store — Online Serving API
Low-latency feature retrieval for ML inference (<5ms p99).
"""

import logging
from typing import Optional

import redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ingestion.consumer import FeatureComputer, FeatureStoreConfig

log = logging.getLogger(__name__)
app = FastAPI(title="Feature Store Serving API", version="1.0.0")

config = FeatureStoreConfig()
r = redis.Redis(host=config.redis_host, port=config.redis_port,
                db=config.redis_db, decode_responses=True)


class FeatureRequest(BaseModel):
    entity_id: str
    feature_group: str = "user_features"
    feature_names: Optional[list[str]] = None  # None = return all features


class FeatureBatchRequest(BaseModel):
    entity_ids: list[str]
    feature_group: str = "user_features"
    feature_names: Optional[list[str]] = None


@app.get("/health")
def health():
    try:
        r.ping()
        return {"status": "ok", "redis": "connected"}
    except Exception:
        raise HTTPException(503, "Redis unavailable")


@app.post("/features/get")
def get_features(req: FeatureRequest) -> dict:
    """
    Get features for a single entity.
    Returns empty dict if entity not found (no error — model handles missing features).
    """
    key = FeatureComputer.redis_key(req.entity_id, req.feature_group)

    if req.feature_names:
        values = r.hmget(key, req.feature_names)
        features = {k: v for k, v in zip(req.feature_names, values) if v is not None}
    else:
        features = r.hgetall(key)

    return {
        "entity_id": req.entity_id,
        "feature_group": req.feature_group,
        "features": features,
        "found": bool(features),
    }


@app.post("/features/batch")
def get_features_batch(req: FeatureBatchRequest) -> dict:
    """
    Bulk feature retrieval for batch inference.
    Uses Redis pipeline for O(1) round trips regardless of entity count.
    """
    pipe = r.pipeline()
    keys = [FeatureComputer.redis_key(eid, req.feature_group) for eid in req.entity_ids]

    for key in keys:
        if req.feature_names:
            pipe.hmget(key, req.feature_names)
        else:
            pipe.hgetall(key)

    results_raw = pipe.execute()

    results = {}
    for entity_id, raw in zip(req.entity_ids, results_raw):
        if req.feature_names and isinstance(raw, list):
            features = {k: v for k, v in zip(req.feature_names, raw) if v is not None}
        else:
            features = raw or {}
        results[entity_id] = features

    return {
        "feature_group": req.feature_group,
        "entities_requested": len(req.entity_ids),
        "entities_found": sum(1 for v in results.values() if v),
        "results": results,
    }


@app.get("/features/stats")
def stats() -> dict:
    """Feature store stats — useful for SLA monitoring."""
    info = r.info("memory")
    return {
        "redis_used_memory_mb": round(info["used_memory"] / 1024 / 1024, 2),
        "redis_used_memory_peak_mb": round(info["used_memory_peak"] / 1024 / 1024, 2),
        "keyspace": r.info("keyspace"),
    }
