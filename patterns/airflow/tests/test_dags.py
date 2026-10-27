"""Import and structure checks for the DAGs. Skipped when Airflow isn't installed."""

from pathlib import Path

import pytest

pytest.importorskip("airflow")
from airflow.models.dagbag import DagBag  # noqa: E402

DAGS = Path(__file__).resolve().parents[1] / "dags"


@pytest.fixture(scope="module")
def bag():
    return DagBag(dag_folder=str(DAGS), include_examples=False)


def test_no_import_errors(bag):
    assert bag.import_errors == {}


def test_claims_daily_structure(bag):
    dag = bag.dags["claims_daily"]
    assert [t.task_id for t in dag.topological_sort()] == ["check_source_freshness", "load_partition", "reconcile"]
    for t in dag.tasks:
        assert t.retries == 3 and t.execution_timeout is not None and t.on_failure_callback
    assert dag.max_active_runs == 1
