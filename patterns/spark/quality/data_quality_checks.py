from typing import Tuple

from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def validate_claims(df: DataFrame) -> Tuple[DataFrame, DataFrame]:
    """
    Split claims into (valid, rejected) instead of silently filtering.

    Rejected rows keep a `_reject_reason` so they can be written to a quarantine
    table and counted. A pipeline that only filters loses the evidence.
    """
    reason = F.when(F.col("claim_id").isNull(), "missing claim_id").when(
        F.col("claim_amount").isNull(), "missing claim_amount"
    )
    tagged = df.withColumn("_reject_reason", reason)
    return (
        tagged.where(F.col("_reject_reason").isNull()).drop("_reject_reason"),
        tagged.where(F.col("_reject_reason").isNotNull()),
    )
