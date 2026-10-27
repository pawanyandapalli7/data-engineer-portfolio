"""Row-level business rules for claims data.

Each rule is a SQL boolean expression that must be TRUE for a valid row. A NULL
result counts as a failure, so a missing date can't slip through a date rule.
`apply_rules` tags every row with the names of the rules it broke instead of
dropping it, so bad rows can be quarantined and explained.
"""

from typing import Dict, Tuple

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

CLAIM_RULES: Dict[str, str] = {
    "claim_id_present": "claim_id IS NOT NULL",
    # A claim is submitted on or after the date the service was delivered.
    "service_before_claim": "service_date <= claim_date",
    "amount_not_negative": "claim_amount >= 0",
    "service_not_in_future": "service_date <= current_date()",
}


def apply_rules(df: DataFrame, rules: Dict[str, str] = CLAIM_RULES) -> Tuple[DataFrame, DataFrame]:
    """Split df into (passed, failed). Failed rows carry `_failed_rules: array<string>`."""
    checks = [F.when(~F.coalesce(F.expr(expr), F.lit(False)), F.lit(name)) for name, expr in rules.items()]
    tagged = df.withColumn("_failed_rules", F.filter(F.array(*checks), lambda x: x.isNotNull()))
    passed = tagged.where(F.size("_failed_rules") == 0).drop("_failed_rules")
    failed = tagged.where(F.size("_failed_rules") > 0)
    return passed, failed


def failure_summary(failed: DataFrame) -> Dict[str, int]:
    """Count failures per rule, e.g. {'amount_not_negative': 3}."""
    rows = failed.select(F.explode("_failed_rules").alias("rule")).groupBy("rule").count().collect()
    return {r["rule"]: r["count"] for r in rows}
