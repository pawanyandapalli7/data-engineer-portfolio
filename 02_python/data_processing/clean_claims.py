import pandas as pd

def clean_claims(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply deterministic data quality rules to raw claims data.

    - Remove records with null claim IDs
    - Normalize claim_date to datetime
    - Deduplicate records by claim_id

    This logic is commonly applied before Spark/Glue ingestion
    or during local validation.
    """
    df = df.loc[df["claim_id"].notna()].copy()

    df["claim_date"] = pd.to_datetime(
        df["claim_date"],
        errors="coerce"
    )

    df = df.drop_duplicates(subset=["claim_id"])

    return df
