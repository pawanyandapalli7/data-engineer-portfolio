from typing import Set
import pandas as pd

REQUIRED_COLUMNS: Set[str] = {
    "claim_id",
    "member_id",
    "provider_id",
    "claim_amount",
    "claim_status",
    "claim_date",
}

def validate_schema(df: pd.DataFrame) -> None:
    """
    Validate that the input DataFrame contains all required columns.

    Raises:
        ValueError: if any required column is missing.
    """
    missing_columns = REQUIRED_COLUMNS - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {sorted(missing_columns)}"
        )
