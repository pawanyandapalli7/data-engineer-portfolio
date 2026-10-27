"""Data and prediction drift with the Population Stability Index (PSI).

PSI = sum((cur% - ref%) * ln(cur% / ref%)) over bins. Common reading:
< 0.1 stable, 0.1-0.25 worth a look, > 0.25 the population has moved.
Numeric bins are reference quantiles, so each bin holds about 10% of the
training data; categories and flags are their own bins, with unseen categories counted too.

    python -m claims_model.drift --tracking-uri sqlite:///mlflow.db --shift
"""

import argparse
import json
from typing import Optional

import numpy as np
import pandas as pd

from .features import BOOLEAN, CATEGORICAL, NUMERIC

WARN, ALERT = 0.10, 0.25
_EPS = 1e-6


def _psi(ref: np.ndarray, cur: np.ndarray) -> float:
    ref, cur = np.clip(ref, _EPS, None), np.clip(cur, _EPS, None)
    return float(np.sum((cur - ref) * np.log(cur / ref)))


def psi_numeric(reference: pd.Series, current: pd.Series, bins: int = 10) -> float:
    edges = np.unique(np.quantile(reference.dropna(), np.linspace(0, 1, bins + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    ref = np.histogram(reference.dropna(), edges)[0] / max(reference.notna().sum(), 1)
    cur = np.histogram(current.dropna(), edges)[0] / max(current.notna().sum(), 1)
    return _psi(ref, cur)


def psi_categorical(reference: pd.Series, current: pd.Series) -> float:
    cats = sorted(set(reference.dropna()) | set(current.dropna()))
    ref = reference.value_counts(normalize=True).reindex(cats, fill_value=0).to_numpy()
    cur = current.value_counts(normalize=True).reindex(cats, fill_value=0).to_numpy()
    return _psi(ref, cur)


def status(value: float) -> str:
    return "alert" if value > ALERT else "warn" if value > WARN else "ok"


def drift_report(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    ref_scores: Optional[np.ndarray] = None,
    cur_scores: Optional[np.ndarray] = None,
) -> dict:
    features = {}
    for col in NUMERIC:
        features[col] = psi_numeric(reference[col], current[col])
    for col in CATEGORICAL + BOOLEAN:
        features[col] = psi_categorical(reference[col], current[col])
    report = {
        "features": {k: {"psi": round(v, 4), "status": status(v)} for k, v in features.items()},
        "thresholds": {"warn": WARN, "alert": ALERT},
    }
    if ref_scores is not None and cur_scores is not None:
        p = psi_numeric(pd.Series(ref_scores), pd.Series(cur_scores))
        report["prediction"] = {"psi": round(p, 4), "status": status(p)}
    statuses = [v["status"] for v in report["features"].values()] + [report.get("prediction", {}).get("status", "ok")]
    report["overall"] = "alert" if "alert" in statuses else "warn" if "warn" in statuses else "ok"
    report["drifted_features"] = sorted(k for k, v in report["features"].items() if v["status"] != "ok")
    return report


def main():
    import mlflow
    from mlflow.tracking import MlflowClient

    from . import CHAMPION, MODEL_NAME
    from .data import generate_claims
    from .features import build_features

    ap = argparse.ArgumentParser()
    ap.add_argument("--tracking-uri", default="sqlite:///mlflow.db")
    ap.add_argument("--shift", action="store_true", help="score a shifted batch instead of a normal one")
    a = ap.parse_args()
    mlflow.set_tracking_uri(a.tracking_uri)

    mv = MlflowClient().get_model_version_by_alias(MODEL_NAME, CHAMPION)
    reference = pd.read_json(
        mlflow.artifacts.load_text(f"runs:/{mv.run_id}/reference/training_features.json"), orient="records"
    )
    model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@{CHAMPION}")
    current = build_features(generate_claims(n=2000, seed=99, shift=a.shift))
    report = drift_report(reference, current, model.predict_proba(reference)[:, 1], model.predict_proba(current)[:, 1])
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
