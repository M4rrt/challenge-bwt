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
for everything except ElastiCache — see the known limitation below).

```bash
# start LocalStack
docker run -d --name localstack -p 4566:4566 localstack/localstack

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

ElastiCache is a LocalStack Pro-tier service (see ADR-0003). On the free tier, `aws_elasticache_cluster`
in `elasticache.tf` will fail on `terraform apply` even though it passes `terraform validate`/`plan`. Every
other resource applies successfully. Local *application* testing uses the plain Redis container from
`backend/docker-compose.yml` instead, independent of this Terraform.

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
