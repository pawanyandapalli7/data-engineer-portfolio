# AWS to Azure Data Platform Mapping

## Overview
This document demonstrates cloud-agnostic data engineering knowledge by mapping
commonly used AWS data services to their Azure equivalents.

The goal is to show how existing AWS-based data pipelines can be conceptually
translated to Azure with minimal friction.

---

## Core Data Platform Mapping

| AWS Service | Azure Equivalent | Usage Context |
|------------|------------------|---------------|
| Amazon S3 | Azure Data Lake Storage Gen2 | Raw and curated data storage |
| AWS Glue | Azure Data Factory | ETL / ELT data pipelines |
| AWS Glue Catalog | Azure Purview / Synapse Catalog | Metadata management |
| AWS Lambda | Azure Functions | Event-driven transformations |
| Amazon Redshift | Azure Synapse Analytics | Data warehousing |
| Amazon EMR | Azure Databricks | Large-scale Spark processing |
| Amazon DMS | Azure Data Factory (CDC) | Change Data Capture |
| Amazon EventBridge | Azure Event Grid | Event-based orchestration |
| Amazon CloudWatch | Azure Monitor | Logging and monitoring |

---

## Security & Governance Mapping

| AWS | Azure |
|----|------|
| IAM | Azure Active Directory (AAD) |
| KMS | Azure Key Vault |
| Secrets Manager | Azure Key Vault |
| Lake Formation | Azure Purview |
| CloudTrail | Azure Activity Logs |

---

## Orchestration & DevOps

| AWS | Azure |
|----|------|
| Apache Airflow (MWAA) | Azure Data Factory / Managed Airflow |
| ECR | Azure Container Registry |
| EKS | Azure Kubernetes Service (AKS) |
| Terraform | Terraform (Cloud-agnostic) |

---

## Example: AWS Glue → Azure Data Factory Translation

**AWS Pattern**
- Glue job reads data from S3
- Applies PySpark transformations
- Loads curated data into Snowflake / Redshift
- Orchestrated via Airflow or EventBridge

**Azure Equivalent**
- ADF pipeline ingests data from ADLS Gen2
- Mapping Data Flows or Databricks for transformations
- Loads curated data into Synapse or Snowflake
- Orchestrated via ADF triggers or Airflow

---

## Key Takeaways
- Core data engineering concepts remain the same across clouds
- Differences are primarily in service names and configuration
- Existing AWS expertise transfers directly to Azure with minimal ramp-up

This mapping reflects practical, real-world cloud migration and
multi-cloud data platform design considerations.
