"""
Business rule validations for healthcare datasets.
"""

from pyspark.sql.functions import col

def validate_claim_dates(df):
    """
    Ensures claim_date is not after service_date.
    """
    invalid_df = df.filter(col("claim_date") > col("service_date"))
    return invalid_df

def validate_positive_amount(df):
    """
    Ensures claim amounts are non-negative.
    """
    return df.filter(col("amount") < 0)
