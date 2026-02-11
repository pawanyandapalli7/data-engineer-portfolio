# Change Data Capture (CDC) Pipeline

This project demonstrates a production-grade Change Data Capture (CDC) pipeline using AWS DMS and Apache Spark.

## Architecture Overview
- Source OLTP database emits inserts, updates, and deletes
- AWS DMS captures changes and writes CDC records to Amazon S3
- Spark applies merge logic to reconstruct the latest state
- Curated datasets are consumed by Snowflake / Redshift for analytics and ML

## Key Engineering Concepts
- Idempotent processing
- Deduplication using window functions
- Late-arriving event handling
- Delete propagation
- Scalable Spark-based processing

## Use Cases
- Insurance claims updates
- Financial transactions
- Customer master data
