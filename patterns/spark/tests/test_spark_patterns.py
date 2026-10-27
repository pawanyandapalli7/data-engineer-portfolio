import sys
from pathlib import Path

import pytest
from pyspark.sql import SparkSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quality.data_quality_checks import validate_claims  # noqa: E402
from transformations.deduplicate_claims import deduplicate_claims  # noqa: E402


@pytest.fixture(scope="module")
def spark():
    s = SparkSession.builder.master("local[1]").config("spark.ui.enabled", "false").getOrCreate()
    yield s
    s.stop()


def test_dedup_keeps_latest_and_uses_tiebreak(spark):
    df = spark.createDataFrame(
        [("c1", 1, 1, "open"), ("c1", 2, 1, "approved"), ("c1", 2, 2, "paid"), ("c2", 1, 1, "open")],
        ["claim_id", "updated_at", "seq", "status"],
    )
    out = {r.claim_id: r.status for r in deduplicate_claims(df, tiebreak_col="seq").collect()}
    assert out == {"c1": "paid", "c2": "open"}


def test_validate_claims_quarantines_with_reason(spark):
    df = spark.createDataFrame([("c1", 10.0), (None, 5.0), ("c3", None)], "claim_id string, claim_amount double")
    valid, rejected = validate_claims(df)
    assert valid.count() == 1
    assert {r._reject_reason for r in rejected.collect()} == {"missing claim_id", "missing claim_amount"}
