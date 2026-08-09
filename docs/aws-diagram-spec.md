# AWS diagram spec

A written specification for the AWS pieces needed to run the system, meant to
be hand-drawn in DrawIO from this document. Every component below maps 1:1 to
a resource actually provisioned in `infra/*.tf` — this is a diagram of what's
really there, not an aspirational target architecture. Frontend hosting (S3 +
CloudFront), autoscaling, and DNS/TLS landed with ticket 25 (`infra/frontend.tf`,
`infra/autoscaling.tf`, `infra/acm.tf`, `infra/dns.tf`) — there's no longer a
hypothetical piece; everything below is real. For why WebSocket runs inside
the backend container instead of API Gateway, and why Redis is provisioned as
ElastiCache, see [ADR-0001](adr/0001-containerized-websocket-over-api-gateway.md)
and [ADR-0003](adr/0003-redis-pubsub-for-horizontal-scaling.md).

**Out of scope:** `infra/bootstrap/` (S3 bucket + DynamoDB table backing
Terraform's own remote state) isn't shown — it's deployment tooling, not a
piece of the running system.

## Components

| Component | Type | `infra/*.tf` resource | Description |
|---|---|---|---|
| VPC | Networking | `aws_vpc.main` (`network.tf`) | Isolated network for all resources below. |
| Internet Gateway | Networking | `aws_internet_gateway.main` (`network.tf`) | Gives the public subnets a route to the internet. |
| Public subnets (×2) | Networking | `aws_subnet.public` (`network.tf`) | Host the ALB and the ECS tasks (tasks get a public IP for outbound image pulls / SSM). |
| Private subnets (×2) | Networking | `aws_subnet.private` (`network.tf`) | Host RDS and ElastiCache — no direct internet route. |
| Security group: ALB | Networking | `aws_security_group.alb` (`network.tf`) | Allows inbound HTTP (80) from `0.0.0.0/0`. |
| Security group: ECS | Networking | `aws_security_group.ecs` (`network.tf`) | Allows inbound on the backend container port, only from the ALB security group. |
| Security group: RDS | Networking | `aws_security_group.rds` (`network.tf`) | Allows inbound Postgres (5432), only from the ECS security group. |
| Security group: Redis | Networking | `aws_security_group.redis` (`network.tf`) | Allows inbound Redis (6379), only from the ECS security group. |
| Application Load Balancer | Compute (edge) | `aws_lb.main` (`network.tf`) | Public entry point, in the public subnets. Terminates HTTP; forwards to the backend target group. **HTTP-only — no listener/cert of its own** (see Known gap under Connections). |
| ALB target group + listener | Compute (edge) | `aws_lb_target_group.backend`, `aws_lb_listener.http` (`network.tf`) | Routes port-80 traffic to backend ECS tasks; health-checks `/health`. |
| ECS Cluster | Compute | `aws_ecs_cluster.main` (`ecs.tf`) | Fargate cluster hosting the backend service. |
| ECS Service (backend) | Compute | `aws_ecs_service.backend` (`ecs.tf`) | Runs the backend as Fargate tasks in the public subnets, registered with the ALB target group. Desired count now managed by Application Auto Scaling, not a fixed value (`lifecycle.ignore_changes = [desired_count]`). |
| ECS Task Definition (backend) | Compute | `aws_ecs_task_definition.backend` (`ecs.tf`) | One container (`backend`), image from ECR, env `FRONTEND_ORIGIN` + secrets pulled from SSM at launch. |
| Application Auto Scaling (target + CPU/memory policies) | Compute (scaling) | `aws_appautoscaling_target.backend`, `aws_appautoscaling_policy.backend_cpu`, `aws_appautoscaling_policy.backend_memory` (`autoscaling.tf`) | Target-tracking scaling on the ECS service, 1–3 tasks, 70% target on both CPU and memory. |
| ECR repository | Compute (image registry) | `aws_ecr_repository.backend` (`ecs.tf`) | Stores the backend Docker image the task definition pulls from. |
| CloudWatch Log Group | Observability | `aws_cloudwatch_log_group.backend` (`ecs.tf`) | Backend container stdout/stderr, 14-day retention, via the `awslogs` driver. |
| IAM role: ECS task execution | IAM | `aws_iam_role.ecs_task_execution` (`ecs.tf`) | Assumed by ECS to launch tasks: pulls the image, writes logs, and reads the SSM secrets below (`AmazonECSTaskExecutionRolePolicy` + an inline `ssm:GetParameters` / `kms:Decrypt` policy). |
| SSM Parameters (SecureString ×4) | Config/secrets | `aws_ssm_parameter.{database_url,redis_url,jwt_secret_key,webhook_hmac_secret}` (`rds.tf`, `elasticache.tf`, `ecs.tf`) | Encrypted secrets injected into the backend container as env vars at task launch — never baked into the image. |
| RDS Postgres instance | Data | `aws_db_instance.postgres` (`rds.tf`) | Single instance, private subnets, not publicly accessible. Holds users/conversations/messages. |
| ElastiCache Redis cluster | Data | `aws_elasticache_cluster.redis` (`elasticache.tf`) | Single node, private subnets. Pub/sub backbone for cross-instance WebSocket delivery — see `docs/architecture.md`. |
| S3 bucket (frontend) | Frontend hosting | `aws_s3_bucket.frontend` (`frontend.tf`) | Holds the built frontend static assets (`frontend/dist`). Fully private — `aws_s3_bucket_public_access_block` blocks all public access; only readable via the CloudFront OAC below. |
| CloudFront distribution | Frontend hosting | `aws_cloudfront_distribution.frontend` (`frontend.tf`) | CDN in front of the S3 bucket, serves the SPA to browsers over HTTPS. SPA-aware: 403/404 from S3 are rewritten to `/index.html` (200) so client-side routes like `/conversations/123` resolve. |
| CloudFront Origin Access Control | Frontend hosting | `aws_cloudfront_origin_access_control.frontend` (`frontend.tf`) | SigV4-signs CloudFront's requests to S3; the S3 bucket policy only trusts requests signed this way, from this distribution's ARN. |
| ACM certificate (frontend) | Certificate/TLS | `aws_acm_certificate.frontend`, `aws_acm_certificate_validation.frontend` (`acm.tf`) | DNS-validated TLS cert for `var.domain_name`, used by the CloudFront distribution. Must be requested in `us-east-1` regardless of the stack's home region — CloudFront's requirement, not this project's choice. |
| Route53 hosted zone | DNS | `aws_route53_zone.main` (`dns.tf`) | Hosted zone for `var.domain_name`. |
| Route53 record: apex → CloudFront | DNS | `aws_route53_record.frontend` (`dns.tf`) | `var.domain_name` (e.g. `chat-app.example.com`) alias-routed to the CloudFront distribution. |
| Route53 record: `api.` → ALB | DNS | `aws_route53_record.alb` (`dns.tf`) | `api.<var.domain_name>` alias-routed to the ALB. Plain HTTP — see Known gap below. |

## Groupings

- **VPC boundary** around the backend compute/data path only.
  - **Public subnets** subgroup: ALB, ECS tasks.
  - **Private subnets** subgroup: RDS, ElastiCache.
- **IAM / SSM** sits outside the VPC boundary as a side group, connected to
  the ECS task with dashed "grants" or "reads" arrows rather than network
  arrows — control-plane relationships, not on-the-wire traffic.
- **Application Auto Scaling** likewise sits outside the VPC boundary, next
  to IAM/SSM — a dashed "adjusts desired count" arrow into the ECS service,
  not on-the-wire traffic.
- **CloudWatch Logs** and **ECR** sit outside the VPC boundary (both are
  regional AWS services the ECS task talks to over AWS's network, not
  through the VPC's own routing).
- **Global edge / frontend** group, drawn separate from the VPC box (these
  are global services, not VPC-scoped): S3 bucket, CloudFront, Origin Access
  Control, ACM certificate, Route53 hosted zone + its two records. The
  Route53 → ALB record is the one edge in this group that reaches back into
  the VPC (to the ALB).

## Connections

| From | To | Label | Notes |
|---|---|---|---|
| Browser | Route53 (`api.<domain_name>`) → ALB | HTTP :80 | Plain HTTP end to end. |
| ALB | ECS Service (target group) | HTTP :backend_container_port | |
| ECS task | RDS Postgres | :5432 | |
| ECS task | ElastiCache Redis | :6379 | |
| ECS task execution role | SSM Parameters | `ssm:GetParameters` (+ `kms:Decrypt`) | Control-plane, dashed. |
| ECS task execution role | ECR repository | pulls image | Control-plane, dashed. |
| ECS task | CloudWatch Log Group | writes logs (`awslogs` driver) | Control-plane, dashed. |
| Application Auto Scaling | ECS Service | adjusts desired count (target-tracking, CPU + memory, 70%) | Control-plane, dashed. |
| Browser | Route53 (`<domain_name>`) → CloudFront | HTTPS, static asset requests | |
| CloudFront | S3 bucket (frontend) | origin fetch, SigV4-signed via OAC | |
| Browser (app served from CloudFront, `https://<domain_name>`) | ALB (`http://api.<domain_name>`) | REST + WebSocket | **Cross-origin now**, not same-origin — the frontend and API live on different subdomains once real DNS is in play, so this relies on the backend's CORS config (`FRONTEND_ORIGIN` env var) rather than same-origin. Flag this edge distinctly (e.g. orange/warning color) — see Known gap below. |

**Known gap — mixed content:** the frontend is served over HTTPS
(CloudFront/ACM), but `api.<domain_name>` is HTTP-only (`network.tf`'s ALB
listener has no TLS). A browser on the HTTPS frontend calling the HTTP API
will hit mixed-content blocking. `infra/README.md`'s "Known gap: ALB stays
HTTP-only" tracks this — an HTTPS listener on the ALB would reuse the same
ACM cert but isn't wired up yet. Mark the last connection row above visibly
(e.g. a warning color/icon) rather than drawing it as a plain solid line like
the others.
