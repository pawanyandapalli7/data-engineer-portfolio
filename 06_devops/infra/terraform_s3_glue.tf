terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

resource "aws_s3_bucket" "raw_bucket" {
  bucket = "claims-raw-data-example"
}

# Encrypt at rest — required for any bucket holding PHI/claims data.
resource "aws_s3_bucket_server_side_encryption_configuration" "raw_bucket" {
  bucket = aws_s3_bucket.raw_bucket.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

# Versioning — supports recovery from accidental overwrite/delete and
# satisfies audit-trail expectations for regulated healthcare data.
resource "aws_s3_bucket_versioning" "raw_bucket" {
  bucket = aws_s3_bucket.raw_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Block all public access — this bucket should never be reachable outside
# the account's IAM/Lake Formation boundary.
resource "aws_s3_bucket_public_access_block" "raw_bucket" {
  bucket                  = aws_s3_bucket.raw_bucket.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_glue_catalog_database" "claims_db" {
  name = "claims_analytics"
}
