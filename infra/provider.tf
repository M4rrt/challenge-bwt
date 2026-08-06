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
}

provider "aws" {
  region = var.aws_region

  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    ec2         = var.localstack_endpoint
    ecr         = var.localstack_endpoint
    ecs         = var.localstack_endpoint
    elasticache = var.localstack_endpoint
    elb         = var.localstack_endpoint
    iam         = var.localstack_endpoint
    logs        = var.localstack_endpoint
    rds         = var.localstack_endpoint
    ssm         = var.localstack_endpoint
    sts         = var.localstack_endpoint
  }
}
