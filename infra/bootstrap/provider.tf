terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Intentionally local state: this config provisions the S3 bucket/DynamoDB table that the
  # main infra/ backend depends on, so it can't use that backend on itself.
}

provider "aws" {
  region = var.aws_region

  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  # LocalStack doesn't route virtual-hosted-style S3 requests (<bucket>.localhost:4566);
  # without this, bucket creation hangs retrying "HEAD /" against the wrong host.
  s3_use_path_style = true

  endpoints {
    dynamodb = var.localstack_endpoint
    s3       = var.localstack_endpoint
    sts      = var.localstack_endpoint
  }
}
