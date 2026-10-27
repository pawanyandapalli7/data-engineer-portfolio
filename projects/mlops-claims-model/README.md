# MLOps: claims denial model with MLflow, a promotion gate and drift monitoring

The model lifecycle around a claims-denial classifier: one feature function
shared by training and serving, MLflow tracking and Model Registry, a champion
alias that only moves when a new version is measurably better, PSI drift
monitoring, and a FastAPI service that serves whatever the champion is.

The data is synthetic (generated from a fixed seed with a known denial signal),
so every number below can be reproduced exactly with the commands at the end.

| | |
|---|---|
| **Tested** | 12 tests in CI, each against a fresh MLflow SQLite registry: promotion gate, logged artifacts, PSI maths, drift detection, API |
| **Runs locally** | `python -m claims_model.train`, or `docker compose` (train, then serve) |
| **Deployed** | No. Locally the registry is SQLite; on Databricks it would be Unity Catalog models |

```mermaid
flowchart LR
  R[Raw claims] --> F[build_features<br/>one implementation]
  F --> T[Train + evaluate<br/>holdout AUC, PR AUC, Brier]
  T --> L[(MLflow run<br/>params, metrics, model,<br/>training feature baseline)]
  L --> V[Registry: new version]
  V --> G{Beats champion<br/>AUC by 0.002?}
  G -->|yes| C[alias: champion]
  G -->|no| K[kept, not promoted<br/>reason logged]
  C --> S[FastAPI<br/>models:/claims_denial@champion]
  F --> S
  L --> D[Drift monitor<br/>PSI per feature + predictions]
```

## A real run (seed 7, 5,000 synthetic claims, 25% holdout)

| Version | Model | ROC AUC | PR AUC | Brier | Promoted? |
|---|---|---|---|---|---|
| 1 | Gradient boosting | 0.692 | 0.249 | 0.110 | Yes, no champion yet |
| 2 | Logistic regression | 0.715 | 0.282 | 0.107 | **Yes**, beat v1 |
| 3 | Baseline (age only) | 0.471 | 0.142 | 0.115 | **No**, stays registered, champion unchanged |

The simpler model won. The synthetic ground truth is close to logistic, so
that's expected, and it is exactly the decision the gate exists to make on
evidence instead of preference.

Drift check of the champion against a normal batch and a shifted one (bigger
amounts, more out-of-network claims, slower submission):

| Batch | Highest feature PSI | Prediction PSI | Overall |
|---|---|---|---|
| Normal | 0.008 | 0.010 | ok |
| Shifted | `days_to_submit` 0.320, `log_amount` 0.208, `out_of_network` 0.191 | 0.269 | **alert** |

## Design choices

| Choice | Why |
|---|---|
| One `build_features` for training and serving | The API turns raw request fields into features with the same function training used, so there is no second implementation to drift |
| Alias-based deployment (`@champion`) | Promote or roll back by moving an alias; the service code never names a version |
| Promotion needs a margin, not just "higher" | A 0.0001 AUC gain on a holdout is noise; requiring 0.002 stops churn |
| Rejected versions stay registered | The run, its metrics and the `promotion_reason` tag explain why it didn't ship |
| Training features logged with the run | The drift baseline is exactly the data the champion learned from |
| PSI with reference-quantile bins | Every bin starts at ~10% of training data, so small shifts in dense regions still show |

## Run

```bash
pip install -r requirements.txt

PYTHONPATH=src python -m claims_model.train --kind hgb
PYTHONPATH=src python -m claims_model.train --kind logreg      # promoted: beats hgb
PYTHONPATH=src python -m claims_model.train --kind baseline    # refused by the gate
PYTHONPATH=src python -m claims_model.drift --shift            # PSI report, overall: alert
PYTHONPATH=src uvicorn claims_model.serve:app --port 8080
mlflow ui --backend-store-uri sqlite:///mlflow.db
```

```bash
PYTHONPATH=src pytest -v tests
```

With Docker: `docker compose run --rm train`, then `docker compose up -d serve`.

## How this maps to production

At Molina I worked with MLflow tracking and Model Registry, Azure Machine
Learning deployment and drift monitoring. This project is the same lifecycle,
small enough to run on a laptop: SQLite instead of a tracking server, a local
FastAPI service instead of a managed endpoint, and synthetic claims instead of
member data.
