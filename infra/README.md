# Infra

Terraform for the AWS resources this app runs on: ECS/Fargate (backend), RDS Postgres, ElastiCache Redis,
networking (VPC, ALB), and IAM. One flat state, no modules — every resource lives in a `.tf` file named
after the resource type it provisions (`network.tf`, `ecs.tf`, `rds.tf`, `elasticache.tf`).

Secrets (DB password, JWT secret, webhook HMAC secret) are generated with `random_password` and published
to SSM Parameter Store as `SecureString` parameters. The ECS task definition injects them into the backend
container via `secrets` (`valueFrom` the parameter ARN), so nothing sensitive is hardcoded or passed as a
plain environment variable.

## Running against LocalStack

Requires [LocalStack](https://docs.localstack.cloud/) running locally (the community/free tier is enough
to `apply` about half of this Terraform — see the known limitation below for exactly which resources).

```bash
# start LocalStack — pin to a known-working community tag; the `latest` tag now
# requires a LOCALSTACK_AUTH_TOKEN just to boot, even for free-tier features
docker run -d --name localstack -p 4566:4566 localstack/localstack:3.8

# from infra/
terraform init
terraform plan
terraform apply
```

The `aws` provider is pre-configured (`provider.tf`) with dummy credentials and every endpoint pointed at
`http://localhost:4566`, so no AWS credentials or account are needed. No `tflocal` wrapper required.

To tear everything down:

```bash
terraform destroy
```

## Known limitation

Confirmed by actually running `terraform apply` against LocalStack community edition 3.8.1 (ticket 11):
several services used here are LocalStack Pro-tier only and fail with a 501 "not yet implemented or pro
feature" error on `apply`, even though they pass `terraform validate`/`plan`:

- **ECS** — `aws_ecs_cluster`, `aws_ecs_service` (`ecs.tf`)
- **ECR** — `aws_ecr_repository` (`ecs.tf`)
- **RDS** — `aws_db_subnet_group`, `aws_db_instance` (`rds.tf`)
- **ElastiCache** — `aws_elasticache_cluster` (`elasticache.tf`, see ADR-0003)
- **ELBv2** — `aws_lb`, `aws_lb_target_group` (`network.tf`)

Only VPC/networking (subnets, route tables, security groups, IGW), IAM, CloudWatch Logs, and SSM
Parameter Store apply successfully against the community tier. Local *application* testing uses the
plain Postgres/Redis containers from `backend/docker-compose.yml` instead, independent of this Terraform.

## Container image

`ecs.tf` provisions an ECR repository (`aws_ecr_repository.backend`) but does not build or push an image —
there's no `Dockerfile` yet. The ECS task definition references
`<repository_url>:<var.image_tag>` (default tag `latest`), so `terraform apply` succeeds and creates an
empty repository; the ECS service won't have a running task until an image is built and pushed there.

## Validating

```bash
terraform validate
```

Checks syntax and internal consistency only — doesn't require LocalStack to be running.
