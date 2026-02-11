from pyspark.sql import Window
from pyspark.sql.functions import row_number, col

def deduplicate_claims(df):
    """
    Purpose:
    Deduplicate records by retaining the latest version per claim_id.
    
    This pattern is commonly used in:
    - CDC pipelines (handling multiple updates per key)
    - Snapshot generation
    - Late-arriving data handling
    """

    # Define window specification:
    # Partition by business key (claim_id) and order by update timestamp
    # so the most recent record appears first
    window_spec = (
        Window
        .partitionBy("claim_id")
        .orderBy(col("updated_at").desc())
    )

    # Assign row numbers within each partition and keep only the latest record
    return (
        df
        .withColumn("rn", row_number().over(window_spec))
        .filter(col("rn") == 1)
        .drop("rn")
    )
