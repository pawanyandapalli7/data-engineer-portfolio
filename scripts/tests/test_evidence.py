import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import evidence  # noqa: E402

JUNIT = (
    '<?xml version="1.0"?><testsuites>'
    '<testsuite name="pytest" tests="{t}" failures="{f}" errors="0" skipped="0"/></testsuites>'
)


def test_counts_junit_and_dbt_by_project(tmp_path):
    (tmp_path / "junit-cdc-pipeline.xml").write_text(JUNIT.format(t=10, f=0))
    (tmp_path / "junit-patterns-sql.xml").write_text(JUNIT.format(t=6, f=0))
    (tmp_path / "junit-patterns-spark.xml").write_text(JUNIT.format(t=2, f=1))
    (tmp_path / "dbt-dbt-claims-marts.json").write_text(
        json.dumps(
            {
                "results": [
                    {"unique_id": "test.claims_marts.a", "status": "pass"},
                    {"unique_id": "unit_test.claims_marts.b", "status": "pass"},
                    {"unique_id": "model.claims_marts.c", "status": "success"},  # models aren't tests
                ]
            }
        )
    )
    ev = evidence.build(tmp_path, commit="abc123")
    by = {p["key"]: p for p in ev["projects"]}
    assert by["cdc-pipeline"]["tests_passed"] == 10 and by["cdc-pipeline"]["status"] == "passing"
    assert by["patterns"]["tests_passed"] == 7 and by["patterns"]["status"] == "failing"
    assert by["dbt-claims-marts"]["tests_passed"] == 2
    assert by["rag-pipeline"]["status"] == "no-data"
    assert ev["totals"] == {"tests_passed": 19, "tests_failed": 1, "projects": len(evidence.PROJECTS), "deployed": 0}


def test_badge_shows_failures_first():
    assert evidence.badge("tests", 10, 0)["message"] == "10 passing"
    assert evidence.badge("tests", 10, 2)["message"] == "2 failing"
