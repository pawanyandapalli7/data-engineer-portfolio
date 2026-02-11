from pyspark.sql import SparkSession
from pyspark.sql.window import Window
from pyspark.sql.functions import col, row_number

spark = SparkSession.builder.appName("CDC-Merge").getOrCreate()

# Read CDC data written by AWS DMS
cdc_df = spark.read.parquet("s3://claims-cdc-raw/")

# Keep latest change per business key
window_spec = Window.partitionBy("claim_id").orderBy(col("event_ts").desc())

dedup_df = (
    cdc_df
    .withColumn("rn", row_number().over(window_spec))
    .filter(col("rn") == 1)
    .drop("rn")
)

# Remove deleted records
curated_df = dedup_df.filter(col("op") != "D")

# Write curated snapshot
curated_df.write.mode("overwrite").parquet(
    "s3://claims-curated-data/"
)
