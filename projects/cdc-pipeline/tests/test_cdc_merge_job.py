"""
CDC Merge Job — Unit Tests
Covers latest-state resolution, late-arriving events, delete propagation,
and input validation.
"""

import pytest
from pyspark.sql import SparkSession

from cdc_merge_job import merge_latest_state


@pytest.fixture(scope="module")
def spark():
    session = SparkSession.builder.appName("cdc-merge-tests").master("local[1]").getOrCreate()
    yield session
    session.stop()


def test_keeps_latest_change_per_key(spark):
    rows = [
        ("C1", "I", 1, "open"),
        ("C1", "U", 2, "approved"),
        ("C1", "U", 3, "paid"),
    ]
    df = spark.createDataFrame(rows, ["claim_id", "op", "event_ts", "status"])

    result = merge_latest_state(df, key="claim_id", event_ts_col="event_ts", op_col="op")
    row = result.collect()[0]

    assert result.count() == 1
    assert row["status"] == "paid"


def test_handles_late_arriving_events(spark):
    """An out-of-order event (lower event_ts arriving after a higher one)
    must not overwrite the already-latest state."""
    rows = [
        ("C1", "U", 5, "paid"),
        ("C1", "U", 2, "approved"),  # arrives late, but is older by event_ts
    ]
    df = spark.createDataFrame(rows, ["claim_id", "op", "event_ts", "status"])

    result = merge_latest_state(df, key="claim_id", event_ts_col="event_ts", op_col="op")
    row = result.collect()[0]

    assert row["status"] == "paid"


def test_drops_deleted_records(spark):
    rows = [
        ("C1", "D", 1, "open"),
    ]
    df = spark.createDataFrame(rows, ["claim_id", "op", "event_ts", "status"])

    result = merge_latest_state(df, key="claim_id", event_ts_col="event_ts", op_col="op")

    assert result.count() == 0


def test_delete_after_update_removes_record(spark):
    rows = [
        ("C1", "U", 1, "open"),
        ("C1", "D", 2, "open"),
    ]
    df = spark.createDataFrame(rows, ["claim_id", "op", "event_ts", "status"])

    result = merge_latest_state(df, key="claim_id", event_ts_col="event_ts", op_col="op")

    assert result.count() == 0


def test_multiple_keys_independent(spark):
    rows = [
        ("C1", "U", 1, "open"),
        ("C2", "U", 1, "denied"),
    ]
    df = spark.createDataFrame(rows, ["claim_id", "op", "event_ts", "status"])

    result = merge_latest_state(df, key="claim_id", event_ts_col="event_ts", op_col="op")

    assert result.count() == 2


def test_raises_on_missing_required_columns(spark):
    df = spark.createDataFrame([("C1", "open")], ["claim_id", "status"])

    with pytest.raises(ValueError, match="missing required columns"):
        merge_latest_state(df, key="claim_id", event_ts_col="event_ts", op_col="op")


def test_full_load_rows_with_null_op_are_kept(spark):
    """DMS full-load rows have no op unless includeOpForFullLoad is set."""
    df = spark.createDataFrame(
        [("C1", None, 1, "open"), ("C2", "U", 1, "paid")],
        "claim_id string, op string, event_ts int, status string",
    )
    result = merge_latest_state(df, key="claim_id", event_ts_col="event_ts", op_col="op")
    assert sorted(r["claim_id"] for r in result.collect()) == ["C1", "C2"]


def test_sequence_column_breaks_timestamp_ties(spark):
    df = spark.createDataFrame(
        [("C1", "U", 5, 2, "approved"), ("C1", "U", 5, 7, "paid"), ("C1", "U", 5, 4, "pending")],
        ["claim_id", "op", "event_ts", "change_seq", "status"],
    )
    result = merge_latest_state(df, "claim_id", "event_ts", "op", seq_col="change_seq")
    assert result.collect()[0]["status"] == "paid"


def test_delete_wins_a_timestamp_tie_without_sequence(spark):
    df = spark.createDataFrame(
        [("C1", "U", 5, "paid"), ("C1", "D", 5, "paid")],
        ["claim_id", "op", "event_ts", "status"],
    )
    assert merge_latest_state(df, "claim_id", "event_ts", "op").count() == 0


def test_internal_columns_do_not_leak(spark):
    df = spark.createDataFrame([("C1", "I", 1, "open")], ["claim_id", "op", "event_ts", "status"])
    cols = merge_latest_state(df, "claim_id", "event_ts", "op").columns
    assert "_op" not in cols and "_rn" not in cols
