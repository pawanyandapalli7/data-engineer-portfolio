import numpy as np
import pandas as pd
import pytest
from mlflow.tracking import MlflowClient

from claims_model import CHAMPION, MODEL_NAME
from claims_model.data import generate_claims
from claims_model.drift import drift_report, psi_categorical, psi_numeric
from claims_model.features import EXCLUDED, FEATURES, build_features
from claims_model.train import train

# ── Features ────────────────────────────────────────────────────────────────


def test_features_never_include_ids_dates_or_target():
    assert not set(FEATURES) & EXCLUDED
    assert list(build_features(generate_claims(50)).columns) == FEATURES


def test_features_are_deterministic_and_rule_based():
    raw = pd.DataFrame(
        [
            {
                "claim_amount": 0,
                "out_of_network": True,
                "prior_auth": False,
                "days_to_submit": 61,
                "diagnosis_group": "cardio",
                "place_of_service": "inpatient",
                "member_age": 40,
                "prior_denials_12m": 1,
            }
        ]
    )
    f = build_features(raw).iloc[0]
    assert f["log_amount"] == 0.0 and f["late_submission"] == 1 and f["missing_prior_auth_facility"] == 1
    pd.testing.assert_frame_equal(build_features(raw), build_features(raw.copy()))


def test_missing_raw_column_fails_loudly():
    with pytest.raises(ValueError, match="claim_amount"):
        build_features(generate_claims(5).drop(columns=["claim_amount"]))


def test_synthetic_data_is_reproducible():
    pd.testing.assert_frame_equal(generate_claims(100, seed=3), generate_claims(100, seed=3))


# ── Training, registry and the promotion gate ───────────────────────────────


def test_first_model_becomes_champion_and_beats_chance(tracking):
    result = train(kind="logreg")
    assert result.promoted and result.reason == "no champion yet"
    assert result.metrics["roc_auc"] > 0.65  # synthetic signal is learnable
    assert str(MlflowClient().get_model_version_by_alias(MODEL_NAME, CHAMPION).version) == result.version


def test_worse_model_is_registered_but_not_promoted(tracking):
    champion = train(kind="logreg")
    challenger = train(kind="baseline")
    client = MlflowClient()
    assert not challenger.promoted
    assert str(client.get_model_version_by_alias(MODEL_NAME, CHAMPION).version) == champion.version
    assert client.get_run(challenger.run_id).data.tags["promoted"] == "False"
    assert len(client.search_model_versions(f"name='{MODEL_NAME}'")) == 2


def test_run_logs_params_metrics_and_drift_baseline(tracking):
    result = train(kind="logreg")
    run = MlflowClient().get_run(result.run_id)
    assert {"roc_auc", "pr_auc", "brier"} <= set(run.data.metrics)
    assert run.data.params["features"] == ",".join(FEATURES)
    artifacts = [a.path for a in MlflowClient().list_artifacts(result.run_id, "reference")]
    assert artifacts == ["reference/training_features.json"]


# ── Drift ───────────────────────────────────────────────────────────────────


def test_psi_near_zero_for_same_distribution():
    rng = np.random.default_rng(0)
    assert psi_numeric(pd.Series(rng.normal(size=5000)), pd.Series(rng.normal(size=5000))) < 0.02


def test_psi_large_for_shifted_distribution():
    rng = np.random.default_rng(0)
    assert psi_numeric(pd.Series(rng.normal(size=5000)), pd.Series(rng.normal(1.0, 1, size=5000))) > 0.25


def test_categorical_psi_counts_unseen_categories():
    ref = pd.Series(["a"] * 50 + ["b"] * 50)
    assert psi_categorical(ref, pd.Series(["a"] * 50 + ["b"] * 50)) == pytest.approx(0, abs=1e-9)
    assert psi_categorical(ref, pd.Series(["a"] * 50 + ["c"] * 50)) > 1.0


def test_report_flags_the_shifted_batch_but_not_a_normal_one():
    ref = build_features(generate_claims(4000, seed=1))
    normal = drift_report(ref, build_features(generate_claims(2000, seed=2)))
    shifted = drift_report(ref, build_features(generate_claims(2000, seed=2, shift=True)))
    assert normal["overall"] == "ok" and normal["drifted_features"] == []
    assert shifted["overall"] == "alert"
    assert {"log_amount", "days_to_submit", "out_of_network"} <= set(shifted["drifted_features"])


# ── Serving ─────────────────────────────────────────────────────────────────


def test_api_serves_the_champion(tracking):
    from fastapi.testclient import TestClient

    from claims_model.serve import app

    champion = train(kind="logreg")
    claim = {
        "claim_amount": 1200.0,
        "out_of_network": True,
        "prior_auth": False,
        "days_to_submit": 75,
        "diagnosis_group": "cardio",
        "place_of_service": "inpatient",
        "member_age": 61,
        "prior_denials_12m": 2,
    }
    low_risk = {
        **claim,
        "out_of_network": False,
        "prior_auth": True,
        "days_to_submit": 3,
        "prior_denials_12m": 0,
        "diagnosis_group": "preventive",
        "place_of_service": "office",
        "claim_amount": 90.0,
    }
    with TestClient(app) as client:
        assert client.get("/health").json()["version"] == champion.version
        body = client.post("/predict", json={"claims": [claim, low_risk]}).json()
        high, low = (p["denial_probability"] for p in body["predictions"])
        assert 0 <= low < high <= 1
        assert client.post("/predict", json={"claims": [{**claim, "place_of_service": "spaceship"}]}).status_code == 422
