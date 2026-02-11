import pandas as pd

def clean_claims(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean raw claims data by:
    - Removing null claim IDs
    - Converting claim_date to datetime
    - Deduplicating records by claim_id
    """
    df = df[df["claim_id"].notna()]
    df["claim_date"] = pd.to_datetime(df["claim_date"])
    df = df.drop_duplicates(subset=["claim_id"])
    return df
