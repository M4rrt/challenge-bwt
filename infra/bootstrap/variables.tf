variable "project" {
  description = "Project name, used as a prefix for resource names. Must match the main infra/'s var.project."
  type        = string
  default     = "chat-app"
}

variable "environment" {
  description = "Deployment environment name. Must match the main infra/'s var.environment."
  type        = string
  default     = "local"
}

variable "aws_region" {
  description = "AWS region to provision the state backend into."
  type        = string
  default     = "us-east-1"
}

variable "localstack_endpoint" {
  description = "Endpoint URL for LocalStack's edge service."
  type        = string
  default     = "http://localhost:4566"
}
