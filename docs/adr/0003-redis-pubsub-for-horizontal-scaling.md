# Redis pub/sub for horizontal WebSocket scaling

**Status:** accepted

The challenge overview names "escalabilidade" as an evaluation focus, not just a nice-to-have. A single backend instance can broadcast messages to WebSocket clients using an in-memory registry (`conversation_id → connections`), but that breaks the moment there's more than one instance behind the load balancer — a client connected to instance A never receives a message that arrived at instance B.

We chose to build this out now rather than defer it: on every message send and webhook event, the backend publishes to a Redis channel keyed by `conversation_id`; every instance runs a subscriber that forwards matching messages to its local WebSocket connections. Locally, Redis runs as a plain container in `docker-compose`. In AWS, it's provisioned as ElastiCache via Terraform.

**Known limitation:** ElastiCache is a LocalStack Pro-tier service, so `terraform apply` against LocalStack won't provision it on the free tier — confirmed by actually running `terraform apply` in ticket 11, which also found this isn't unique to ElastiCache (ECS, ECR, RDS, and ELBv2 are equally Pro-tier-gated; see `infra/README.md`'s "Known limitation" section for the full picture). The Terraform module is still written and validated with `terraform plan`; local *application* testing uses the plain Redis container directly, independent of LocalStack.
