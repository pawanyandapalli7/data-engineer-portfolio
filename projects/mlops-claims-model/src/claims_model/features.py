"""One feature function for training and serving, so the two can't drift apart.

The serving API calls `build_features` on the raw request exactly as training
does; there is no second implementation to keep in sync.
"""

import numpy as np
import pandas as pd

NUMERIC = ["log_amount", "days_to_submit", "member_age", "prior_denials_12m"]
BOOLEAN = ["out_of_network", "missing_prior_auth_facility", "late_submission"]
CATEGORICAL = ["diagnosis_group", "place_of_service"]
FEATURES = NUMERIC + BOOLEAN + CATEGORICAL
TARGET = "denied"

# Columns that would leak the outcome or identify a row; never features.
EXCLUDED = {"claim_id", "service_date", TARGET}

RAW_REQUIRED = [
    "claim_amount",
    "out_of_network",
    "prior_auth",
    "days_to_submit",
    "diagnosis_group",
    "place_of_service",
    "member_age",
    "prior_denials_12m",
]


def build_features(raw: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in RAW_REQUIRED if c not in raw.columns]
    if missing:
        raise ValueError(f"missing raw columns: {missing}")
    f = pd.DataFrame(index=raw.index)
    f["log_amount"] = np.log1p(raw["claim_amount"].astype(float).clip(lower=0))
    f["days_to_submit"] = raw["days_to_submit"].astype(float)
    f["member_age"] = raw["member_age"].astype(float)
    f["prior_denials_12m"] = raw["prior_denials_12m"].astype(float)
    f["out_of_network"] = raw["out_of_network"].astype(bool).astype(int)
    facility = raw["place_of_service"].isin(["inpatient", "outpatient"])
    f["missing_prior_auth_facility"] = (~raw["prior_auth"].astype(bool) & facility).astype(int)
    f["late_submission"] = (raw["days_to_submit"] > 60).astype(int)
    f["diagnosis_group"] = raw["diagnosis_group"].astype(str)
    f["place_of_service"] = raw["place_of_service"].astype(str)
    return f[FEATURES]
