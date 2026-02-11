# Change Data Capture (CDC) Pipeline

This project demonstrates a production-grade Change Data Capture (CDC) pipeline using AWS DMS and Apache Spark to reliably process incremental data changes from a transactional system into analytics-ready datasets.

---

## Architecture Overview

- Source OLTP database emits inserts, updates, and deletes
- AWS DMS captures full load and ongoing CDC events
- CDC records are written to Amazon S3 (raw zone)
- Apache Spark applies merge logic to reconstruct the latest state
- Curated datasets are published to Snowflake / Amazon Redshift for analytics and ML

---

## Key Engineering Concepts

- **Idempotent processing** — safe reprocessing without data corruption  
- **Deduplication** using Spark window functions  
- **Late-arriving event handling** based on event timestamps  
- **Delete propagation** from source to curated layer  
- **Scalable Spark-based processing** for large CDC volumes  

---

## CDC Processing Logic

1. Read raw CDC records written by AWS DMS from Amazon S3  
2. Partition records by business key (e.g., `claim_id`)  
3. Order events by change timestamp (`event_ts`)  
4. Retain the most recent record per key  
5. Filter delete operations (`op = 'D'`)  
6. Write a consistent curated snapshot for downstream consumption  

This approach ensures deterministic outputs and correctness even with out-of-order or reprocessed events.

---

## Use Cases

- Insurance claims and policy updates  
- Financial transaction reconciliation  
- Customer master data synchronization  
- Any system requiring incremental data ingestion  

---

## Technology Stack

- **Source Database:** PostgreSQL  
- **CDC Tool:** AWS DMS  
- **Processing Engine:** Apache Spark (PySpark)  
- **Storage:** Amazon S3  
- **Analytics:** Snowflake, Amazon Redshift  
