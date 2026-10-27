"""
Turn CI test results into evidence.json (and shields.io badge files) for GitHub Pages.

Each CI job uploads a JUnit XML named junit-<key>.xml; dbt also uploads its
run_results.json as dbt-<key>.json. This script counts passed/failed/skipped per
project and writes:

    out/evidence.json          per-project results + totals, for the website
    out/badges/tests.json      shields.io endpoint: "tests | 160 passing"
    out/badges/<key>.json      one badge per project

    python scripts/evidence.py --results results/ --out site/ --commit $GITHUB_SHA
"""

import argparse
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

REPO = "https://github.com/pawanyandapalli7/data-engineer-portfolio"
SITE = "https://www.pawanyandapalli.com/work"

PROJECTS = {
    "azure-lakehouse": dict(
        title="Azure lakehouse, Bronze to Gold",
        path="projects/azure-lakehouse",
        case_study=f"{SITE}/azure-lakehouse",
        deployed=False,
    ),
    "mlops-claims-model": dict(
        title="MLOps: claims denial model", path="projects/mlops-claims-model", case_study=None, deployed=False
    ),
    "dbt-claims-marts": dict(
        title="dbt claims marts", path="projects/dbt-claims-marts", case_study=None, deployed=False
    ),
    "cdc-pipeline": dict(title="CDC snapshot job", path="projects/cdc-pipeline", case_study=None, deployed=False),
    "data-quality": dict(title="Data quality checks", path="projects/data-quality", case_study=None, deployed=False),
    "feature-store": dict(
        title="Real-time feature store",
        path="projects/feature-store",
        case_study=f"{SITE}/feature-store",
        deployed=False,
    ),
    "rag-pipeline": dict(
        title="RAG pipeline", path="projects/rag-pipeline", case_study=f"{SITE}/rag-pipeline", deployed=False
    ),
    "llm-eval-harness": dict(
        title="LLM evaluation harness", path="projects/llm-eval-harness", case_study=f"{SITE}/llm-eval", deployed=False
    ),
    "patterns": dict(title="Patterns", path="patterns", case_study=None, deployed=False),
}


def project_key(name: str) -> str:
    """'junit-patterns-sql' -> 'patterns'; 'dbt-dbt-claims-marts' -> 'dbt-claims-marts'."""
    stem = name.split("-", 1)[1]
    return "patterns" if stem.startswith("patterns") else stem


def count_junit(path: Path) -> dict:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    c = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for s in suites:
        for k in c:
            c[k] += int(s.get(k, 0))
    return c


def count_dbt(path: Path) -> dict:
    """dbt run_results.json: count tests and unit tests (data tests + unit tests)."""
    results = json.loads(path.read_text())["results"]
    tests = [r for r in results if r["unique_id"].split(".")[0] in ("test", "unit_test")]
    return {
        "tests": len(tests),
        "failures": sum(r["status"] == "fail" for r in tests),
        "errors": sum(r["status"] == "error" for r in tests),
        "skipped": sum(r["status"] == "skipped" for r in tests),
    }


def _status(t: dict) -> str:
    if not t["tests"]:
        return "no-data"
    return "failing" if t["failures"] or t["errors"] else "passing"


def build(results_dir: Path, commit: str = "", run_url: str = "") -> dict:
    totals = {k: {"tests": 0, "failures": 0, "errors": 0, "skipped": 0} for k in PROJECTS}
    for f in sorted(results_dir.rglob("*")):
        if f.suffix == ".xml" and f.name.startswith("junit-"):
            counts = count_junit(f)
        elif f.suffix == ".json" and f.name.startswith("dbt-"):
            counts = count_dbt(f)
        else:
            continue
        key = project_key(f.stem)
        if key not in totals:
            raise SystemExit(f"{f.name}: unknown project key {key!r}")
        for k, v in counts.items():
            totals[key][k] += v

    projects = []
    for key, meta in PROJECTS.items():
        t = totals[key]
        passed = t["tests"] - t["failures"] - t["errors"] - t["skipped"]
        projects.append(
            {
                "key": key,
                **meta,
                "code": f"{REPO}/tree/main/{meta['path']}",
                "tests_passed": passed,
                "tests_failed": t["failures"] + t["errors"],
                "tests_skipped": t["skipped"],
                "status": _status(t),
            }
        )
    passed = sum(p["tests_passed"] for p in projects)
    failed = sum(p["tests_failed"] for p in projects)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": commit,
        "ci_run": run_url,
        "repo": REPO,
        "totals": {
            "tests_passed": passed,
            "tests_failed": failed,
            "projects": len(projects),
            "deployed": sum(p["deployed"] for p in projects),
        },
        "projects": projects,
    }


def badge(label: str, passed: int, failed: int) -> dict:
    ok = failed == 0 and passed > 0
    return {
        "schemaVersion": 1,
        "label": label,
        "message": f"{passed} passing" if ok else f"{failed} failing",
        "color": "17332A" if ok else "B4472F",
        "labelColor": "F4EFE2" if ok else "555",
    }


CSS = (
    "body{font:16px/1.5 system-ui,sans-serif;max-width:52rem;margin:2rem auto;padding:0 1rem;"
    "color:#17332A;background:#F4EFE2}"
    "table{border-collapse:collapse;width:100%}"
    "td,th{text-align:left;padding:.4rem .6rem;border-bottom:1px solid #17332A33}a{color:inherit}"
    "@media (prefers-color-scheme:dark){body{color:#EFE8D6;background:#0E1F18}td,th{border-color:#EFE8D633}}"
)


def render_html(ev: dict) -> str:
    """A plain, dependency-free page so the evidence is readable without the website."""
    rows = "".join(
        f"<tr><td><a href='{p['code']}'>{p['title']}</a></td><td>{p['tests_passed']}</td>"
        f"<td>{p['tests_failed']}</td><td>{p['status']}</td><td>{'yes' if p['deployed'] else 'not yet'}</td></tr>"
        for p in ev["projects"]
    )
    t = ev["totals"]
    run = f" (<a href='{ev['ci_run']}'>run</a>)" if ev["ci_run"] else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>CI evidence</title>
<style>{CSS}</style>
</head><body><h1>CI evidence</h1>
<p>{t["tests_passed"]} tests passing, {t["tests_failed"]} failing, across {t["projects"]} projects.
Generated {ev["generated_at"]} from commit <code>{ev["commit"][:7]}</code>{run}.</p>
<table><tr><th>Project</th><th>Passing</th><th>Failing</th><th>Status</th><th>Deployed</th></tr>{rows}</table>
<p><a href="evidence.json">evidence.json</a> &middot; <a href="{ev["repo"]}">repository</a></p></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--commit", default="")
    ap.add_argument("--run-url", default="")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any test failed")
    a = ap.parse_args()
    ev = build(a.results, a.commit, a.run_url)
    (a.out / "badges").mkdir(parents=True, exist_ok=True)
    (a.out / "evidence.json").write_text(json.dumps(ev, indent=2))
    (a.out / "badges" / "tests.json").write_text(
        json.dumps(badge("tests", ev["totals"]["tests_passed"], ev["totals"]["tests_failed"]))
    )
    for p in ev["projects"]:
        (a.out / "badges" / f"{p['key']}.json").write_text(
            json.dumps(badge("tests", p["tests_passed"], p["tests_failed"]))
        )
    (a.out / "index.html").write_text(render_html(ev))
    print(json.dumps(ev["totals"]))
    if a.strict and ev["totals"]["tests_failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
