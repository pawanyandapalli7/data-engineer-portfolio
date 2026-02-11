import boto3

def get_s3_client():
    """Create and return an S3 client."""
    return boto3.client("s3")

def list_objects(bucket: str, prefix: str):
    """
    List objects under a given S3 prefix.
    """
    s3 = get_s3_client()
    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    return [obj["Key"] for obj in response.get("Contents", [])]
