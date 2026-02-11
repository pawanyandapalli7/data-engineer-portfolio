from pyspark.sql.functions import col

def validate_claims(df):
    """
    Purpose:
    Apply basic data quality checks to claims data.

    Ensures:
    - Records have a valid claim_id (business key)
    - Records have a non-null claim_amount (required for analytics)

    This step is commonly used early in ETL pipelines to
    prevent bad data from propagating downstream.
    """

    # Filter out records that violate core data quality rules
    return df.filter(
        col("claim_id").isNotNull() &
        col("claim_amount").isNotNull()
    )
