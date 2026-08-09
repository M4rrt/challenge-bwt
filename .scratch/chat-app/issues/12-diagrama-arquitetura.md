# 12 — Diagrama de arquitetura

**What to build:** A diagram explaining the data flow and, separately, the AWS pieces required to run the system — requirement 5 of the challenge.

**Blocked by:** 02.

**Status:** done

- [x] `docs/architecture.md` with a Mermaid diagram showing the request/message flow (client → API/WS → Postgres/Redis → other clients; webhook → same path)
- [x] A second diagram (or section) covering all AWS pieces needed to run the system (ECS, RDS, ElastiCache, ALB, networking, SSM), matching what's in `infra/` — delivered as `docs/aws-diagram-spec.md`, a written spec for hand-drawing in DrawIO (see Comments)
- [x] Diagram vocabulary matches `CONTEXT.md` and the ADRs (e.g. reflects ADR-0001's in-app WebSocket, not API Gateway)

## Comments

**Grilling session, paused mid-way — resume before implementing.** Decided so far:

1. **Two separate deliverable files**, not one file with two sections:
   - `docs/architecture.md` — data-flow diagram, real Mermaid, rendered inline (ticket's explicit requirement, kept as-is).
   - `docs/aws-diagram-spec.md` — a written specification (components, groupings, connections, labels) for the AWS piece, **not** a rendered diagram. The user will hand-draw it in DrawIO themselves from this spec — Claude can't operate a GUI drawing tool. This follows the original challenge text, which suggests DrawIO specifically for the AWS diagram (data-flow diagram was left tool-agnostic).

2. **Data-flow diagram (`docs/architecture.md`) — Mermaid `flowchart`/`graph`**, not `sequenceDiagram`. Reason: client (REST/WS) and webhook are two entry points that need to converge into the same downstream path (API → Postgres + Redis pub/sub → other clients); a flowchart shows that convergence naturally, a sequence diagram would need to be split in two.

3. **Data-flow diagram includes both pub/sub channels**, not just the conversation one:
   - `conversation:{id}` channel — chat messages, existing ticket wording ("other clients").
   - `user:{id}` channel — cross-conversation activity indicator (ticket 17).
   Both are real, distinct paths in `backend/app/services/realtime.py` (two `ConnectionManager` maps, two channel patterns); omitting the user channel would under-document the actual system.

4. **AWS spec includes a hypothetical frontend hosting piece (S3 + CloudFront)** even though `infra/*.tf` provisions backend-only (no frontend hosting Terraform exists today). User explicitly chose to include it over the recommended "match infra/ exactly" option.
5. **Hypothetical S3/CloudFront visually distinguished** from real Terraform-backed resources in the DrawIO spec: dashed border + explicit "not in infra/, hypothetical" note.
6. **AWS spec includes ECR, CloudWatch Logs, and the IAM task-execution role** as explicit entries, even though the ticket's example list omits them — they're real resources in `infra/ecs.tf`, so the spec stays faithful to what's actually provisioned.
7. **AWS spec format: table of components (name/type/description) + explicit connection list** (source → destination, label) — easiest to translate 1:1 into DrawIO.

Grilling resumed and closed — all decisions made, proceeding to implementation.

**2026-08-09 — update after ticket 25 merged.** `main` picked up
`infra/frontend.tf`, `infra/autoscaling.tf`, `infra/acm.tf`, `infra/dns.tf`
(S3+CloudFront, target-tracking autoscaling, ACM + Route53) — merged into
this branch. This supersedes decisions 4/5 above: S3/CloudFront are no
longer hypothetical, so the "hypothetical" framing and dashed-border
convention were dropped from `docs/aws-diagram-spec.md` in favor of real
component rows, plus new rows for autoscaling, ACM, and Route53. Also added
`docs/aws-architecture.md`, a Mermaid rendering of the spec (user-requested,
not part of the original decision 1 — the written spec stays authoritative
for the DrawIO hand-draw). One thing the infra update surfaced: the previous
"same origin as today" assumption for the frontend→ALB hop no longer holds
once real DNS is in play (`domain_name` vs `api.domain_name` are different
origins), and the ALB is still HTTP-only against an HTTPS frontend
(`infra/README.md`'s "Known gap: ALB stays HTTP-only") — both files now flag
that connection distinctly instead of drawing it like the others.
