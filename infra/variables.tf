variable "project" {
  description = "Project name, used as a prefix for resource names."
  type        = string
  default     = "chat-app"
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "local"
}

variable "aws_region" {
  description = "AWS region to provision into."
  type        = string
  default     = "us-east-1"
}

variable "localstack_endpoint" {
  description = "Endpoint URL for LocalStack's edge service."
  type        = string
  default     = "http://localhost:4566"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "azs" {
  description = "Availability zones to spread subnets across."
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets (ALB, ECS tasks)."
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets (RDS, ElastiCache)."
  type        = list(string)
  default     = ["10.0.101.0/24", "10.0.102.0/24"]
}

variable "backend_container_port" {
  description = "Port the backend container listens on."
  type        = number
  default     = 8000
}

variable "backend_cpu" {
  description = "Fargate task CPU units for the backend service."
  type        = string
  default     = "256"
}

variable "backend_memory" {
  description = "Fargate task memory (MiB) for the backend service."
  type        = string
  default     = "512"
}

variable "backend_desired_count" {
  description = "Number of backend task instances to run."
  type        = number
  default     = 1
}

variable "image_tag" {
  description = "Tag of the backend image to deploy from ECR."
  type        = string
  default     = "latest"
}

variable "db_name" {
  description = "Postgres database name."
  type        = string
  default     = "chat"
}

variable "db_username" {
  description = "Postgres master username."
  type        = string
  default     = "chat"
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t3.micro"
}

variable "db_engine_version" {
  description = "Postgres engine version, matching backend/docker-compose.yml."
  type        = string
  default     = "16"
}

variable "db_allocated_storage" {
  description = "RDS allocated storage in GB."
  type        = number
  default     = 20
}

variable "redis_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.t3.micro"
}

variable "redis_engine_version" {
  description = "Redis engine version, matching backend/docker-compose.yml."
  type        = string
  default     = "7.0"
}

variable "frontend_origin" {
  description = "Allowed CORS origin for the frontend, passed to the backend as FRONTEND_ORIGIN."
  type        = string
  default     = "http://localhost:5173"
}
