"""Schema contract checks for Spark DataFrames.

A contract is a dict of column -> expected Spark type string. Generic type
names match any parameterised form ("decimal" accepts "decimal(10,2)"), while a
fully specified type must match exactly ("decimal(12,2)" rejects
"decimal(10,2)"). That way a contract can be strict where precision matters
(money) and loose where it doesn't.
"""

from typing import Dict, List

from pyspark.sql import DataFrame


def _type_matches(expected: str, actual: str) -> bool:
    expected, actual = expected.lower().strip(), actual.lower().strip()
    if "(" in expected:
        return expected == actual
    return actual == expected or actual.startswith(expected + "(")


def validate_schema(df: DataFrame, expected_schema: Dict[str, str], allow_extra: bool = True) -> List[str]:
    """Return a list of human-readable contract violations (empty list = schema is valid)."""
    actual = {f.name: f.dataType.simpleString() for f in df.schema.fields}
    errors = []
    for col, dtype in expected_schema.items():
        if col not in actual:
            errors.append(f"missing column: {col}")
        elif not _type_matches(dtype, actual[col]):
            errors.append(f"type mismatch on {col}: expected {dtype}, got {actual[col]}")
    if not allow_extra:
        errors += [f"unexpected column: {c}" for c in actual if c not in expected_schema]
    return errors
