from typing import Tuple

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

from .config import Source


# ── Bronze: land the file as-is, plus lineage columns ─────────────────────
def to_bronze(raw: DataFrame, source: Source, batch_id: str) -> DataFrame:
    missing = [c for c in source.columns if c not in raw.columns]
    if missing:
        raise ValueError(f"{source.name}: source file is missing columns {missing}")
    return (
        raw.select(*source.columns)
        .withColumn("_source_file", F.lit(source.file))
        .withColumn("_batch_id", F.lit(batch_id))
        .withColumn("_ingested_at", F.current_timestamp())
    )


# ── Silver: type, rename, de-duplicate, validate ──────────────────────────
def standardize(bronze: DataFrame, source: Source) -> DataFrame:
    df = bronze
    for c, typ in df.dtypes:
        if typ == "string":
            df = df.withColumn(c, F.when(F.trim(F.col(c)) == "", None).otherwise(F.trim(F.col(c))))
    for col, typ in source.types.items():
        df = df.withColumn(col, F.col(col).cast(typ))
    for old, new in source.rename.items():
        df = df.withColumnRenamed(old, new)
    return df


def latest_per_key(df: DataFrame, key) -> DataFrame:
    """Keep the most recently ingested row per business key, so replays are safe."""
    w = Window.partitionBy(*key).orderBy(F.col("_ingested_at").desc(), F.col("_batch_id").desc())
    return df.withColumn("_rn", F.row_number().over(w)).where("_rn = 1").drop("_rn")


def apply_expectations(df: DataFrame, source: Source) -> Tuple[DataFrame, DataFrame]:
    """Split rows into (passed, quarantined). Quarantined rows list the checks they failed."""
    checks = [F.when(~F.coalesce(F.expr(e["rule"]), F.lit(False)), F.lit(e["name"])) for e in source.expectations]
    failed_list = F.filter(F.array(*checks), lambda x: x.isNotNull()) if checks else F.array().cast("array<string>")
    flagged = df.withColumn("_failed_checks", failed_list)
    passed = flagged.where(F.size("_failed_checks") == 0).drop("_failed_checks")
    failed = flagged.where(F.size("_failed_checks") > 0)
    return passed, failed


def to_silver(bronze: DataFrame, source: Source) -> Tuple[DataFrame, DataFrame]:
    std = standardize(bronze, source)
    dedup = latest_per_key(std, source.silver_key)
    return apply_expectations(dedup, source)


# ── Gold: dimensional models ───────────────────────────────────────────────
def fact_claim_lines(claims: DataFrame, txns: DataFrame) -> DataFrame:
    """One row per claim transaction, enriched with claim attributes."""
    c = claims.select("claim_id", "provider_id", "payer_id", "service_ts", "primary_diagnosis")
    return txns.join(c, "claim_id", "left").select(
        "transaction_id",
        "claim_id",
        "patient_id",
        "provider_id",
        "payer_id",
        F.to_date("service_ts").alias("service_date"),
        "txn_type",
        "amount",
        "procedure_code",
        "primary_diagnosis",
    )


def claims_by_month(fact: DataFrame) -> DataFrame:
    return (
        fact.withColumn("month", F.date_trunc("month", "service_date").cast("date"))
        .groupBy("month")
        .agg(
            F.countDistinct("claim_id").alias("claims"),
            F.sum(F.when(F.col("txn_type") == "CHARGE", F.col("amount"))).alias("charged"),
            F.sum(F.when(F.col("txn_type") == "PAYMENT", F.col("amount"))).alias("paid"),
        )
        .orderBy("month")
    )
