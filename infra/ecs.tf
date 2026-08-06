resource "random_password" "jwt_secret" {
  length  = 32
  special = false
}

resource "random_password" "webhook_hmac_secret" {
  length  = 32
  special = false
}

resource "aws_ssm_parameter" "jwt_secret_key" {
  name  = "/${var.project}/${var.environment}/jwt_secret_key"
  type  = "SecureString"
  value = random_password.jwt_secret.result

  tags = {
    Name = "${local.name}-jwt-secret-key"
  }
}

resource "aws_ssm_parameter" "webhook_hmac_secret" {
  name  = "/${var.project}/${var.environment}/webhook_hmac_secret"
  type  = "SecureString"
  value = random_password.webhook_hmac_secret.result

  tags = {
    Name = "${local.name}-webhook-hmac-secret"
  }
}

resource "aws_ecr_repository" "backend" {
  name                 = "${local.name}-backend"
  image_tag_mutability = "MUTABLE"
}

resource "aws_ecs_cluster" "main" {
  name = local.name
}

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${local.name}-backend"
  retention_in_days = 14
}

resource "aws_iam_role" "ecs_task_execution" {
  name = "${local.name}-ecs-task-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_task_execution_ssm" {
  name = "${local.name}-ecs-task-execution-ssm"
  role = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["ssm:GetParameters"]
        Resource = [
          aws_ssm_parameter.database_url.arn,
          aws_ssm_parameter.redis_url.arn,
          aws_ssm_parameter.jwt_secret_key.arn,
          aws_ssm_parameter.webhook_hmac_secret.arn,
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "${local.name}-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.backend_cpu
  memory                   = var.backend_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn

  container_definitions = jsonencode([
    {
      name  = "backend"
      image = "${aws_ecr_repository.backend.repository_url}:${var.image_tag}"

      portMappings = [{
        containerPort = var.backend_container_port
        protocol      = "tcp"
      }]

      secrets = [
        { name = "DATABASE_URL", valueFrom = aws_ssm_parameter.database_url.arn },
        { name = "REDIS_URL", valueFrom = aws_ssm_parameter.redis_url.arn },
        { name = "JWT_SECRET_KEY", valueFrom = aws_ssm_parameter.jwt_secret_key.arn },
        { name = "WEBHOOK_HMAC_SECRET", valueFrom = aws_ssm_parameter.webhook_hmac_secret.arn },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.backend.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "backend"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "backend" {
  name            = "${local.name}-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.backend_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = var.backend_container_port
  }

  depends_on = [aws_lb_listener.http]
}
