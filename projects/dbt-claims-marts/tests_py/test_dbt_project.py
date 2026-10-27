"""
End-to-end checks on the dbt project, run through the dbt CLI.

1. `dbt build` passes (models, snapshot, data tests, unit test).
2. A second build changes nothing: the incremental fact and the snapshot are idempotent.
3. When a patient moves, the snapshot closes the old version and opens a new one.
"""

import csv
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

PROJECT = Path(__file__).resolve().parents[1]
SAMPLE = PROJECT.parent / "azure-lakehouse" / "sample_data" / "synthea"


@pytest.fixture
def workdir(tmp_path):
    proj = tmp_path / "proj"
    shutil.copytree(PROJECT, proj, ignore=shutil.ignore_patterns("target", "logs", "tests_py", "dbt_packages"))
    data = tmp_path / "synthea"
    shutil.copytree(SAMPLE, data)
    return proj, data


DBT = str(Path(sys.executable).with_name("dbt"))


def dbt(proj: Path, data: Path, *args: str):
    """Run the dbt CLI in a subprocess so each build gets a fresh DuckDB connection."""
    cmd = [DBT, *args, "--project-dir", str(proj), "--profiles-dir", str(proj), "--vars", f"{{synthea_dir: '{data}'}}"]
    res = subprocess.run(cmd, cwd=proj, capture_output=True, text=True)
    assert res.returncode == 0, res.stdout[-3000:]


def query(proj: Path, sql: str):
    with duckdb.connect(str(proj / "target" / "claims.duckdb"), read_only=True) as con:
        return con.execute(sql).fetchall()


COUNTS = """
    select (select count(*) from main.fct_claim_lines), (select count(*) from main.dim_patient),
           (select count(*) from main.claims_quarantine), (select count(*) from main.claims_by_month)
"""


def test_build_is_green_and_idempotent(workdir):
    proj, data = workdir
    dbt(proj, data, "build")
    first = query(proj, COUNTS)
    fact, patients, quarantined, months = first[0]
    assert fact > 0 and months >= 18
    assert quarantined == 26  # 6 patients with unknown gender + 20 claims with a negative balance
    dbt(proj, data, "build")
    assert query(proj, COUNTS) == first


def test_snapshot_records_a_patient_move(workdir):
    proj, data = workdir
    dbt(proj, data, "build")

    path = data / "patients.csv"
    rows = list(csv.DictReader(path.open(newline="")))
    mover = next(r for r in rows if r["GENDER"] in ("M", "F"))
    mover["ZIP"] = "00000"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    dbt(proj, data, "build")
    versions = query(
        proj,
        f"select zip, is_current from main.dim_patient where patient_id = '{mover['Id']}' order by valid_from",
    )
    assert [v[1] for v in versions] == [False, True]
    assert versions[-1][0] == "00000"
