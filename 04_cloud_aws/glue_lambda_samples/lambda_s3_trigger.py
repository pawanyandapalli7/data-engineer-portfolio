import json
import boto3

glue = boto3.client("glue")

def lambda_handler(event, context):
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        glue.start_job_run(
            JobName="claims-glue-etl-job",
            Arguments={
                "--source_bucket": bucket,
                "--source_key": key
            }
        )

    return {
        "statusCode": 200,
        "body": json.dumps("Glue job triggered successfully")
    }
