import sys
from pathlib import Path

import mlflow
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture
def tracking(tmp_path, monkeypatch):
    """A fresh MLflow tracking server + registry (SQLite) per test."""
    monkeypatch.chdir(tmp_path)
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    mlflow.set_tracking_uri(uri)
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)
    yield uri
    mlflow.set_tracking_uri(None)
