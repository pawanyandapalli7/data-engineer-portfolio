import boto3
from typing import List

def get_s3_client():
    """
    Create and return a boto3 S3 client.
    """
    return boto3.client("s3")


def list_objects(bucket: str, prefix: str) -> List[str]:
    """
    List all object keys under a given S3 prefix.

    Handles pagination to safely retrieve more than 1,000 objects.
    """
    s3 = get_s3_client()
    paginator = s3.get_paginator("list_objects_v2")

    keys: List[str] = []

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])

    return keys
