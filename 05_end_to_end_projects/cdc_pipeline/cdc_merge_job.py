"""
CDC Merge Job — reconstructs curated state from AWS DMS change events.

Reads raw CDC records (I/U/D operations) written by AWS DMS to S3, keeps the
latest change per business key (handling late-arriving/out-of-order events),
drops deleted records, and writes an idempotent curated snapshot.

Usage:
    spark-submit cdc_merge_job.py \
        --input s3://claims-cdc-raw/ \
        --output s3://claims-curated-data/ \
        --key claim_id
"""

import argparse
import logging
import sys

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import col, row_number
from pyspark.sql.window import Window

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("cdc_merge_job")

# CDC operation types produced by AWS DMS: I = Insert, U = Update, D = Delete
DELETE_OP = "D"


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="S3 path to raw CDC parquet (DMS output)")
    parser.add_argument("--output", required=True, help="S3 path to write curated parquet")
    parser.add_argument("--key", default="claim_id", help="Business key column to dedupe on")
    parser.add_argument("--event-ts-col", default="event_ts", help="Column holding source commit timestamp")
    parser.add_argument("--op-col", default="op", help="Column holding the CDC operation (I/U/D)")
    return parser.parse_args(argv)


def read_cdc_events(spark: SparkSession, input_path: str) -> DataFrame:
    log.info(f"Reading raw CDC events from {input_path}")
    df = spark.read.parquet(input_path)
    if df.rdd.isEmpty():
        log.warning(f"No records found at {input_path} — nothing to merge")
    return df


def merge_latest_state(df: DataFrame, key: str, event_ts_col: str, op_col: str) -> DataFrame:
    """
    Keep the latest change per business key, then drop deletes.

    Late-arriving events are handled naturally: ordering by event_ts (the
    source commit time, not ingestion time) means an out-of-order event
    still resolves to the correct "latest" state once reprocessed.
    """
    required_cols = {key, event_ts_col, op_col}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Input is missing required columns: {sorted(missing)}")

    window_spec = Window.partitionBy(key).orderBy(col(event_ts_col).desc())

    latest = (
        df.withColumn("_rn", row_number().over(window_spec))
        .filter(col("_rn") == 1)
        .drop("_rn")
    )

    curated = latest.filter(col(op_col) != DELETE_OP)
    return curated


def write_curated(df: DataFrame, output_path: str) -> None:
    log.info(f"Writing curated snapshot to {output_path}")
    df.write.mode("overwrite").parquet(output_path)


def run(args: argparse.Namespace) -> int:
    spark = SparkSession.builder.appName("CDC-Merge").getOrCreate()
    try:
        cdc_df = read_cdc_events(spark, args.input)
        curated_df = merge_latest_state(cdc_df, args.key, args.event_ts_col, args.op_col)
        write_curated(curated_df, args.output)
        log.info("CDC merge completed successfully")
        return 0
    except Exception:
        log.exception("CDC merge job failed")
        return 1
    finally:
        spark.stop()


if __name__ == "__main__":
    sys.exit(run(parse_args()))
