"""Train, evaluate, log to MLflow, register, and promote only if the new model is better.

    python -m claims_model.train --tracking-uri sqlite:///mlflow.db

Promotion gate: the new version gets the `champion` alias only if its holdout
ROC AUC beats the current champion's by at least `min_gain`. The decision and
both scores are logged on the run, so every promotion (or refusal) is auditable.
"""

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import mlflow
import pandas as pd
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from . import CHAMPION, MODEL_NAME
from .data import generate_claims
from .features import BOOLEAN, CATEGORICAL, FEATURES, NUMERIC, TARGET, build_features


@dataclass
class TrainResult:
    run_id: str
    version: str
    metrics: dict
    promoted: bool
    previous_champion_auc: Optional[float]
    reason: str


def make_model(kind: str = "hgb", seed: int = 7) -> Pipeline:
    prep = ColumnTransformer(
        [
            ("num", StandardScaler(), NUMERIC),
            ("bool", "passthrough", BOOLEAN),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
        ]
    )
    if kind == "logreg":
        clf = LogisticRegression(max_iter=1000)
    elif kind == "hgb":
        clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_depth=3, random_state=seed)
    elif kind == "baseline":  # deliberately weak; proves the promotion gate refuses regressions
        prep = ColumnTransformer([("num", StandardScaler(), ["member_age"])])
        clf = LogisticRegression()
    else:
        raise ValueError(f"unknown model kind {kind}")
    return Pipeline([("prep", prep), ("clf", clf)])


def evaluate(model: Pipeline, X: pd.DataFrame, y: pd.Series) -> dict:
    p = model.predict_proba(X)[:, 1]
    return {
        "roc_auc": round(float(roc_auc_score(y, p)), 4),
        "pr_auc": round(float(average_precision_score(y, p)), 4),
        "brier": round(float(brier_score_loss(y, p)), 4),
        "denial_rate": round(float(y.mean()), 4),
    }


def champion_auc(client: MlflowClient) -> Optional[float]:
    try:
        mv = client.get_model_version_by_alias(MODEL_NAME, CHAMPION)
    except Exception:
        return None
    return float(client.get_run(mv.run_id).data.metrics["roc_auc"])


def train(
    raw: Optional[pd.DataFrame] = None,
    kind: str = "hgb",
    seed: int = 7,
    min_gain: float = 0.002,
    experiment: str = "claims_denial",
    reports_dir: Optional[Path] = None,
) -> TrainResult:
    raw = raw if raw is not None else generate_claims(seed=seed)
    X, y = build_features(raw), raw[TARGET]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, stratify=y, random_state=seed)

    mlflow.set_experiment(experiment)
    client = MlflowClient()
    with mlflow.start_run(run_name=f"{kind}-seed{seed}") as run:
        model = make_model(kind, seed).fit(X_tr, y_tr)
        metrics = evaluate(model, X_te, y_te)
        params = {"model_kind": kind, "seed": seed, "n_train": len(X_tr), "n_test": len(X_te)}
        mlflow.log_params({**params, "features": ",".join(FEATURES)})
        mlflow.log_metrics(metrics)
        info = mlflow.sklearn.log_model(
            model,
            name="model",
            signature=infer_signature(X_te, model.predict_proba(X_te)[:, 1]),
            input_example=X_te.head(3),
            registered_model_name=MODEL_NAME,
        )
        version = str(info.registered_model_version)

        prev = champion_auc(client)
        if prev is None:
            promoted, reason = True, "no champion yet"
        elif metrics["roc_auc"] >= prev + min_gain:
            promoted, reason = True, f"roc_auc {metrics['roc_auc']} beats champion {prev} by >= {min_gain}"
        else:
            promoted, reason = False, f"roc_auc {metrics['roc_auc']} does not beat champion {prev} by {min_gain}"
        if promoted:
            client.set_registered_model_alias(MODEL_NAME, CHAMPION, version)
        mlflow.set_tags({"promoted": str(promoted), "promotion_reason": reason})

        # The training feature distribution is stored with the run, as the drift baseline.
        mlflow.log_text(X_tr.to_json(orient="records"), "reference/training_features.json")

    result = TrainResult(run.info.run_id, version, metrics, promoted, prev, reason)
    if reports_dir:
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "latest_training_run.json").write_text(json.dumps(asdict(result), indent=2))
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tracking-uri", default="sqlite:///mlflow.db")
    ap.add_argument("--kind", default="hgb", choices=["hgb", "logreg", "baseline"])
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--reports-dir", default="reports")
    a = ap.parse_args()
    mlflow.set_tracking_uri(a.tracking_uri)
    print(json.dumps(asdict(train(kind=a.kind, seed=a.seed, reports_dir=Path(a.reports_dir))), indent=2))


if __name__ == "__main__":
    main()
