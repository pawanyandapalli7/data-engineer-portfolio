# AWS Glue & Lambda Samples

This module demonstrates an event-driven data processing pattern on AWS using Glue and Lambda.

## Components
- **AWS Glue (PySpark):** Cleans and curates raw healthcare claims data
- **AWS Lambda:** Triggers Glue jobs on S3 object creation events

## Flow
1. Raw data lands in Amazon S3
2. S3 event triggers AWS Lambda
3. Lambda starts AWS Glue ETL job
4. Curated data is written back to S3

## Use Cases
- Healthcare claims ingestion
- Event-driven ETL pipelines
- Analytics and ML-ready data preparation

## Why This Matters

This pattern is commonly used in production data platforms to:
- Enable near real-time data processing
- Reduce operational overhead with serverless services
- Ensure scalable and cost-efficient ETL pipelines

This design is suitable for healthcare, finance, and event-driven analytics workloads.
