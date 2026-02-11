def write_partitioned(df, path):
    """
    Write a DataFrame to S3 as Parquet files partitioned by claim_date.

    Why partitioning matters:
    - Enables partition pruning for faster query performance
    - Reduces data scanned by engines like Athena, Spark, Redshift Spectrum
    - Common best practice for analytics-ready data lakes
    """

    # Write data in overwrite mode to refresh the target dataset
    # Partitioning by claim_date creates directory-level partitions
    # (e.g., claim_date=2024-01-01/)
    (
        df
        .write
        .mode("overwrite")
        .partitionBy("claim_date")
        .parquet(path)
    )
