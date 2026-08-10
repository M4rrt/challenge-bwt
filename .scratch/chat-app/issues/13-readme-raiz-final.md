# 13 — README raiz final

**What to build:** The root `README.md` updated as the challenge's "Entrega" section requires — run instructions, technical decisions/trade-offs, and what would be done differently with more time. The final step, once everything else exists to describe.

**Blocked by:** 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12.

**Status:** done

- [x] Instructions to run frontend, backend, and infra locally (linking to each layer's own README)
- [x] Summary of key technical decisions and trade-offs, drawing from `docs/adr/` and `docs/decisions.md` rather than duplicating them
- [x] "What I'd do differently with more time" section, covering at minimum the items already logged in `docs/decisions.md` (extras not pursued, offline/unread tracking, single-instance-if-Redis-were-dropped scenario discussed but not taken)

## Comments

Entire root `README.md` rewritten: the original challenge prompt (everything from `## Visão Geral` down) was dropped per explicit user request, leaving only the delivery content (how to run, decisions/trade-offs, what I'd do differently), sourced from `docs/adr/`, `docs/decisions.md`, and a second pass over every ticket's own `## Comments`/`## Answer` section (dispatched to a subagent — 25 tickets is too much to hold in-line) to catch decisions that never made it into `docs/decisions.md` (e.g. refresh token hashed with SHA-256 not bcrypt and not rotated on use, the webhook not checking `conversation_id` participant-membership, and `Conversation.participant_user_ids` ordering being an accidental side effect of a Postgres index rather than an explicit `ORDER BY` — all from ticket 24/07/23 respectively). Layer-specific findings from that pass were pushed down into `backend/README.md`, `frontend/README.md`, and `infra/README.md` instead of duplicated at the root, keeping root at the architecture/trade-off level and layers at the operational level.

Also linked the previously-orphaned `docs/aws-architecture.drawio` and `docs/aws-diagram-spec.md` from the root README — they existed (ticket 12) but nothing pointed to them, and the challenge brief calls out DrawIO by name.

Found while starting this ticket: ticket 12 (architecture diagrams) was already implemented and committed on local `main` (`2828b3b`), but that commit hadn't been pushed to `origin/main` yet — this ticket's worktree, created from `origin/main`, was missing it. Fixed by rebasing the worktree branch onto local `main` before writing anything, rather than redoing ticket 12's work or leaving the "Blocked by: ... 12" dependency unmet.

Per explicit user instruction, all root/layer README prose is in Portuguese; `docs/adr/`, `docs/decisions.md`, and the architecture docs were deliberately left in English (asked, user declined translating those).
