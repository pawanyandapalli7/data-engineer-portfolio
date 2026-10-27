# Patterns

Smaller, focused pieces. Each folder says how it was verified, because "runs in
CI", "ran once locally" and "written from the docs" are different claims.

| Folder | What's in it | Verified by |
|---|---|---|
| [`sql/`](sql) | Window functions, dedup, spike detection that excludes the row being judged, deterministic ordering on ties | Every query runs on DuckDB against a fixture in CI, key results asserted |
| [`spark/`](spark) | Latest-per-key dedup with a tiebreaker; validation that quarantines with a reason instead of filtering | Spark tests in CI |
| [`python/`](python) | Pandas claims cleanup that keeps the latest version; schema check; paginated S3 listing | Tests in CI |
| [`aws-glue-lambda/`](aws-glue-lambda) | S3 event → Lambda → one Glue run per file (decoded key, no full-bucket reprocessing); Terraform for KMS-encrypted, versioned, TLS-only buckets | Lambda tests in CI; `terraform validate` in CI. Glue job not run |
| [`airflow/`](airflow) | Airflow 3 DAG: retries with backoff, execution timeouts, a freshness gate, failure callback, idempotent partition loads | DAG import + structure tests in CI; full `airflow dags test` run on Airflow 3.1.8 |
| [`snowflake/`](snowflake) | Per-workload warehouses, resource monitor, finding expensive and non-pruning queries, when clustering is worth it, streams + tasks incremental MERGE | Written against Snowflake docs; **not run against an account in this repo** |
| [`governance/`](governance) | PHI masking (SSN, date of birth) and row access by line of business, in both Snowflake and Unity Catalog; PHI access audit query | Written against vendor docs; **not run in this repo** |
