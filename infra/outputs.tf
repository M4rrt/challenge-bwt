output "vpc_id" {
  description = "ID of the VPC."
  value       = aws_vpc.main.id
}

output "alb_dns_name" {
  description = "Public DNS name of the load balancer fronting the backend."
  value       = aws_lb.main.dns_name
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster."
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "Name of the ECS service running the backend."
  value       = aws_ecs_service.backend.name
}

output "ecr_repository_url" {
  description = "URL of the ECR repository to push the backend image to."
  value       = aws_ecr_repository.backend.repository_url
}

output "rds_endpoint" {
  description = "Connection endpoint (host:port) of the RDS Postgres instance."
  value       = aws_db_instance.postgres.endpoint
}

output "redis_endpoint" {
  description = "Connection endpoint (host:port) of the ElastiCache Redis cluster."
  value       = "${aws_elasticache_cluster.redis.cache_nodes[0].address}:${aws_elasticache_cluster.redis.cache_nodes[0].port}"
}

output "frontend_bucket" {
  description = "Name of the S3 bucket to sync the frontend build output (frontend/dist) to."
  value       = aws_s3_bucket.frontend.id
}

output "cloudfront_distribution_id" {
  description = "ID of the CloudFront distribution fronting the frontend bucket — needed to invalidate its cache after a deploy."
  value       = aws_cloudfront_distribution.frontend.id
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution's own domain name (*.cloudfront.net), reachable before/without custom DNS."
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "route53_name_servers" {
  description = "Name servers for the Route53 hosted zone — point the registrar for var.domain_name at these to make DNS live."
  value       = aws_route53_zone.main.name_servers
}

