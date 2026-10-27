"""Serve the current champion: `uvicorn claims_model.serve:app`.

The model is resolved by alias at startup (models:/claims_denial@champion), so
promoting a new version is an alias change plus a restart, with no code change.
Requests carry raw claim fields; the same `build_features` used in training
turns them into model inputs.
"""

import os
from contextlib import asynccontextmanager
from typing import Literal

import mlflow
import pandas as pd
from fastapi import FastAPI, HTTPException
from mlflow.tracking import MlflowClient
from pydantic import BaseModel, Field

from . import CHAMPION, MODEL_NAME
from .features import build_features

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "sqlite:///mlflow.db"))
    mv = MlflowClient().get_model_version_by_alias(MODEL_NAME, CHAMPION)
    state["model"] = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@{CHAMPION}")
    state["version"] = str(mv.version)
    yield
    state.clear()


app = FastAPI(title="Claims denial model", version="1.0.0", lifespan=lifespan)


class Claim(BaseModel):
    claim_amount: float = Field(ge=0)
    out_of_network: bool
    prior_auth: bool
    days_to_submit: int = Field(ge=0, le=3650)
    diagnosis_group: str
    place_of_service: Literal["office", "outpatient", "inpatient", "emergency", "telehealth"]
    member_age: int = Field(ge=0, le=120)
    prior_denials_12m: int = Field(ge=0)


class PredictRequest(BaseModel):
    claims: list[Claim] = Field(min_length=1, max_length=1000)


@app.get("/health")
def health():
    if "model" not in state:
        raise HTTPException(503, "model not loaded")
    return {"status": "ok", "model": MODEL_NAME, "version": state["version"], "alias": CHAMPION}


@app.post("/predict")
def predict(req: PredictRequest):
    raw = pd.DataFrame([c.model_dump() for c in req.claims])
    probs = state["model"].predict_proba(build_features(raw))[:, 1]
    return {
        "model_version": state["version"],
        "predictions": [{"denial_probability": round(float(p), 4)} for p in probs],
    }
