from datetime import date, datetime
from decimal import Decimal

import pytest
from pyspark.sql import functions as F

from lakehouse.scd2 import scd2_merge
from lakehouse.transforms import claims_by_month, fact_claim_lines, to_bronze, to_silver

PATIENT_COLS = ["Id", "BIRTHDATE", "DEATHDATE", "GENDER", "STATE", "COUNTY", "ZIP", "FIRST"]


def raw_patients(spark, rows):
    return spark.createDataFrame(rows, PATIENT_COLS)


def bronze_batch(spark, src, rows, batch, ts):
    b = to_bronze(raw_patients(spark, rows), src, batch)
    return b.withColumn("_ingested_at", F.lit(ts).cast("timestamp"))


def test_config_has_three_sources(sources):
    assert set(sources) == {"patients", "claims", "claim_transactions"}
    assert sources["claims"].silver_key == ["claim_id"]


def test_bronze_keeps_only_declared_columns_and_adds_lineage(spark, sources):
    b = to_bronze(
        raw_patients(spark, [("p1", "1980-01-02", "", "F", "CA", "Alameda", "94568", "Ana")]), sources["patients"], "b1"
    )
    assert "FIRST" not in b.columns  # direct identifiers never enter the lake
    assert {"_source_file", "_batch_id", "_ingested_at"} <= set(b.columns)


def test_bronze_fails_loudly_on_missing_columns(spark, sources):
    with pytest.raises(ValueError, match="missing columns"):
        to_bronze(spark.createDataFrame([("p1",)], ["Id"]), sources["patients"], "b1")


def test_silver_types_dedups_latest_and_quarantines(spark, sources):
    src = sources["patients"]
    b1 = bronze_batch(
        spark,
        src,
        [
            ("p1", "1980-01-02", "", "F", "CA", "Alameda", "94568", "x"),
            ("p2", "2999-01-01", "", "M", "CA", "Alameda", "94566", "x"),  # future birth date
            ("p3", "1990-05-05", "", "X", "NV", "Washoe", "89501", "x"),
        ],  # unknown gender
        "b1",
        "2026-01-01 00:00:00",
    )
    b2 = bronze_batch(
        spark, src, [("p1", "1980-01-02", "", "F", "CA", "Alameda", "94588", "x")], "b2", "2026-02-01 00:00:00"
    )
    passed, failed = to_silver(b1.unionByName(b2), src)
    rows = {r.patient_id: r for r in passed.collect()}
    assert set(rows) == {"p1"}
    assert rows["p1"].zip == "94588"  # latest batch wins
    assert rows["p1"].death_date is None  # '' became NULL
    assert rows["p1"].birth_date == date(1980, 1, 2)  # typed
    reasons = {r.patient_id: set(r._failed_checks) for r in failed.collect()}
    assert reasons == {"p2": {"birth_date_valid"}, "p3": {"gender_known"}}


def test_silver_replay_of_same_batch_is_a_no_op(spark, sources):
    src = sources["patients"]
    row = [("p1", "1980-01-02", "", "F", "CA", "Alameda", "94568", "x")]
    once, _ = to_silver(bronze_batch(spark, src, row, "b1", "2026-01-01 00:00:00"), src)
    twice, _ = to_silver(
        bronze_batch(spark, src, row, "b1", "2026-01-01 00:00:00").unionByName(
            bronze_batch(spark, src, row, "b1", "2026-01-01 00:00:00")
        ),
        src,
    )
    assert once.count() == twice.count() == 1


def _dim(spark, rows):
    return spark.createDataFrame(
        rows, "patient_id string, gender string, state string, county string, zip string, death_date date"
    )


def test_scd2_initial_change_insert_and_gap(spark):
    tracked = ["gender", "state", "county", "zip", "death_date"]
    v1 = scd2_merge(
        None,
        _dim(spark, [("p1", "F", "CA", "Alameda", "94568", None), ("p2", "M", "CA", "Alameda", "94566", None)]),
        "patient_id",
        tracked,
        "2026-01-01",
    )
    assert v1.where("is_current").count() == 2

    # p1 moves, p2 missing from snapshot, p3 is new
    v2 = scd2_merge(
        v1,
        _dim(spark, [("p1", "F", "NV", "Washoe", "89501", None), ("p3", "M", "CA", "Contra Costa", "94520", None)]),
        "patient_id",
        tracked,
        "2026-03-01",
    )
    r = {(x.patient_id, x.is_current): x for x in v2.collect()}
    assert r[("p1", False)].zip == "94568" and r[("p1", False)].valid_to == date(2026, 2, 28)
    assert r[("p1", True)].zip == "89501" and r[("p1", True)].valid_from == date(2026, 3, 1)
    assert r[("p2", True)].valid_from == date(2026, 1, 1)  # gap is not a delete
    assert ("p3", True) in r
    assert v2.count() == 4

    # same snapshot again → nothing changes (idempotent)
    v3 = scd2_merge(
        v2,
        _dim(spark, [("p1", "F", "NV", "Washoe", "89501", None), ("p3", "M", "CA", "Contra Costa", "94520", None)]),
        "patient_id",
        tracked,
        "2026-04-01",
    )
    assert sorted(map(tuple, v3.collect())) == sorted(map(tuple, v2.collect()))


def test_gold_fact_and_monthly_rollup(spark):
    claims = spark.createDataFrame(
        [
            ("c1", "p1", "dr1", "pay1", datetime(2026, 1, 5), "J45"),
            ("c2", "p2", "dr1", "pay1", datetime(2026, 2, 9), "E11"),
        ],
        "claim_id string, patient_id string, provider_id string, payer_id string, "
        "service_ts timestamp, primary_diagnosis string",
    )
    txns = spark.createDataFrame(
        [
            ("t1", "c1", "p1", "CHARGE", Decimal("120.00"), "99213"),
            ("t2", "c1", "p1", "PAYMENT", Decimal("100.00"), "99213"),
            ("t3", "c2", "p2", "CHARGE", Decimal("80.50"), "83036"),
        ],
        "transaction_id string, claim_id string, patient_id string, txn_type string, "
        "amount decimal(12,2), procedure_code string",
    )
    fact = fact_claim_lines(claims, txns)
    assert fact.count() == 3 and fact.where("provider_id IS NULL").count() == 0
    m = {r.month: r for r in claims_by_month(fact).collect()}
    assert m[date(2026, 1, 1)].charged == Decimal("120.00") and m[date(2026, 1, 1)].paid == Decimal("100.00")
    assert m[date(2026, 2, 1)].claims == 1


def test_end_to_end_on_sample_data(spark, sources, tmp_path):
    """bronze → silver → gold on the bundled sample, using the same functions the job uses."""
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, str(root / "sample_data" / "make_sample.py")], check=True, capture_output=True)
    data = root / "sample_data" / "synthea"
    silver = {}
    for name, src in sources.items():
        raw = spark.read.option("header", True).csv(str(data / src.file))
        passed, failed = to_silver(to_bronze(raw, src, "sample"), src)
        bad_ratio = failed.count() / raw.count()
        assert bad_ratio < 0.05, f"{name}: {bad_ratio:.1%} quarantined"
        silver[name] = passed
    assert silver["patients"].count() == 294  # 6 of 300 have an unknown gender
    assert silver["claims"].count() == 1180  # 20 of 1200 have a negative balance
    fact = fact_claim_lines(silver["claims"], silver["claim_transactions"])
    assert fact.where("service_date IS NULL").count() == 40  # transactions of quarantined claims stay visible
    monthly = claims_by_month(fact.where("service_date IS NOT NULL")).collect()
    assert len(monthly) >= 18 and all(r.paid <= r.charged for r in monthly)


def test_scd2_second_change_on_same_day_never_inverts_dates(spark):
    tracked = ["gender", "state", "county", "zip", "death_date"]
    v1 = scd2_merge(
        None, _dim(spark, [("p1", "F", "CA", "Alameda", "94568", None)]), "patient_id", tracked, "2026-01-01"
    )
    v2 = scd2_merge(v1, _dim(spark, [("p1", "F", "NV", "Washoe", "89501", None)]), "patient_id", tracked, "2026-03-01")
    v3 = scd2_merge(v2, _dim(spark, [("p1", "F", "NV", "Washoe", "89502", None)]), "patient_id", tracked, "2026-03-01")
    rows = v3.collect()
    assert all(r.valid_from <= r.valid_to for r in rows)
    current = [r for r in rows if r.is_current]
    assert len(current) == 1 and current[0].zip == "89502" and current[0].valid_from == date(2026, 3, 1)
    assert len(rows) == 2  # Jan version closed, same-day correction replaced in place
