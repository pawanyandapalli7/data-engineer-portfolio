# Data quality checks for Spark pipelines

Four kinds of check, each returning evidence instead of silently filtering:

| Check | Module | Returns |
|---|---|---|
| Schema contract | `validations/schema_validation.py` | List of violations. `"decimal"` accepts any precision, `"decimal(12,2)"` must match exactly |
| Row rules | `validations/business_rules.py` | `(passed, failed)`; failed rows carry `_failed_rules`. A NULL counts as a failure |
| Reconciliation | `validations/reconciliation.py` | Compares row count, distinct keys **and** a sum, so "right count, wrong values" is caught |
| Generic SQL tests | `sql_tests/*.sql` + `validations/sql_tests.py` | `unique`, `not_null`, `accepted_values`; a test passes when the query returns no rows (the dbt convention) |

| | |
|---|---|
| **Tested** | 12 Spark tests in CI, including running each SQL test on Spark SQL |

## Example

```python
from validations.business_rules import apply_rules, failure_summary

passed, failed = apply_rules(claims_df)          # default rules: CLAIM_RULES
failed.write.mode("append").saveAsTable("dq.claims_quarantine")
print(failure_summary(failed))                   # {'service_before_claim': 12, 'amount_not_negative': 3}
```

Rules are SQL expressions in a dict, so adding one is a one-line change:

```python
CLAIM_RULES = {
    "claim_id_present":      "claim_id IS NOT NULL",
    "service_before_claim":  "service_date <= claim_date",   # a claim is filed on or after the service
    "amount_not_negative":   "claim_amount >= 0",
    "service_not_in_future": "service_date <= current_date()",
}
```

The [Azure lakehouse](../azure-lakehouse) uses the same idea, driven from YAML,
as the gate between Bronze and Silver.

## Run

```bash
pip install -r requirements-dev.txt   # needs Java 17
pytest -v tests
```
