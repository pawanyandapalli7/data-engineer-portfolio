import sys
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql.functions import col, to_date

args = getResolvedOptions(sys.argv, ["JOB_NAME"])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

claims_df = spark.read.parquet("s3://claims-raw-data/")

clean_df = (
    claims_df
    .filter(col("claim_id").isNotNull())
    .withColumn("claim_date", to_date(col("claim_date")))
    .dropDuplicates(["claim_id"])
)

clean_df.write.mode("overwrite").parquet(
    "s3://claims-curated-data/"
)

job.commit()

# Read raw claims data from S3 (Raw Zone)
claims_df = spark.read.parquet("s3://claims-raw-data/")

# Apply data quality rules:
# - Remove null claim IDs
# - Normalize date fields
# - Deduplicate records
clean_df = (
    claims_df
    .filter(col("claim_id").isNotNull())
    .withColumn("claim_date", to_date(col("claim_date")))
    .dropDuplicates(["claim_id"])
)

# Write curated dataset to S3 (Curated Zone)
clean_df.write.mode("overwrite").parquet(
    "s3://claims-curated-data/"
)
