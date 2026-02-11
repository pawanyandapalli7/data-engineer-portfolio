from pyspark.sql import SparkSession
from pyspark.sql.window import Window
from pyspark.sql.functions import col, row_number

# --------------------------------------------------
# CDC operation types produced by AWS DMS
# I = Insert
# U = Update
# D = Delete
# --------------------------------------------------

spark = SparkSession.builder.appName("CDC-Merge").getOrCreate()

# --------------------------------------------------
# Read CDC data written by AWS DMS to S3 (raw zone)
# --------------------------------------------------
cdc_df = spark.read.parquet("s3://claims-cdc-raw/")

# Expected columns:
# claim_id        : Primary key
# op              : CDC operation (I/U/D)
# event_ts        : Commit timestamp from source
# <other columns> : Business attributes

# --------------------------------------------------
# Keep latest change per business key
# Handles late-arriving CDC events
# --------------------------------------------------
window_spec = (
    Window
    .partitionBy("claim_id")
    .orderBy(col("event_ts").desc())
)

latest_df = (
    cdc_df
    .withColumn("rn", row_number().over(window_spec))
    .filter(col("rn") == 1)
    .drop("rn")
)

# --------------------------------------------------
# Remove deleted records (D)
# --------------------------------------------------
curated_df = latest_df.filter(col("op") != "D")

# --------------------------------------------------
# Write curated snapshot (idempotent overwrite)
# --------------------------------------------------
curated_df.write.mode("overwrite").parquet(
    "s3://claims-curated-data/"
)

# --------------------------------------------------
# Stop Spark session
# --------------------------------------------------
spark.stop()
