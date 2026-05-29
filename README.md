# Pawan Yandapalli — Data & AI Engineering Portfolio

[![CI](https://github.com/pawanyandapalli7/data-engineer-portfolio/actions/workflows/ci.yml/badge.svg)](https://github.com/pawanyandapalli7/data-engineer-portfolio/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-pawanyandapalli-blue)](https://www.linkedin.com/in/pawanyandapalli/)

**Python · PySpark · FastAPI · OpenAI API · LangChain · Pinecone · Kafka · Redis · AWS · Snowflake**

---

## About

I'm a Data & AI Engineer who builds production-grade data pipelines *and* LLM-powered systems. Most data engineers stop at the data layer. I go further — building the RAG pipelines, eval frameworks, and real-time feature stores that make ML actually work in production.

My recent focus: **end-to-end AI systems** — from document ingestion and vector search to LLM evaluation harnesses that answer *"is this model safe to deploy?"*

📧 pawanyandapalli7@gmail.com · 🔗 [LinkedIn](https://www.linkedin.com/in/pawanyandapalli/) · 🐙 [GitHub](https://github.com/pawanyandapalli7)

---

## Featured Projects

### 🤖 Enterprise RAG Pipeline  `11_rag_pipeline/`

> *End-to-end Retrieval-Augmented Generation for enterprise document search*

Built a production RAG system with semantic chunking, OpenAI embeddings, pgvector storage, and GPT-4o generation. Designed for air-gap compatibility (swap OpenAI → `sentence-transformers`, Pinecone → pgvector with no architecture changes).

| Metric | Value |
|---|---|
| Query latency (p50/p95) | 380ms / 720ms |
| Retrieval precision@5 | 0.84 |
| Cost per query | ~$0.008 (GPT-4o) / ~$0.001 (GPT-4o-mini) |
| Ingestion throughput | ~500 chunks/min |

**Stack:** `Python` · `OpenAI API` · `pgvector` · `FastAPI` · `Docker`  
**Key decisions:** Semantic chunking over fixed-size (preserves meaning at boundaries), SHA256 chunk IDs for idempotent upserts, lexical reranking with zero API cost.

---

### 📊 LLM Evaluation Harness  `12_llm_eval_harness/`

> *Automated framework for measuring LLM quality before production deployment*

Built the type of eval harness OpenAI's Forward Deployed Engineering team uses when a customer deployment underperforms. Measures faithfulness, hallucination rate, relevance, latency, and cost using LLM-as-judge (GPT-4o evaluating GPT-4o-mini).

```
gpt-4o-mini vs gpt-4o  (8 healthcare governance eval cases)
────────────────────────────────────────────────────────────
pass_rate              87.5%   →   100.0%
avg_faithfulness       0.891   →   0.962
hallucination_rate    12.5%   →    0.0%
avg_latency_ms         354     →    687
cost_per_query        $0.0001  →   $0.008
```

**Stack:** `Python` · `OpenAI API` · `pytest` · `dataclasses`  
**Design:** Separate faithfulness (continuous) and hallucination (boolean) — they are distinct failure modes. Temperature=0 for reproducible evals.

---

### ⚡ Real-Time Feature Store  `13_realtime_feature_store/`

> *Dual-store ML feature system: Redis (<10ms) + Snowflake + dbt*

Built the fraud detection feature pipeline pattern used at Uber (Michelangelo), Airbnb (Zipline), and Spotify. Event arrives → features computed → Redis updated → ML model queries in <50ms total.

| | Online (Redis) | Offline (Snowflake) |
|---|---|---|
| Latency | <10ms | seconds |
| Data window | 1 hour TTL | 90 days |
| Use case | Real-time inference | Model training |
| Point-in-time correct | No | Yes (critical — prevents training leakage) |

**Stack:** `Python` · `Kafka` · `Redis` · `FastAPI` · `Snowflake` · `dbt` · `Airflow` · `Docker`

---

### 🏥 Healthcare Claims Data Platform  `05_end_to_end_projects/`

> *Production-grade AWS data platform: batch + CDC ingestion → analytics*

End-to-end pipeline for healthcare insurance claims. Handles both full-load and incremental CDC processing, with HIPAA-aligned data governance (PHI masking, column-level access control, audit logging).

**Stack:** `AWS S3` · `AWS Glue` · `AWS DMS` · `PySpark` · `Snowflake` · `Airflow`

---

### 🔄 CDC Pipeline  `05_end_to_end_projects/cdc_pipeline/`

> *Idempotent Change Data Capture with Spark merge logic*

Captures row-level changes from PostgreSQL via AWS DMS, applies Spark window-function deduplication, and publishes curated snapshots. Handles late-arriving events, delete propagation, and safe reprocessing.

**Stack:** `PostgreSQL` · `AWS DMS` · `PySpark` · `Amazon S3`

---

## Skills

**Languages:** Python (Advanced) · SQL · PySpark  
**AI/ML & LLM:** OpenAI API · LangChain · RAG · Vector Databases (pgvector, Pinecone) · LLM Evaluation · Fine-tuning concepts  
**Data & Streaming:** Apache Spark · Kafka · dbt · Apache Airflow · AWS Glue  
**Cloud (AWS):** S3 · Glue · DMS · Redshift · EMR · Lambda · EventBridge · IAM  
**Databases:** Snowflake · PostgreSQL · Redis  
**DevOps:** Docker · Terraform · CI/CD (GitHub Actions)  
**Data Governance:** HIPAA-aligned design · PHI masking · Audit logging

---

## Repository Structure

```
data-engineer-portfolio/
├── 01_sql/                       # Advanced SQL, window functions
├── 02_python/                    # Reusable processing utilities + tests
├── 03_spark_pyspark/             # Spark transformations, optimization
├── 04_cloud_aws/                 # AWS Glue/Lambda samples, architecture diagrams
├── 05_end_to_end_projects/       # CDC pipeline, healthcare claims platform
├── 06_devops/                    # Docker, Terraform, CI/CD
├── 07_data_quality_framework/    # Schema validation, business rules, reconciliation
├── 08_healthcare_data_governance/# PHI masking, HIPAA-aligned patterns
├── 09_snowflake_optimization/    # Clustering, query tuning, cost optimization
├── 10_pipeline_monitoring_sla/   # Airflow SLA, retries, backfill strategy
├── 11_rag_pipeline/              # ★ Enterprise RAG system (FastAPI + pgvector)
├── 12_llm_eval_harness/          # ★ LLM evaluation framework
└── 13_realtime_feature_store/    # ★ Kafka + Redis + Snowflake feature store
```

★ = AI/ML projects (recommended starting point)

---

## Certifications

- NVIDIA — AI for All: From Basics to GenAI Practice
- DeepLearning.AI — AI For Everyone
