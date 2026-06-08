# Pawan Yandapalli — Data Engineering Portfolio

[![CI](https://github.com/pawanyandapalli7/data-engineer-portfolio/actions/workflows/ci.yml/badge.svg)](https://github.com/pawanyandapalli7/data-engineer-portfolio/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-pawanyandapalli-blue)](https://www.linkedin.com/in/pawanyandapalli/)
[![Portfolio](https://img.shields.io/badge/Portfolio-Live-brightgreen)](https://pawanyandapalli.com)

**Python · PySpark · Kafka · Spark · Snowflake · AWS · dbt · Databricks · Airflow**

---

## About

I'm a Data Engineer with 5+ years building production-grade data pipelines on AWS — CDC ingestion, real-time streaming, HIPAA-aligned data governance, and analytics-ready datasets for ML teams.

Lately I've been extending into AI infrastructure: RAG pipelines, LLM evaluation, and real-time feature stores. These aren't production deployments — they're how I'm learning the AI layer by building it from the ground up.

📧 pawanyandapalli1@gmail.com · 🔗 [LinkedIn](https://www.linkedin.com/in/pawanyandapalli/) · 🌐 [pawanyandapalli.com](https://pawanyandapalli.com)

---

## Core Data Engineering Projects

### 🏥 Healthcare Claims Data Platform &nbsp;`05_end_to_end_projects/`

> *Production-grade AWS data platform: batch + CDC ingestion → analytics*

End-to-end pipeline for healthcare insurance claims at TouchWorld. Dual batch + CDC ingestion, HIPAA-aligned governance (PHI masking, column-level access, audit logging), curated datasets serving 3 downstream ML teams.

- **500K+ records/day** · Latency cut from **4h → 30min** · Zero HIPAA incidents across 24 months
- Schema drift was root cause of silent contract failures — introduced version enforcement, zero incidents since

**Stack:** `AWS S3` · `AWS Glue` · `AWS DMS` · `PySpark` · `Snowflake` · `Airflow` · `Lake Formation`

---

### 🔄 CDC Pipeline &nbsp;`05_end_to_end_projects/cdc_pipeline/`

> *Idempotent Change Data Capture with Spark merge logic*

Captures row-level changes from PostgreSQL via AWS DMS, applies Spark window-function deduplication, publishes curated snapshots. Handles late-arriving events, delete propagation, and safe reprocessing.

**Stack:** `PostgreSQL` · `AWS DMS` · `PySpark` · `Amazon S3`

---

### 🛡️ Data Quality Framework &nbsp;`07_data_quality_framework/`

> *Reusable validation layer for healthcare and analytics pipelines*

Schema validation, null/uniqueness checks, business rule enforcement, and source-vs-target reconciliation. Pluggable across Glue, Spark, and dbt pipelines.

**Stack:** `PySpark` · `SQL` · `Great Expectations`

---

### ❄️ Snowflake Optimization &nbsp;`09_snowflake_optimization/`

> *Query tuning and cost optimization at analytics scale*

Clustering keys for partition pruning, materialized views, result caching, warehouse right-sizing with cost analysis from production workloads.

**Stack:** `Snowflake` · `SQL`

---

## AI / LLM Exploration Projects

> These are learning projects — built to understand how AI systems work from the data infrastructure side. Not production deployments.

### 🤖 Enterprise RAG Pipeline &nbsp;`11_rag_pipeline/`

Built a full RAG system to understand the data pipeline underneath LLM applications — chunking strategies, embedding models, vector storage, and retrieval quality. The eval harness (below) was built specifically to measure whether this system was any good.

| Metric | Value |
|---|---|
| Query latency (p50 / p95) | 380ms / 720ms |
| Retrieval precision@5 | 0.84 |
| Cost per query | ~$0.008 (GPT-4o) / ~$0.001 (GPT-4o-mini) |

**Stack:** `Python` · `OpenAI API` · `pgvector` · `FastAPI` · `Docker`

---

### 📊 LLM Evaluation Harness &nbsp;`12_llm_eval_harness/`

Built to answer the question I kept asking while building the RAG system: *"how do I know if this is actually working?"* Measures faithfulness, hallucination rate, relevance, latency, and cost using LLM-as-judge.

```
gpt-4o-mini vs gpt-4o  ·  8 healthcare governance eval cases
─────────────────────────────────────────────────────────────
pass_rate           87.5%   →  100.0%
avg_faithfulness    0.891   →    0.962
hallucination_rate 12.5%   →    0.0%
avg_latency_ms      354     →    687
cost_per_query     $0.0001  →   $0.008
```

**Stack:** `Python` · `OpenAI API` · `pytest`

---

### ⚡ Real-Time Feature Store &nbsp;`13_realtime_feature_store/`

Built to understand how ML teams consume data at inference time — the part that sits between clean data pipelines and deployed models. Dual-store: Redis for online serving (<10ms), Snowflake for offline training with point-in-time correctness.

| | Online (Redis) | Offline (Snowflake) |
|---|---|---|
| Latency | <10ms | seconds |
| Use case | Real-time inference | Model training |
| Point-in-time correct | No | Yes — prevents training leakage |

**Stack:** `Kafka` · `Redis` · `FastAPI` · `Snowflake` · `dbt` · `Airflow`

---

## Skills

**Core (Production):** Python · PySpark · SQL · Apache Spark · Kafka · dbt · Airflow · AWS Glue · Databricks  
**Cloud:** AWS (S3, Glue, DMS, Redshift, EMR, Lambda, EventBridge, IAM) · Azure Databricks  
**Databases:** Snowflake · PostgreSQL · Redis  
**DevOps:** Docker · Terraform · CI/CD (GitHub Actions)  
**Data Governance:** HIPAA-aligned design · PHI masking · Schema contracts · Audit logging  
**Exploring:** OpenAI API · LangChain · RAG · Vector Databases (pgvector, Pinecone) · LLM Evaluation

---

## Repository Structure

```
data-engineer-portfolio/
├── 01_sql/                        # Advanced SQL, window functions
├── 02_python/                     # Reusable processing utilities + tests
├── 03_spark_pyspark/              # Spark transformations, optimization
├── 04_cloud_aws/                  # AWS Glue/Lambda samples, architecture diagrams
│   └── aws_to_azure_mapping.md    # AWS ↔ Azure service mapping
├── 05_end_to_end_projects/        # CDC pipeline, healthcare claims platform ★
├── 06_devops/                     # Docker, Terraform, CI/CD
├── 07_data_quality_framework/     # Schema validation, business rules, reconciliation ★
├── 08_healthcare_data_governance/ # PHI masking, HIPAA-aligned patterns ★
├── 09_snowflake_optimization/     # Clustering, query tuning, cost optimization
├── 10_pipeline_monitoring_sla/    # Airflow SLA, retries, backfill strategy
├── 11_rag_pipeline/               # RAG system (learning project)
├── 12_llm_eval_harness/           # LLM evaluation framework (learning project)
└── 13_realtime_feature_store/     # Feature store (learning project)
```

★ = production-pattern projects

---

## Certifications

**Platform Architecture**
- 🏆 AWS Databricks Platform Architect — Databricks · Aug 2025 · *expires Aug 2027*
- 🏆 Azure Databricks Platform Architect — Databricks · Sep 2025

**Data Engineering**
- ✅ dbt Fundamentals — dbt Labs · Oct 2025

**AI / LLM**
- ✅ Building RAG Agents with LLMs — NVIDIA DLI · 2024
- ✅ Generative AI with Diffusion Models — NVIDIA DLI · 2024
- ✅ LangChain for LLM Application Development — DeepLearning.AI · 2024
- ✅ Building Systems with the ChatGPT API — DeepLearning.AI · 2024
