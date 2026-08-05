# 02 — Infra scaffold

**What to build:** The Terraform skeleton for the AWS resources decided in the design session (ECS/Fargate, RDS Postgres, ElastiCache, networking/ALB/IAM), flat `.tf` files by resource type per `docs/decisions.md`, targeting LocalStack. No real AWS apply.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `infra/` with `network.tf`, `ecs.tf`, `rds.tf`, `elasticache.tf`, `variables.tf`, `outputs.tf` — one flat state, no modules
- [ ] Secrets provisioned via SSM Parameter Store (not hardcoded), per the design session's decision
- [ ] `infra/README.md` documents how to run against LocalStack
- [ ] `terraform validate` passes
