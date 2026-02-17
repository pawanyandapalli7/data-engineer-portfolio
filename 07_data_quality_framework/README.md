# Data Quality & Validation Framework

## Overview
This module demonstrates a reusable data quality framework designed for
healthcare and analytics pipelines.

## Quality Dimensions Covered
- Accuracy
- Completeness
- Timeliness
- Consistency

## Validation Layers

### 1. Schema Validation
- Column existence checks
- Data type enforcement

### 2. Row-Level Validation
- Not-null constraints
- Uniqueness checks
- Accepted values validation

### 3. Business Rules
- Claim/service date consistency
- Duplicate record detection
- Invalid code handling

### 4. Reconciliation
- Source vs target row counts
- Aggregate checksum comparisons

## Integration
Designed to integrate with Spark, AWS Glue, and Airflow pipelines.

## Why This Matters
Reliable healthcare analytics depend on trusted, validated data.
