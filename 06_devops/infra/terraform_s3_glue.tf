provider "aws" {
  region = "us-east-1"
}

resource "aws_s3_bucket" "raw_bucket" {
  bucket = "claims-raw-data-example"
}

resource "aws_glue_catalog_database" "claims_db" {
  name = "claims_analytics"
}
