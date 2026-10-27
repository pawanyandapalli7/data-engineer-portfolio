# Azure lakehouse: Bronze / Silver / Gold on Azure Databricks

Metadata-driven ingestion into Delta, data-quality gates with a quarantine,
SCD Type 2 history and dimensional Gold tables, governed by Unity Catalog and
deployed with Terraform and a Databricks Asset Bundle. It runs on **Synthea
synthetic patient data**, so there is no real PHI anywhere.

| | |
|---|---|
| **Tested** | 9 tests on local Spark in CI, including an end-to-end bronze → silver → gold run on the bundled sample |
| **Infra** | `terraform validate` in CI for both stages |
| **Deployed** | Not yet. Deploying is four `make` targets (see *Run it on Azure*) |

A personal reference build, not employer code.

```mermaid
flowchart LR
  S[Synthea CSVs<br/>landing container] -->|bronze job| B[(bronze<br/>as landed + lineage)]
  B -->|silver job<br/>type · dedup · checks| SV[(silver<br/>clean, one row per key)]
  B -.->|failed checks| Q[(silver.*_quarantine)]
  SV -->|gold job| G1[(gold.dim_patient<br/>SCD Type 2)]
  SV --> G2[(gold.fact_claim_lines<br/>liquid clustered)]
  G2 --> G3[(gold.claims_by_month)]
  subgraph Unity Catalog — lakehouse_demo
    B; SV; Q; G1; G2; G3
  end
```

## What's in here

| Path | What it does |
|---|---|
| `conf/sources.yml` | The metadata: files, keys, columns, types, renames and data-quality rules per source. Adding a source is a config change. |
| `src/lakehouse/transforms.py` | Pure PySpark functions: bronze landing with lineage, silver typing / de-dup (latest per key) / expectations, gold fact and monthly rollup. |
| `src/lakehouse/scd2.py` | SCD Type 2 for `dim_patient`: closes changed rows, opens new versions, keeps keys missing from a snapshot open, and is idempotent on re-runs. |
| `jobs/run.py` | The Databricks entrypoint. Only I/O: Delta appends, `MERGE` into silver, quarantine tables (appended per run), a liquid-clustered gold fact. Fails the job if more than 5% of a source fails checks. |
| `databricks.yml` | Databricks Asset Bundle: one job, three tasks (bronze → silver → gold) on a small job cluster, email on failure. |
| `infra/azure` | Terraform stage 1: resource group, ADLS Gen2 (HNS on, **account keys disabled**, TLS 1.2), Databricks Premium workspace, access connector with a managed identity, RBAC, and a monthly budget alert. |
| `infra/databricks` | Terraform stage 2: Unity Catalog storage credential, an external location per container, and a catalog whose bronze / silver / gold schemas each store data in their own container. |
| `tests/` | 9 tests on local Spark: lineage columns, loud failure on schema drift, typing and de-dup, quarantine reasons, replay safety, SCD2 behaviour (including two changes on the same day), gold math, and an end-to-end run on the sample data. |

Design choices worth calling out:

- **Names and SSNs never enter the lake.** Bronze keeps only the columns
  declared in `sources.yml`, so the name and SSN columns in the source file are
  dropped at the door. Birth date and 5-digit ZIP are kept because the demo
  needs them; both are HIPAA Safe Harbor identifiers, so a real build would
  generalise them (birth year, 3-digit ZIP) before Gold or mask them with a
  Unity Catalog column mask (see `patterns/governance`).
- **Bad rows are quarantined, not dropped.** Each one records which checks it
  failed (`_failed_checks`) and when, every run appends to the quarantine table,
  and a run fails loudly above a 5% bad-row ratio.
- **Re-runs are safe.** Bronze skips a batch it already loaded; silver keeps
  the latest row per key; SCD2 produces no change when the snapshot hasn't,
  and a second change on the same day replaces that day's version instead of
  producing a row whose `valid_to` is before its `valid_from`.
- **Liquid clustering on the fact table** instead of a date partition plus
  ZORDER: no small-file problem, and the clustering keys can change later
  without rewriting the table.
- **No secrets.** Unity Catalog reaches storage through the access connector's
  managed identity; storage keys are turned off entirely.

## Run the tests (no Azure needed)

```bash
pip install -r requirements-dev.txt   # needs Java 17+
make test
```

## Run it on Azure

Prerequisites: an Azure subscription where you can create role assignments
(Owner, or Contributor + User Access Administrator), Azure CLI (`az login`),
Terraform ≥ 1.6, Databricks CLI ≥ 0.218, and a Unity Catalog metastore in your
region (new Databricks accounts get one automatically).

```bash
cp infra/azure/example.tfvars infra/azure/terraform.tfvars   # set subscription_id and alert_email
make infra      # ~10 min: Azure resources, then Unity Catalog objects
make data       # generate the sample CSVs and upload them to the landing container
make deploy run # deploy the job and run bronze → silver → gold
```

Then, in the workspace's SQL editor:

```sql
SELECT * FROM lakehouse_demo.gold.claims_by_month ORDER BY month;
SELECT _failed_checks, count(*) FROM lakehouse_demo.silver.claims_quarantine GROUP BY 1;
SELECT * FROM lakehouse_demo.gold.dim_patient WHERE NOT is_current;   -- history after a second run
```

For realistic volume, swap the generated sample for the Synthea sample download
(synthetichealth.github.io/synthea-sample-data) — the CSV export has the same columns.

### Cost and teardown

A pipeline run uses a 2-node job cluster for a few minutes, which costs well
under a dollar. The workspace also keeps a NAT gateway for secure cluster
connectivity, which costs roughly a dollar a day while it exists, so tear down
when you're done. The budget alert emails you at 80% of `monthly_budget_usd`.

```bash
make destroy
```
