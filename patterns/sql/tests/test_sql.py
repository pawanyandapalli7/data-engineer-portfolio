"""Every query in this folder runs on DuckDB against a small fixture, and key results are asserted."""

from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")
HERE = Path(__file__).resolve().parents[1]


def statements(name):
    text = "\n".join(line for line in (HERE / name).read_text().splitlines() if not line.strip().startswith("--"))
    return [s.strip() for s in text.split(";") if s.strip()]


@pytest.fixture
def db():
    con = duckdb.connect()
    con.execute((HERE / "schema.sql").read_text())
    con.execute((HERE / "tests" / "sample_data.sql").read_text())
    return con


@pytest.mark.parametrize("name", ["analytics_queries.sql", "window_functions.sql", "interview_cases.sql"])
def test_every_query_runs(db, name):
    for sql in statements(name):
        db.execute(sql).fetchall()


def test_latest_version_per_claim(db):
    rows = db.execute(statements("window_functions.sql")[0]).fetchall()
    assert [(r[0], float(r[2])) for r in rows][0] == (1, 120.0) and len(rows) == 5


def test_interview_cases(db):
    went_up, always_up, spikes = (db.execute(s).fetchall() for s in statements("interview_cases.sql"))
    assert went_up == [(100,)]
    assert always_up == [(100,)]  # 100 -> 120 -> 150 -> 900; member 200 went down
    assert [r[1] for r in spikes] == [3]


def test_approval_rate(db):
    assert float(db.execute(statements("analytics_queries.sql")[2]).fetchone()[0]) == pytest.approx(66.67)
