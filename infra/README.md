# Infra

Terraform for the AWS resources this app runs on: ECS/Fargate (backend), RDS Postgres, ElastiCache Redis,
networking (VPC, ALB), CloudFront/S3 (frontend), Route53/ACM (DNS/TLS), Application Auto Scaling, IAM, and
remote state (S3 + DynamoDB, provisioned separately by `infra/bootstrap/`). One flat state, no modules —
every resource lives in a `.tf` file named after the resource type it provisions (`network.tf`, `ecs.tf`,
`rds.tf`, `elasticache.tf`, `frontend.tf`, `acm.tf`, `dns.tf`, `autoscaling.tf`).

Secrets (DB password, JWT secret, webhook HMAC secret) are generated with `random_password` and published
to SSM Parameter Store as `SecureString` parameters. The ECS task definition injects them into the backend
container via `secrets` (`valueFrom` the parameter ARN), so nothing sensitive is hardcoded or passed as a
plain environment variable.

## Remote state (`infra/bootstrap/`)

Main `infra/`'s state lives in S3 (with DynamoDB locking) instead of a local `terraform.tfstate` file, so
more than one person can `apply` without clobbering each other's state. That backend's own bucket/table are
provisioned by a separate, self-contained Terraform config — `infra/bootstrap/` — which necessarily keeps
its *own* state local, since it creates the very backend that main `infra/` depends on.

Run this once (per environment):

```bash
cd infra/bootstrap
terraform init
terraform apply
```

This creates a versioned S3 bucket (`<project>-<environment>-terraform-state`) and a DynamoDB table
(`<project>-<environment>-terraform-lock`) — `chat-app-local-*` with the default vars.

Then point main `infra/` at that backend:

```bash
cd infra
cp backend.hcl.example backend.hcl   # gitignored; edit if you customized project/environment above
terraform init -backend-config=backend.hcl
```

`provider.tf` declares an empty `backend "s3" {}` block — a static backend block can't reference
variables, and the bucket/table don't exist before `bootstrap/` runs, so the actual bucket/key/region/table
are supplied via `-backend-config` instead of being hardcoded.

**What this does and doesn't prove:** the LocalStack run below (single container, single operator) confirms
the S3-backend *mechanism* — init, state read/write, and DynamoDB locking all work end-to-end. It does not
exercise concurrent applies from two different people, since that scenario needs a real shared AWS account
to actually trigger lock contention.

## Running against LocalStack

Requires [LocalStack](https://docs.localstack.cloud/) running locally (the community/free tier is enough
to `apply` a bit under half of this Terraform — see "Known limitation" below for exactly which resources).

```bash
# start LocalStack — pin to a known-working community tag; the `latest` tag now
# requires a LOCALSTACK_AUTH_TOKEN just to boot, even for free-tier features
docker run -d --name localstack -p 4566:4566 localstack/localstack:3.8

# from infra/bootstrap/, once
terraform init
terraform apply

# from infra/
cp backend.hcl.example backend.hcl
terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

The `aws` provider is pre-configured (`provider.tf`) with dummy credentials and every endpoint pointed at
`http://localhost:4566`, so no AWS credentials or account are needed. No `tflocal` wrapper required. Both
the default provider and the `aws.us_east_1` alias (used for ACM/Route53 — see "DNS and TLS" below) set
`s3_use_path_style = true`; without it, S3 bucket creation against LocalStack hangs retrying a malformed
`HEAD /` request instead of erroring, since LocalStack's edge router doesn't resolve virtual-hosted-style
bucket subdomains (`<bucket>.localhost:4566`) the way real S3 does.

To tear everything down:

```bash
terraform destroy                              # from infra/
cd bootstrap && terraform destroy              # from infra/bootstrap/, last (S3 versioned bucket needs
                                                # its object versions deleted first if it still holds state)
```

## Known limitation

Confirmed by actually running `terraform apply` against LocalStack community edition 3.8.1 (ticket 11,
re-confirmed under ticket 25 with the resources added below): several services used here are LocalStack
Pro-tier only and fail with a 501 "not yet implemented or pro feature" error on `apply`, even though they
pass `terraform validate`/`plan`:

- **ECS** — `aws_ecs_cluster`, `aws_ecs_service` (`ecs.tf`)
- **ECR** — `aws_ecr_repository` (`ecs.tf`)
- **RDS** — `aws_db_subnet_group`, `aws_db_instance` (`rds.tf`)
- **ElastiCache** — `aws_elasticache_cluster` (`elasticache.tf`, see ADR-0003)
- **ELBv2** — `aws_lb`, `aws_lb_target_group` (`network.tf`)
- **CloudFront** — `aws_cloudfront_origin_access_control`, `aws_cloudfront_distribution` (`frontend.tf`,
  new finding from ticket 25)

**Not gated**, contrary to what was assumed going into ticket 25 — these applied successfully against the
community tier: S3 (`aws_s3_bucket.frontend` and friends), Route53 (`aws_route53_zone`, records), and ACM
(`aws_acm_certificate`, `aws_acm_certificate_validation`, including its DNS validation round-trip).

**Untested** — `aws_appautoscaling_target`/`aws_appautoscaling_policy` (`autoscaling.tf`) depend on
`aws_ecs_service.backend`, which never gets created (ECS is Pro-gated above), so Application Auto Scaling's
own LocalStack support couldn't actually be exercised; `terraform plan` is the only evidence it's wired up
correctly.

Only VPC/networking (subnets, route tables, security groups, IGW), IAM, CloudWatch Logs, SSM Parameter
Store, S3, Route53, and ACM apply successfully against the community tier. Local *application* testing uses
the plain Postgres/Redis containers from `backend/docker-compose.yml` instead, independent of this
Terraform.

## Known gap: NAT Gateway

Not provisioned. A NAT Gateway costs ~$32+/month running idle, and nothing in this stack would use the
private route today — RDS/ElastiCache don't need internet egress, and ECS still runs in the public subnets
(ticket 02's design, unchanged here). Provisioning an orphaned NAT now would be cost with no payoff. It
ships together with a future "move ECS to private subnets" ticket, not before it — that's the ticket where
it earns its cost.

## Known gap: ALB stays HTTP-only

`dns.tf` gives the frontend TLS via CloudFront (`aliases`/`viewer_certificate` backed by the ACM cert in
`acm.tf`), but the ALB itself gets no listener/cert change — `api.<var.domain_name>` resolves to it over
plain HTTP only. So `<var.domain_name>` (the frontend) is TLS end-to-end, but the API/WebSocket path behind
`api.<var.domain_name>` is not. Adding an HTTPS listener to the ALB would reuse the same ACM certificate;
deliberately out of scope here since ticket 25 was about closing the frontend-hosting/autoscaling/DNS/state
gaps, not the ALB's transport security.

## Frontend hosting

`frontend.tf` provisions a private S3 bucket (no public access) plus a CloudFront distribution reading from
it via Origin Access Control — the bucket itself is unreachable except through CloudFront. Two
`custom_error_response` blocks turn S3's 403/404 (any path that isn't a literal object, e.g.
`/conversations/123`) into a 200 serving `/index.html`, so React Router's client-side routes work on direct
load and refresh.

Build and deploy:

```bash
./infra/scripts/deploy-frontend.sh
# or, against LocalStack:
LOCALSTACK_ENDPOINT=http://localhost:4566 ./infra/scripts/deploy-frontend.sh
```

This runs `npm run build` in `frontend/`, syncs `frontend/dist/` to the bucket (`aws s3 sync --delete`),
and (real AWS only — LocalStack community doesn't support CloudFront, per the gap above) invalidates the
CloudFront cache.

## Container image

`backend/Dockerfile` builds the FastAPI backend (multi-stage, `uv`-managed deps, runs as a non-root user,
`uvicorn app.main:app` on port 8000). Build and push it to `aws_ecr_repository.backend`:

```bash
./infra/scripts/push-backend-image.sh
# or, against LocalStack:
LOCALSTACK_ENDPOINT=http://localhost:4566 ./infra/scripts/push-backend-image.sh
```

Tags the image with `git rev-parse --short HEAD` (not `latest`) so deploys are reproducible/rollback-able —
redeploy a specific build with `terraform apply -var="image_tag=<sha>"`. `var.image_tag` still *defaults* to
`latest` for convenience (first `apply` before any image exists), but the documented push path always uses
the commit SHA.

## Autoscaling

`autoscaling.tf` adds an `aws_appautoscaling_target` for `aws_ecs_service.backend` (`min_capacity = 1`,
`max_capacity = 3`) with two target-tracking policies — `ECSServiceAverageCPUUtilization` and
`ECSServiceAverageMemoryUtilization`, both targeting 70%. `var.backend_desired_count` still sets the
service's *initial* task count at `apply` time; auto scaling takes over adjusting it afterward.
`aws_ecs_service.backend` has `lifecycle { ignore_changes = [desired_count] }` (`ecs.tf`) so a later
`terraform apply` doesn't reset a scaled-up task count back down to `var.backend_desired_count`.

## DNS and TLS

`dns.tf` creates an `aws_route53_zone` for `var.domain_name` (placeholder default: `chat-app.example.com`)
with two alias records: the apex (`var.domain_name`) to CloudFront (frontend, TLS), and
`api.var.domain_name` to the ALB (backend, HTTP-only — see the known gap above). `acm.tf` requests the ACM
certificate CloudFront needs for the custom domain, in `us-east-1` specifically (CloudFront's hard
requirement regardless of `var.aws_region`, via the `aws.us_east_1` provider alias in `provider.tf`), and
validates it via DNS records in that same zone.

Going live against real AWS additionally needs: `var.domain_name` set to an actually-registered domain, and
that domain's registrar pointed at the zone's `route53_name_servers` output (Terraform can't do this last
step — it's at the registrar, outside AWS).

## Validating

```bash
terraform validate   # infra/
terraform validate   # infra/bootstrap/
```

Checks syntax and internal consistency only — doesn't require LocalStack to be running.
