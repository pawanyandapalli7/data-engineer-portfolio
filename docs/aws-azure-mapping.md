# AWS ↔ Azure ↔ Microsoft Fabric: data platform mapping

Closest equivalents, not exact ones. The notes column is where the real
migration work hides.

| Concern | AWS | Azure | Microsoft Fabric | Notes |
|---|---|---|---|---|
| Lake storage | S3 | ADLS Gen2 | OneLake | OneLake is ADLS Gen2 underneath, with one lake per tenant |
| Table format | Iceberg / Delta on S3 | Delta on ADLS | Delta (native) | Fabric stores every table as Delta |
| Spark processing | EMR, Glue | Azure Databricks, Synapse Spark | Fabric Spark (notebooks, Spark job definitions) | Databricks runs on both clouds, which often makes it the portable choice |
| Serverless ETL | Glue jobs | Data Factory (mapping data flows) | Data Factory in Fabric (pipelines, Dataflow Gen2) | |
| CDC from databases | DMS | Data Factory CDC, Databricks + Debezium | Mirroring (for supported sources) | Validate delete handling and ordering, not just row counts |
| Warehouse | Redshift | Synapse dedicated SQL pools, Databricks SQL | Fabric Warehouse, SQL analytics endpoint | |
| Streaming ingest | Kinesis, MSK | Event Hubs (Kafka-compatible) | Eventstreams, Real-Time Intelligence | |
| Orchestration | MWAA (Airflow), Step Functions | Data Factory, Databricks Workflows | Fabric pipelines, Apache Airflow job | |
| Catalog and governance | Glue Data Catalog, Lake Formation | Unity Catalog, Microsoft Purview | OneLake catalog, Purview | Unity Catalog covers both clouds when Databricks is the platform |
| Identity | IAM | Microsoft Entra ID (formerly Azure AD) | Entra ID | Prefer managed identities over keys on Azure |
| Keys and secrets | KMS, Secrets Manager | Key Vault | Key Vault (via connections) | |
| Audit | CloudTrail | Activity Log, diagnostic settings | Fabric audit logs (via Purview) | |
| Monitoring | CloudWatch | Azure Monitor | Monitoring hub, capacity metrics app | |
| Containers | ECR, EKS | ACR, AKS | n/a | |
| IaC | Terraform, CloudFormation | Terraform, Bicep | Terraform (Fabric provider), REST APIs | |

Worked example in this repo: the [Azure lakehouse](../projects/azure-lakehouse)
is the Azure/Databricks version of a raw → curated → analytics flow that on AWS
would be S3 + Glue/EMR + Lake Formation.
