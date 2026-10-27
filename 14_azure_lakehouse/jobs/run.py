"""Databricks entrypoint: python jobs/run.py --layer bronze|silver|gold ...

Reads and writes Delta tables in Unity Catalog. All business logic lives in
src/lakehouse (pure functions, unit-tested); this file only does I/O.
"""
import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent if "__file__" in globals() else Path(sys.argv[0]).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from delta.tables import DeltaTable  # noqa: E402  (provided by Databricks Runtime)
from pyspark.sql import SparkSession  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

from lakehouse.config import load_sources  # noqa: E402
from lakehouse.scd2 import scd2_merge  # noqa: E402
from lakehouse.transforms import claims_by_month, fact_claim_lines, to_bronze, to_silver  # noqa: E402


def table_exists(spark, name: str) -> bool:
    return spark.catalog.tableExists(name)


def run_bronze(spark, args, sources):
    batch_id = args.batch_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    for s in sources.values():
        target = f"{args.catalog}.bronze.{s.name}"
        if table_exists(spark, target) and spark.table(target).where(F.col("_batch_id") == batch_id).limit(1).count():
            print(f"[bronze] {s.name}: batch {batch_id} already loaded, skipping (idempotent re-run)")
            continue
        raw = spark.read.option("header", True).option("inferSchema", False).csv(f"{args.landing.rstrip('/')}/{s.file}")
        out = to_bronze(raw, s, batch_id)
        out.write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable(target)
        print(f"[bronze] {s.name}: appended {out.count()} rows as batch {batch_id}")


def run_silver(spark, args, sources):
    for s in sources.values():
        bronze = spark.table(f"{args.catalog}.bronze.{s.name}")
        passed, failed = to_silver(bronze, s)
        target, quarantine = f"{args.catalog}.silver.{s.name}", f"{args.catalog}.silver.{s.name}_quarantine"
        passed = passed.drop("_source_file")
        if table_exists(spark, target):
            cond = " AND ".join(f"t.{k} = s.{k}" for k in s.silver_key)
            (DeltaTable.forName(spark, target).alias("t").merge(passed.alias("s"), cond)
                .whenMatchedUpdateAll(condition="s._ingested_at > t._ingested_at").whenNotMatchedInsertAll().execute())
        else:
            passed.write.format("delta").saveAsTable(target)
        n_bad, n_all = failed.count(), bronze.select(*s.key).distinct().count()
        failed.write.format("delta").mode("overwrite").saveAsTable(quarantine)
        ratio = n_bad / max(n_all, 1)
        print(f"[silver] {s.name}: {n_all - n_bad} passed, {n_bad} quarantined ({ratio:.2%})")
        if ratio > args.max_bad_ratio:
            raise RuntimeError(f"{s.name}: {ratio:.2%} of rows failed checks (limit {args.max_bad_ratio:.0%}) — see {quarantine}")


def run_gold(spark, args, sources):
    c = args.catalog
    patients = spark.table(f"{c}.silver.patients")
    dim_name = f"{c}.gold.dim_patient"
    current = spark.table(dim_name) if table_exists(spark, dim_name) else None
    dim = scd2_merge(current, patients, key="patient_id", tracked=["gender", "state", "county", "zip", "death_date"],
                     as_of=args.as_of or date.today().isoformat())
    dim.localCheckpoint().write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(dim_name)

    fact = fact_claim_lines(spark.table(f"{c}.silver.claims"), spark.table(f"{c}.silver.claim_transactions"))
    fact.write.format("delta").mode("overwrite").option("overwriteSchema", "true").partitionBy("service_date").saveAsTable(f"{c}.gold.fact_claim_lines")
    spark.sql(f"OPTIMIZE {c}.gold.fact_claim_lines ZORDER BY (patient_id, claim_id)")
    claims_by_month(fact).write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{c}.gold.claims_by_month")
    print(f"[gold] dim_patient, fact_claim_lines, claims_by_month refreshed in {c}.gold")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--layer", choices=["bronze", "silver", "gold"], required=True)
    p.add_argument("--catalog", required=True)
    p.add_argument("--landing", help="folder holding the Synthea CSVs, e.g. abfss://landing@<account>.dfs.core.windows.net/synthea")
    p.add_argument("--conf", default=str(HERE.parent / "conf" / "sources.yml"))
    p.add_argument("--batch-id", default=None)
    p.add_argument("--as-of", default=None, help="SCD2 effective date (YYYY-MM-DD), defaults to today")
    p.add_argument("--max-bad-ratio", type=float, default=0.05)
    args = p.parse_args(argv)
    spark = SparkSession.builder.getOrCreate()
    sources = load_sources(args.conf)
    {"bronze": run_bronze, "silver": run_silver, "gold": run_gold}[args.layer](spark, args, sources)


if __name__ == "__main__":
    main()
