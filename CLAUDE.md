## Agent skills

### Issue tracker

Issues and specs live as markdown files under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default label vocabulary (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root `CONTEXT.md` + `docs/adr/`. See `docs/agents/domain.md`.

## Rules
Read files before writing. No `any` in TypeScript. No over-engineering. Test once.

## Behavior
when not using a mattpocock skill, provide short, direct answers. No introductions, concluding summaries, or line-by-line explanations. Deliver only the code or the result—nothing else.

Use fluid prose for explanations—avoid excessive bullet points and unnecessary bold text. Reserve lists for genuinely distinct items.

Never speculate about code you haven't read. Read the file before answering any questions about it.

When making an assumption, state what is being assumed and why, and ask if the assumption is correct.

## TDD
Strictly follow the Red → Green → Refactor cycle. Never implement code without a failing test first. Work in small increments—one behavior per cycle. If requirements are ambiguous, ask before writing the test.

Structure of each cycle:

**RED** — behavior to implement + failing test + reason for failure.
**GREEN** — minimum code to make the test pass.
**REFACTOR** — improvements without changing behavior.
**STATUS** — behaviors covered + next simplest behavior.

## Commits
Never commit without asking first and getting explicit confirmation — even when a skill's own instructions say to commit (e.g. `/implement`'s "commit your work" step). Finish the work, then ask.

use Conventional Commits: `<type>[(scope)]: <descrição>`. Types: `feat`, `fix`, `refactor`, `test`, `chore`, `docs`, `perf`, `ci`, `build`, `style`, `revert`. Breaking change: `!` on prefix or `BREAKING CHANGE:` on footer.
