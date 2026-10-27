"""
CDC snapshot job: rebuilds the current state of a table from AWS DMS change events.

Reads raw CDC records written by AWS DMS to S3 (parquet), keeps the latest change
per business key, drops keys whose latest change is a delete, and writes a
curated snapshot.

Design notes
------------
* Ordering is by the *source commit* timestamp, not arrival time, so a late
  event can never overwrite a newer state.
* Two changes can share a commit timestamp (one transaction, several updates).
  Pass ``--seq-col`` (for example the DMS ``AR_H_CHANGE_SEQ`` header column) to
  break those ties deterministically. Without it, ties are broken by operation
  priority (D > U > I) so the result is still deterministic.
* DMS full-load rows carry a NULL operation unless ``includeOpForFullLoad`` is
  set. Those rows are treated as inserts instead of being silently dropped.
* This is a full rebuild from the raw zone on every run: simple, replay-safe and
  correct, but it costs a full scan. The incremental version of this job is a
  Delta/Iceberg MERGE of only the new change files into the curated table.

Usage:
    spark-submit cdc_merge_job.py \
        --input s3://claims-cdc-raw/ --output s3://claims-curated/ \
        --key claim_id --event-ts-col event_ts --op-col op --seq-col change_seq
"""

import argparse
import logging
import sys
from typing import Optional

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("cdc_merge_job")

INSERT_OP, UPDATE_OP, DELETE_OP = "I", "U", "D"


def _op_priority():
    """Within one commit timestamp a delete wins over an update, and an update over an insert."""
    return F.when(F.col("_op") == DELETE_OP, 3).when(F.col("_op") == UPDATE_OP, 2).otherwise(1)


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Rebuild a curated snapshot from DMS CDC files")
    p.add_argument("--input", required=True, help="Path to raw CDC parquet (DMS output)")
    p.add_argument("--output", required=True, help="Path to write the curated snapshot")
    p.add_argument("--key", default="claim_id", help="Business key column")
    p.add_argument("--event-ts-col", default="event_ts", help="Source commit timestamp column")
    p.add_argument("--op-col", default="op", help="CDC operation column (I/U/D, NULL on full load)")
    p.add_argument("--seq-col", default=None, help="Optional change-sequence column used as a tiebreaker")
    return p.parse_args(argv)


def merge_latest_state(
    df: DataFrame, key: str, event_ts_col: str, op_col: str, seq_col: Optional[str] = None
) -> DataFrame:
    """Return one row per key holding its latest state; keys whose latest change is a delete are removed."""
    required = {key, event_ts_col, op_col} | ({seq_col} if seq_col else set())
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Input is missing required columns: {sorted(missing)}")

    with_op = df.withColumn("_op", F.upper(F.coalesce(F.col(op_col), F.lit(INSERT_OP))))
    order = [F.col(event_ts_col).desc_nulls_last()]
    if seq_col:
        order.append(F.col(seq_col).desc_nulls_last())
    order.append(_op_priority().desc())

    latest = (
        with_op.withColumn("_rn", F.row_number().over(Window.partitionBy(key).orderBy(*order)))
        .where(F.col("_rn") == 1)
        .drop("_rn")
    )
    return latest.where(F.col("_op") != DELETE_OP).drop("_op")


def run(args: argparse.Namespace) -> int:
    spark = SparkSession.builder.appName("cdc-snapshot").getOrCreate()
    try:
        log.info("Reading CDC events from %s", args.input)
        events = spark.read.parquet(args.input)
        curated = merge_latest_state(events, args.key, args.event_ts_col, args.op_col, args.seq_col)
        log.info("Writing curated snapshot to %s", args.output)
        curated.write.mode("overwrite").parquet(args.output)
        return 0
    except Exception:
        log.exception("CDC snapshot job failed")
        return 1
    finally:
        spark.stop()


if __name__ == "__main__":
    sys.exit(run(parse_args()))
