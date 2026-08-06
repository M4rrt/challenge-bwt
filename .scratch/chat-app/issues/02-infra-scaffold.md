# 02 — Infra scaffold

**What to build:** The Terraform skeleton for the AWS resources decided in the design session (ECS/Fargate, RDS Postgres, ElastiCache, networking/ALB/IAM), flat `.tf` files by resource type per `docs/decisions.md`, targeting LocalStack. No real AWS apply.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] `infra/` with `network.tf`, `ecs.tf`, `rds.tf`, `elasticache.tf`, `variables.tf`, `outputs.tf` — one flat state, no modules
- [x] Secrets provisioned via SSM Parameter Store (not hardcoded), per the design session's decision
- [x] `infra/README.md` documents how to run against LocalStack
- [x] `terraform validate` passes

## Comments

Also added `provider.tf` (terraform/provider blocks + LocalStack `endpoints{}` config) alongside the 6 required files — not one of the enumerated resource files, but needed for `init`/`validate` to work at all.

Decisions made while implementing (confirmed with user):
- ALB + security groups live in `network.tf`; ECS IAM roles live in `ecs.tf` — no separate `alb.tf`/`iam.tf` since the checklist only names 6 files.
- Secrets (DB password, JWT secret, webhook HMAC secret) generated via `random_password`, published as SSM `SecureString` params, injected into the ECS task definition via `secrets`/`valueFrom` — never as plain env vars or hardcoded.
- ECS runs in public subnets with `assign_public_ip = true`, no NAT Gateway. RDS/ElastiCache stay in private subnets (no internet egress needed). Simpler and free on LocalStack; documented as a scope choice, not an oversight.
- `ecs.tf` provisions an empty `aws_ecr_repository` for the backend image (no Dockerfile/build/push yet — that's out of scope here). The task definition references `<repository_url>:<image_tag>`, so `apply` succeeds but the ECS service won't have a running task until an image exists.
- Postgres 16 / Redis 7.0 versions matched to `backend/docker-compose.yml`.

`terraform validate` run 2026-08-06 (Terraform v1.15.8, providers hashicorp/aws ~>5.100.0, hashicorp/random ~>3.9.0): **Success! The configuration is valid.** `terraform fmt` applied one alignment fix in `rds.tf`.
