terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Bucket/table/region/endpoints are supplied at `terraform init` time via
  # `-backend-config=backend.hcl` (see backend.hcl.example and infra/README.md) — a static
  # backend block can't reference vars, and the bucket/table only exist after infra/bootstrap/
  # has been applied.
  backend "s3" {}
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
    appautoscaling = var.localstack_endpoint
    cloudfront     = var.localstack_endpoint
    ec2            = var.localstack_endpoint
    ecr            = var.localstack_endpoint
    ecs            = var.localstack_endpoint
    elasticache    = var.localstack_endpoint
    elb            = var.localstack_endpoint
    iam            = var.localstack_endpoint
    logs           = var.localstack_endpoint
    rds            = var.localstack_endpoint
    s3             = var.localstack_endpoint
    ssm            = var.localstack_endpoint
    sts            = var.localstack_endpoint
  }
}

# CloudFront, ACM certificates for CloudFront, and Route53 are region-agnostic services that
# Terraform still requires a provider region for — ACM certs used by CloudFront specifically
# must be requested in us-east-1 regardless of where the rest of the stack runs (acm.tf).
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    acm     = var.localstack_endpoint
    route53 = var.localstack_endpoint
    sts     = var.localstack_endpoint
  }
}
