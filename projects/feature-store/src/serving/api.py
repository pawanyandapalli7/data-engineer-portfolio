"""Real-time feature store: online serving API (single and batched lookups from Redis)."""

import logging
from typing import Optional

import redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ingestion.consumer import FeatureComputer, FeatureStoreConfig

log = logging.getLogger(__name__)
app = FastAPI(title="Feature Store Serving API", version="1.1.0")

config = FeatureStoreConfig.from_env()
r = redis.Redis(host=config.redis_host, port=config.redis_port, db=config.redis_db, decode_responses=True)


class FeatureRequest(BaseModel):
    entity_id: str
    feature_group: str = "user_features"
    feature_names: Optional[list[str]] = None  # None = all features


class FeatureBatchRequest(BaseModel):
    entity_ids: list[str] = Field(min_length=1, max_length=1000)
    feature_group: str = "user_features"
    feature_names: Optional[list[str]] = None


@app.get("/health")
def health():
    try:
        r.ping()
        return {"status": "ok", "redis": "connected"}
    except Exception:
        raise HTTPException(503, "Redis unavailable") from None


@app.post("/features/get")
def get_features(req: FeatureRequest) -> dict:
    """Features for one entity. Missing entity -> empty dict; the model decides how to handle it."""
    key = FeatureComputer.redis_key(req.entity_id, req.feature_group)
    if req.feature_names:
        features = {k: v for k, v in zip(req.feature_names, r.hmget(key, req.feature_names)) if v is not None}
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
    """Many entities in one Redis round trip (pipelined)."""
    pipe = r.pipeline(transaction=False)
    for eid in req.entity_ids:
        key = FeatureComputer.redis_key(eid, req.feature_group)
        if req.feature_names:
            pipe.hmget(key, req.feature_names)
        else:
            pipe.hgetall(key)
    results = {}
    for eid, raw in zip(req.entity_ids, pipe.execute()):
        if req.feature_names:
            results[eid] = {k: v for k, v in zip(req.feature_names, raw) if v is not None}
        else:
            results[eid] = raw or {}
    return {
        "feature_group": req.feature_group,
        "entities_requested": len(req.entity_ids),
        "entities_found": sum(1 for v in results.values() if v),
        "results": results,
    }
