import pandas as pd
import pytest

from data_processing.clean_claims import clean_claims
from data_processing.validate_schema import validate_schema


def test_clean_claims_removes_null_and_duplicates():
    df = pd.DataFrame({
        "claim_id": [1, None, 1, 2],
        "member_id": [10, 20, 10, 30],
        "claim_date": ["2024-01-01", "2024-01-02", "2024-01-01", "2024-01-03"]
    })

    result = clean_claims(df)

    assert result["claim_id"].isna().sum() == 0
    assert result["claim_id"].nunique() == 2


def test_validate_schema_raises_error_on_missing_columns():
    df = pd.DataFrame({
        "claim_id": [1],
        "member_id": [10]
    })

    with pytest.raises(ValueError):
        validate_schema(df)
