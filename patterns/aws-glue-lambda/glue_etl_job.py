"""
Glue job: clean one raw claims file and append it to the curated zone.

Each run handles only the file in --source_path (passed by the Lambda), so
concurrent arrivals don't reprocess or overwrite each other. Output is
partitioned by claim_date and tagged with the source file for lineage; re-running
the same file is made safe downstream by deduplicating on claim_id + updated_at.
"""

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F

args = getResolvedOptions(sys.argv, ["JOB_NAME", "source_path", "curated_path"])

glue_context = GlueContext(SparkContext.getOrCreate())
spark = glue_context.spark_session
job = Job(glue_context)
job.init(args["JOB_NAME"], args)

raw = spark.read.parquet(args["source_path"])

clean = (
    raw.where(F.col("claim_id").isNotNull())
    .withColumn("claim_date", F.to_date("claim_date"))
    .dropDuplicates(["claim_id", "updated_at"])
    .withColumn("_source_file", F.lit(args["source_path"]))
    .withColumn("_processed_at", F.current_timestamp())
)

clean.write.mode("append").partitionBy("claim_date").parquet(args["curated_path"])
job.commit()
