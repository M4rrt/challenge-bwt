# 20 — The drain runs in production

**What to build:** The drain process exists in the deployed environment, not only in `docker-compose.yml`. Until it does, a production deploy of the service after ticket 07 accepts messages, stores them, returns `201` — and delivers nothing in realtime, silently, because the request no longer publishes and nothing is running to publish on its behalf.

This is the deployment consequence of [07](07-outbox-drain-and-fan-out-addresses.md), and it is the kind of gap that does not announce itself: every HTTP test passes, every message is durable, and the only symptom is that live screens stop updating. `infra/ecs.tf` defines one task definition and one service, both named `backend`. The drain is a second long-running process with the same image, the same secrets and no load balancer, so it is a second task definition and a second service rather than a second container in the existing task — sharing a task would tie the drain's replica count to the API's, and the two scale on entirely different signals.

**Blocked by:** 07.

**Status:** ready-for-agent

- [ ] A deployed environment runs `python -m app.drain` as a long-running process, separate from the API service
- [ ] It reads the same database and Redis, from the same SSM parameters, and is not reachable from any load balancer or the public internet
- [ ] It survives its own crash: the orchestrator restarts it, the way `restart: unless-stopped` does locally
- [ ] Running more than one replica is safe and is stated to be safe — `drain_once` takes one row per transaction with `FOR UPDATE SKIP LOCKED`, so replicas share a backlog rather than publishing it twice
- [ ] Its logs reach the same destination as the API's, because a drain that has stopped publishing says so in a log and nowhere else until ticket 18 lands
- [ ] `infra/README.md` says what breaks when the drain is not running, so the next person to read it does not have to infer it from ticket 07

## Notes

The free-tier LocalStack limitation recorded in [ADR-0003](../../docs/adr/0003-redis-pubsub-for-horizontal-scaling.md) and `infra/README.md` applies here unchanged: ECS is Pro-tier-gated, so this is validated with `terraform plan` rather than `terraform apply`, exactly as the backend service already is.

Autoscaling is deliberately not in scope. The API scales on request load; the drain's load is the outbox's pending depth, which is not a metric anything publishes yet — [18](18-operational-surface.md) is what exposes it. One replica, restarted on failure, is the honest starting point, and the pending age is what would tell an operator it is not enough.
