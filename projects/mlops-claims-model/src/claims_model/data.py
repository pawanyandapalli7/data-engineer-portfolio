"""Synthetic claims with a known denial signal, so model quality can be checked honestly.

No real data: every row is generated from a fixed seed. `shift=True` produces a
batch whose distribution has moved (larger amounts, more out-of-network claims,
slower submission), which is what the drift monitor should catch.
"""

import numpy as np
import pandas as pd

DIAGNOSIS_GROUPS = ["respiratory", "diabetes", "cardio", "musculoskeletal", "preventive"]
PLACES_OF_SERVICE = ["office", "outpatient", "inpatient", "emergency", "telehealth"]


def generate_claims(n: int = 5000, seed: int = 7, shift: bool = False) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    amount = rng.lognormal(mean=6.4 if shift else 6.0, sigma=0.9, size=n).round(2)
    out_of_network = rng.random(n) < (0.30 if shift else 0.12)
    prior_auth = rng.random(n) < 0.70
    days_to_submit = rng.gamma(shape=2.0, scale=14.0 if shift else 9.0, size=n).round().astype(int)
    diagnosis = rng.choice(DIAGNOSIS_GROUPS, size=n, p=[0.25, 0.2, 0.2, 0.2, 0.15])
    place = rng.choice(PLACES_OF_SERVICE, size=n, p=[0.4, 0.2, 0.1, 0.1, 0.2])
    member_age = rng.integers(18, 90, size=n)
    prior_denials = rng.poisson(0.4, size=n)

    # Ground truth: roughly the rules a payer's adjudication follows, plus noise.
    logit = (
        -2.6
        + 1.4 * out_of_network
        + 1.1 * (~prior_auth & np.isin(place, ["inpatient", "outpatient"]))
        + 0.9 * (days_to_submit > 60)
        + 0.45 * np.log1p(amount / 500)
        + 0.35 * prior_denials
        - 0.8 * (diagnosis == "preventive")
    )
    denied = rng.random(n) < 1 / (1 + np.exp(-logit))

    start = np.datetime64("2026-01-01")
    return pd.DataFrame(
        {
            "claim_id": [f"C{seed:02d}{i:06d}" for i in range(n)],
            "service_date": start + rng.integers(0, 270, size=n).astype("timedelta64[D]"),
            "claim_amount": amount,
            "out_of_network": out_of_network,
            "prior_auth": prior_auth,
            "days_to_submit": days_to_submit,
            "diagnosis_group": diagnosis,
            "place_of_service": place,
            "member_age": member_age,
            "prior_denials_12m": prior_denials,
            "denied": denied.astype(int),
        }
    )
