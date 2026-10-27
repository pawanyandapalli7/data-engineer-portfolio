import pandas as pd


def clean_claims(df: pd.DataFrame) -> pd.DataFrame:
    """
    Deterministic cleanup for raw claims, e.g. before a local validation run.

    - drops rows without a claim_id
    - parses claim_date (unparseable values become NaT instead of failing the batch)
    - keeps one row per claim_id: the most recent by updated_at when that column
      exists, otherwise the last occurrence in file order
    """
    df = df.loc[df["claim_id"].notna()].copy()
    df["claim_date"] = pd.to_datetime(df["claim_date"], errors="coerce")
    if "updated_at" in df.columns:
        df["updated_at"] = pd.to_datetime(df["updated_at"], errors="coerce")
        df = df.sort_values("updated_at", kind="stable", na_position="first")
    return df.drop_duplicates(subset=["claim_id"], keep="last").reset_index(drop=True)
