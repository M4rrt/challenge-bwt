# 11 — Validação LocalStack

**What to build:** The Terraform in `infra/` (ticket 02) actually provisions against LocalStack, proving the IaC works end-to-end within the project's stated constraints (ADR-0003's known ElastiCache gap).

**Blocked by:** 02.

**Status:** ready-for-agent

- [ ] LocalStack running via Docker, `terraform init`/`plan`/`apply` targeted at it
- [ ] Resources other than ElastiCache apply successfully
- [ ] ElastiCache's expected failure/limitation documented in `infra/README.md` (LocalStack Pro-tier gap, per ADR-0003)
- [ ] `terraform destroy` documented and confirmed to work
