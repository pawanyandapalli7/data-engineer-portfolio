"""Source-vs-target reconciliation.

Row counts alone miss the classic failure where the right number of rows arrive
with the wrong values, so this also compares distinct keys and a sum over a
numeric column.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from pyspark.sql import DataFrame
from pyspark.sql import functions as F


@dataclass
class ReconciliationResult:
    passed: bool
    source: dict
    target: dict
    problems: List[str] = field(default_factory=list)


def _profile(df: DataFrame, key: str, amount_col: Optional[str]) -> dict:
    aggs = [F.count(F.lit(1)).alias("rows"), F.countDistinct(key).alias("distinct_keys")]
    if amount_col:
        aggs.append(F.coalesce(F.sum(amount_col), F.lit(0)).cast("decimal(38,2)").alias("amount_sum"))
    return df.agg(*aggs).collect()[0].asDict()


def reconcile(
    source: DataFrame, target: DataFrame, key: str, amount_col: Optional[str] = None, count_tolerance: float = 0.0
) -> ReconciliationResult:
    """Compare source and target. `count_tolerance` is a fraction (0.01 = 1%)."""
    s, t = _profile(source, key, amount_col), _profile(target, key, amount_col)
    problems = []
    if s["rows"] == 0:
        problems.append("source is empty")
    elif abs(s["rows"] - t["rows"]) / s["rows"] > count_tolerance:
        problems.append(f"row count {s['rows']} -> {t['rows']}")
    if s["distinct_keys"] != t["distinct_keys"]:
        problems.append(f"distinct {key} {s['distinct_keys']} -> {t['distinct_keys']}")
    if amount_col and s["amount_sum"] != t["amount_sum"]:
        problems.append(f"sum({amount_col}) {s['amount_sum']} -> {t['amount_sum']}")
    return ReconciliationResult(passed=not problems, source=s, target=t, problems=problems)
