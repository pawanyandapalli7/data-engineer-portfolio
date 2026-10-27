terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "bucket_prefix" {
  description = "Globally unique prefix for the raw and curated buckets"
  type        = string
}

provider "aws" {
  region = var.region
}

resource "aws_kms_key" "lake" {
  description         = "Encrypts the claims raw and curated zones"
  enable_key_rotation = true
}

resource "aws_s3_bucket" "zone" {
  for_each = toset(["raw", "curated"])
  bucket   = "${var.bucket_prefix}-claims-${each.key}"
}

# Encrypt at rest with a customer-managed key (rotation on).
resource "aws_s3_bucket_server_side_encryption_configuration" "zone" {
  for_each = aws_s3_bucket.zone
  bucket   = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.lake.arn
    }
    bucket_key_enabled = true
  }
}

# Versioning: recover from accidental overwrites and deletes.
resource "aws_s3_bucket_versioning" "zone" {
  for_each = aws_s3_bucket.zone
  bucket   = each.value.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "zone" {
  for_each                = aws_s3_bucket.zone
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Deny any request that isn't over TLS.
data "aws_iam_policy_document" "tls_only" {
  for_each = aws_s3_bucket.zone
  statement {
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [each.value.arn, "${each.value.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "tls_only" {
  for_each = aws_s3_bucket.zone
  bucket   = each.value.id
  policy   = data.aws_iam_policy_document.tls_only[each.key].json
}

resource "aws_glue_catalog_database" "claims" {
  name = "claims_analytics"
}
