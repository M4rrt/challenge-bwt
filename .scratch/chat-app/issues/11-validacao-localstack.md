# 11 — Validação LocalStack

**What to build:** The Terraform in `infra/` (ticket 02) actually provisions against LocalStack, proving the IaC works end-to-end within the project's stated constraints (ADR-0003's known ElastiCache gap).

**Blocked by:** 02.

**Status:** done

- [x] LocalStack running via Docker, `terraform init`/`plan`/`apply` targeted at it
- [x] Resources other than ElastiCache apply successfully — revised: only VPC/networking, IAM, CloudWatch Logs, and SSM actually apply; ECS, ECR, RDS, and ELBv2 turned out to be equally Pro-tier-gated (see Comments)
- [x] ElastiCache's expected failure/limitation documented in `infra/README.md` (LocalStack Pro-tier gap, per ADR-0003) — expanded to cover all five affected resources
- [x] `terraform destroy` documented and confirmed to work

## Comments

**2026-08-07** — Ran the full cycle against a live LocalStack container (Terraform v1.15.8, `hashicorp/aws` 5.100.0).

- `localstack/localstack:latest` (pulled fresh) no longer boots on the community tier at all — it now requires a `LOCALSTACK_AUTH_TOKEN` and exits with code 55 ("License activation failed"). Pinned to `localstack/localstack:3.8` (3.8.1, community edition) instead, which starts cleanly. Updated `infra/README.md`'s docker command to pin this tag so the next person doesn't hit the same wall.
- `terraform init` and `terraform plan` both succeeded cleanly against LocalStack (38 resources planned, 0 errors).
- `terraform apply`: 24 resources created successfully (VPC, subnets, route tables, IGW, security groups, IAM role + policy attachment, CloudWatch log group, SSM params, `random_password` resources). 5 resources failed with LocalStack 501 "not yet implemented or pro feature": `aws_ecr_repository.backend`, `aws_ecs_cluster.main`, `aws_elasticache_subnet_group.main`, `aws_db_subnet_group.main`, `aws_lb.main`/`aws_lb_target_group.backend`. This contradicts what ADR-0003 and the original `infra/README.md` claimed (only ElastiCache affected) — ECS, ECR, RDS, and ELBv2 are equally Pro-tier-only on LocalStack community edition. Corrected both docs to list the full set.
- `terraform destroy` on the partially-applied state cleaned up all 24 created resources with 0 errors.
- LocalStack container removed after verification (`docker rm -f localstack`) — this was a one-off local check, nothing left running.
