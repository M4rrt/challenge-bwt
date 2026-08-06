resource "aws_elasticache_subnet_group" "main" {
  name       = "${local.name}-redis"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id         = "${local.name}-redis"
  engine             = "redis"
  engine_version     = var.redis_engine_version
  node_type          = var.redis_node_type
  num_cache_nodes    = 1
  port               = 6379
  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]

  tags = {
    Name = "${local.name}-redis"
  }
}

resource "aws_ssm_parameter" "redis_url" {
  name  = "/${var.project}/${var.environment}/redis_url"
  type  = "SecureString"
  value = "redis://${aws_elasticache_cluster.redis.cache_nodes[0].address}:${aws_elasticache_cluster.redis.cache_nodes[0].port}/0"

  tags = {
    Name = "${local.name}-redis-url"
  }
}
