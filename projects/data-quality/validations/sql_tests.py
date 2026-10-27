"""Render the generic SQL tests in ../sql_tests and run them on Spark.

A test passes when its query returns zero rows, the same convention dbt uses.
"""

from pathlib import Path

SQL_DIR = Path(__file__).resolve().parents[1] / "sql_tests"


def render(test_name: str, **params: str) -> str:
    lines = (SQL_DIR / f"{test_name}.sql").read_text().splitlines()
    sql = "\n".join(line for line in lines if not line.lstrip().startswith("--")).strip().rstrip(";")
    for key, value in params.items():
        sql = sql.replace("{{ " + key + " }}", value)
    if "{{" in sql:
        raise ValueError(f"{test_name}: missing parameters in {sql!r}")
    return sql


def run(spark, test_name: str, **params: str) -> int:
    """Return the number of failing rows the test query produces."""
    return spark.sql(render(test_name, **params)).count()
