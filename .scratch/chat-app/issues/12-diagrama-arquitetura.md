# 12 — Diagrama de arquitetura

**What to build:** A diagram explaining the data flow and, separately, the AWS pieces required to run the system — requirement 5 of the challenge.

**Blocked by:** 02.

**Status:** ready-for-agent

- [ ] `docs/architecture.md` with a Mermaid diagram showing the request/message flow (client → API/WS → Postgres/Redis → other clients; webhook → same path)
- [ ] A second diagram (or section) covering all AWS pieces needed to run the system (ECS, RDS, ElastiCache, ALB, networking, SSM), matching what's in `infra/`
- [ ] Diagram vocabulary matches `CONTEXT.md` and the ADRs (e.g. reflects ADR-0001's in-app WebSocket, not API Gateway)
