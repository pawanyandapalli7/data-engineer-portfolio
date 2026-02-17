"""
Schema validation utilities for data pipelines.
Designed for Spark / Glue-style ingestion jobs.
"""

def validate_schema(df, expected_schema: dict):
    """
    Validate dataframe schema against expected schema.

    expected_schema = {
        "claim_id": "string",
        "member_id": "string",
        "claim_date": "date",
        "amount": "decimal"
    }
    """
    errors = []

    actual_fields = {field.name: field.dataType.simpleString()
                     for field in df.schema.fields}

    for col, dtype in expected_schema.items():
        if col not in actual_fields:
            errors.append(f"Missing column: {col}")
        elif actual_fields[col] != dtype:
            errors.append(
                f"Column {col} type mismatch: "
                f"expected={dtype}, actual={actual_fields[col]}"
            )

    return errors
