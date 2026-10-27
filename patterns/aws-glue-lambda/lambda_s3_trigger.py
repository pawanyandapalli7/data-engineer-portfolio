"""S3 ObjectCreated -> start one Glue run for exactly the object that arrived."""

import json
import logging
import os
from urllib.parse import unquote_plus

import boto3

log = logging.getLogger()
log.setLevel(logging.INFO)

GLUE_JOB = os.environ.get("GLUE_JOB_NAME", "claims-glue-etl-job")
_glue = None


def glue_client():
    global _glue
    if _glue is None:
        _glue = boto3.client("glue")
    return _glue


def lambda_handler(event, context):
    runs = []
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])  # S3 event keys are URL-encoded
        if key.endswith("/"):
            continue  # folder placeholder, nothing to process
        run = glue_client().start_job_run(
            JobName=GLUE_JOB,
            Arguments={"--source_path": f"s3://{bucket}/{key}"},
        )
        log.info("Started %s run %s for s3://%s/%s", GLUE_JOB, run["JobRunId"], bucket, key)
        runs.append(run["JobRunId"])
    return {"statusCode": 200, "body": json.dumps({"job_runs": runs})}
