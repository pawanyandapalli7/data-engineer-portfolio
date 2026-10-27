"""Slowly Changing Dimension Type 2 for dim_patient, as a pure function.

Given the current dimension and an incoming snapshot, return the complete new
dimension: unchanged rows untouched, changed rows closed out and re-opened as a
new version, new keys inserted, and keys missing from the snapshot left open
(a gap in a snapshot is not a deletion). The job overwrites the Delta table with
the result, so the logic is identical on a laptop and on Databricks.
"""
from typing import List, Optional

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

HIGH_DATE = "9999-12-31"


def _hash(cols: List[str]):
    return F.sha2(F.concat_ws("||", *[F.coalesce(F.col(c).cast("string"), F.lit("<null>")) for c in cols]), 256)


def scd2_merge(current: Optional[DataFrame], incoming: DataFrame, key: str, tracked: List[str], as_of: str) -> DataFrame:
    asof = F.lit(as_of).cast("date")
    high = F.lit(HIGH_DATE).cast("date")
    cols = [key, *tracked, "valid_from", "valid_to", "is_current"]
    inc = incoming.select(key, *tracked).dropDuplicates([key]).withColumn("_h", _hash(tracked))

    if current is None or current.limit(1).count() == 0:
        return inc.select(key, *tracked, asof.alias("valid_from"), high.alias("valid_to"), F.lit(True).alias("is_current"))

    history = current.where(~F.col("is_current")).select(*cols)
    open_ = current.where(F.col("is_current")).withColumn("_h", _hash(tracked))
    j = open_.alias("o").join(inc.alias("i"), key, "full_outer")
    o = lambda c: F.col(f"o.{c}")
    i = lambda c: F.col(f"i.{c}")

    same = j.where(o("_h") == i("_h")).select(key, *[o(c).alias(c) for c in tracked], o("valid_from").alias("valid_from"),
                                              o("valid_to").alias("valid_to"), o("is_current").alias("is_current"))
    changed = j.where(o("_h").isNotNull() & i("_h").isNotNull() & (o("_h") != i("_h")))
    closed = changed.select(key, *[o(c).alias(c) for c in tracked], o("valid_from").alias("valid_from"),
                            F.date_sub(asof, 1).alias("valid_to"), F.lit(False).alias("is_current"))
    reopened = changed.select(key, *[i(c).alias(c) for c in tracked], asof.alias("valid_from"), high.alias("valid_to"),
                              F.lit(True).alias("is_current"))
    inserted = j.where(o("_h").isNull()).select(key, *[i(c).alias(c) for c in tracked], asof.alias("valid_from"),
                                                high.alias("valid_to"), F.lit(True).alias("is_current"))
    kept = j.where(i("_h").isNull()).select(key, *[o(c).alias(c) for c in tracked], o("valid_from").alias("valid_from"),
                                            o("valid_to").alias("valid_to"), o("is_current").alias("is_current"))
    out = history
    for part in (same, closed, reopened, inserted, kept):
        out = out.unionByName(part.select(*cols))
    return out
