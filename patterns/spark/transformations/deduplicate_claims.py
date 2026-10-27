from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F


def deduplicate_claims(
    df: DataFrame, key: str = "claim_id", order_col: str = "updated_at", tiebreak_col: str = None
) -> DataFrame:
    """
    Keep the latest row per key.

    Without a tiebreaker, two rows with the same `updated_at` make the result
    depend on partition order, so pass a unique, increasing column (an ingest
    sequence or file offset) when one exists.
    """
    order = [F.col(order_col).desc_nulls_last()]
    if tiebreak_col:
        order.append(F.col(tiebreak_col).desc_nulls_last())
    w = Window.partitionBy(key).orderBy(*order)
    return df.withColumn("_rn", F.row_number().over(w)).where(F.col("_rn") == 1).drop("_rn")
