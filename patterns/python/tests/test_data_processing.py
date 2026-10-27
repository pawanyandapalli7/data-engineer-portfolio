import pandas as pd
import pytest

from data_processing.clean_claims import clean_claims
from data_processing.validate_schema import validate_schema


def test_clean_claims_removes_null_and_duplicates():
    df = pd.DataFrame(
        {
            "claim_id": [1, None, 1, 2],
            "member_id": [10, 20, 10, 30],
            "claim_date": ["2024-01-01", "2024-01-02", "2024-01-01", "2024-01-03"],
        }
    )
    result = clean_claims(df)
    assert result["claim_id"].isna().sum() == 0
    assert sorted(result["claim_id"]) == [1, 2]


def test_clean_claims_keeps_latest_version():
    df = pd.DataFrame(
        {
            "claim_id": ["c1", "c1", "c1"],
            "status": ["paid", "open", "approved"],
            "claim_date": ["2024-01-01"] * 3,
            "updated_at": ["2024-01-03", "2024-01-01", "2024-01-02"],
        }
    )
    assert clean_claims(df).loc[0, "status"] == "paid"


def test_bad_dates_become_nat_instead_of_failing():
    df = pd.DataFrame({"claim_id": ["c1"], "claim_date": ["not-a-date"]})
    assert pd.isna(clean_claims(df).loc[0, "claim_date"])


def test_validate_schema_raises_error_on_missing_columns():
    with pytest.raises(ValueError, match="provider_id"):
        validate_schema(pd.DataFrame({"claim_id": [1], "member_id": [10]}))


def test_list_objects_follows_pagination():
    from unittest.mock import MagicMock, patch

    from utilities import s3_helpers

    client = MagicMock()
    client.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "a"}, {"Key": "b"}]},
        {"Contents": [{"Key": "c"}]},
        {},  # an empty page has no Contents key
    ]
    with patch.object(s3_helpers, "get_s3_client", return_value=client):
        assert s3_helpers.list_objects("bucket", "prefix/") == ["a", "b", "c"]
