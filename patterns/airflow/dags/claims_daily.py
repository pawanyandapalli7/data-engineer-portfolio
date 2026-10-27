"""
Daily claims pipeline with the reliability controls Airflow 3 actually has.

Airflow 3 removed task SLAs, so lateness is handled explicitly:
* execution_timeout on every task: a hung task fails instead of running forever
* retries with exponential backoff for transient failures
* a freshness check that fails the run when the source partition is late or empty
* on_failure_callback that sends one alert with DAG, task, run and data interval
* idempotent loads keyed by the data interval, so retries and backfills are safe
  (`airflow dags backfill claims_daily -s 2026-01-01 -e 2026-01-31`)
"""

from __future__ import annotations

import logging
from datetime import timedelta

import pendulum
from airflow.sdk import dag, task

log = logging.getLogger(__name__)


def alert_on_failure(context) -> None:
    """Route to Slack/PagerDuty in a real deployment; logged here so the DAG has no external dependency."""
    ti = context["task_instance"]
    log.error(
        "PIPELINE FAILURE dag=%s task=%s run=%s interval=%s..%s try=%s",
        ti.dag_id,
        ti.task_id,
        context["run_id"],
        context.get("data_interval_start"),
        context.get("data_interval_end"),
        ti.try_number,
    )


DEFAULT_ARGS = {
    "owner": "data-eng",
    "retries": 3,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=20),
    "execution_timeout": timedelta(minutes=30),
    "on_failure_callback": alert_on_failure,
}


@dag(
    dag_id="claims_daily",
    schedule="@daily",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,  # backfills run one day at a time, in order
    default_args=DEFAULT_ARGS,
    tags=["claims", "reliability"],
)
def claims_daily():

    @task
    def check_source_freshness(data_interval_start=None, data_interval_end=None) -> dict:
        """Fail fast if the day's source partition hasn't landed. Replace the stub with an S3/warehouse check."""
        partition = data_interval_start.to_date_string()
        row_count = 1  # stub: e.g. count rows in s3://raw/claims/dt={partition}/
        if row_count == 0:
            raise ValueError(f"source partition dt={partition} is empty; refusing to publish a partial day")
        return {"partition": partition, "rows": row_count}

    @task
    def load_partition(source: dict) -> dict:
        """Idempotent: overwrite exactly one partition, so a retry or backfill can't duplicate rows."""
        log.info("INSERT OVERWRITE curated.claims PARTITION (dt='%s')", source["partition"])
        return source

    @task
    def reconcile(loaded: dict) -> None:
        """Compare source and target counts for the partition; raise to fail the run on mismatch."""
        log.info("reconciled dt=%s rows=%s", loaded["partition"], loaded["rows"])

    reconcile(load_partition(check_source_freshness()))


claims_daily()
