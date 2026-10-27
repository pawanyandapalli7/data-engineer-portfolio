from datetime import date
from decimal import Decimal

import pytest

from validations import sql_tests
from validations.business_rules import apply_rules, failure_summary
from validations.reconciliation import reconcile
from validations.schema_validation import validate_schema

CLAIMS_DDL = (
    "claim_id string, member_id string, service_date date, claim_date date, claim_amount decimal(10,2), status string"
)


def claims(spark, rows):
    return spark.createDataFrame(rows, CLAIMS_DDL)


GOOD = ("c1", "m1", date(2026, 1, 3), date(2026, 1, 10), Decimal("120.00"), "APPROVED")


class TestSchema:
    def test_generic_decimal_matches_any_precision(self, spark):
        assert validate_schema(claims(spark, [GOOD]), {"claim_amount": "decimal", "claim_id": "string"}) == []

    def test_exact_decimal_must_match(self, spark):
        errors = validate_schema(claims(spark, [GOOD]), {"claim_amount": "decimal(12,2)"})
        assert errors == ["type mismatch on claim_amount: expected decimal(12,2), got decimal(10,2)"]

    def test_missing_and_extra_columns(self, spark):
        errors = validate_schema(
            claims(spark, [GOOD]).select("claim_id", "status"),
            {"claim_id": "string", "provider_id": "string"},
            allow_extra=False,
        )
        assert "missing column: provider_id" in errors and "unexpected column: status" in errors


class TestBusinessRules:
    def test_valid_claim_passes(self, spark):
        passed, failed = apply_rules(claims(spark, [GOOD]))
        assert passed.count() == 1 and failed.count() == 0

    def test_failures_are_tagged_not_dropped(self, spark):
        rows = [
            GOOD,
            ("c2", "m1", date(2026, 2, 10), date(2026, 2, 1), Decimal("50.00"), "APPROVED"),  # claimed before service
            ("c3", "m2", date(2026, 1, 1), date(2026, 1, 2), Decimal("-5.00"), "DENIED"),  # negative amount
            ("c4", "m2", None, date(2026, 1, 2), Decimal("5.00"), "DENIED"),  # NULL date fails, not passes
        ]
        passed, failed = apply_rules(claims(spark, rows))
        reasons = {r.claim_id: set(r._failed_rules) for r in failed.collect()}
        assert passed.count() == 1
        assert reasons["c2"] == {"service_before_claim"}
        assert reasons["c3"] == {"amount_not_negative"}
        assert reasons["c4"] == {"service_before_claim", "service_not_in_future"}
        assert failure_summary(failed)["service_before_claim"] == 2


class TestReconciliation:
    def test_identical_data_reconciles(self, spark):
        df = claims(spark, [GOOD])
        assert reconcile(df, df, "claim_id", "claim_amount").passed

    def test_same_count_different_values_is_caught(self, spark):
        src = claims(spark, [GOOD])
        tgt = claims(spark, [GOOD[:4] + (Decimal("12.00"),) + GOOD[5:]])
        result = reconcile(src, tgt, "claim_id", "claim_amount")
        assert not result.passed and result.problems == ["sum(claim_amount) 120.00 -> 12.00"]

    def test_duplicated_key_is_caught(self, spark):
        result = reconcile(
            claims(spark, [GOOD, GOOD]), claims(spark, [GOOD, GOOD]).limit(1), "claim_id", count_tolerance=0.6
        )
        assert result.passed  # within tolerance, keys match
        result = reconcile(claims(spark, [GOOD, GOOD]), claims(spark, [GOOD]), "claim_id")
        assert not result.passed


class TestSqlTests:
    @pytest.fixture(autouse=True)
    def view(self, spark):
        claims(
            spark, [GOOD, GOOD, ("c9", "m3", None, None, None, None), ("c8", "m3", None, None, None, "LOST")]
        ).createOrReplaceTempView("claims")

    def test_unique_finds_duplicate_key(self, spark):
        assert sql_tests.run(spark, "unique", table_name="claims", column_name="claim_id") == 1

    def test_not_null_finds_nulls(self, spark):
        assert sql_tests.run(spark, "not_null", table_name="claims", column_name="status") == 1

    def test_accepted_values_reports_nulls_and_unknowns(self, spark):
        failing = sql_tests.run(
            spark,
            "accepted_values",
            table_name="claims",
            column_name="status",
            accepted_values="'APPROVED','DENIED','PENDING'",
        )
        assert failing == 2  # NULL and 'LOST'

    def test_missing_parameter_raises(self):
        with pytest.raises(ValueError):
            sql_tests.render("unique", table_name="claims")
