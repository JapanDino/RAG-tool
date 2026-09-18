# Start prompt for the online Codex session

> Historical prompt. Do not execute the completed slice below. For continuation,
> use `AURUS_HANDOFF.md` and the current `development/STATUS.md` instead.

Copy the text below into the first task after the prepared branch is visible in
the online checkout.

---

Continue the RAG-tool project from the current repository state.

First read `AGENTS.md`,
`development/specs/active/M05-letovo-embedded-course-companion.md`, the
`Current batch`, `Next batch`, and `External blockers` sections of
`development/STATUS.md`, and
`development/handoffs/ONLINE_CODEX_HANDOFF.md`. Treat them as the source of
truth in that order. Before editing, confirm that the active branch contains
the exact-session `/course-map`, `/canvas-companion`, the local Canvas
simulator, and the 0033-0038 LTI/OAuth migrations. If they are absent, stop and
report that the wrong or incomplete branch was opened.

Implement only the next vertical slice: deterministic development-only,
idempotent, secret-free bootstrapping of one synthetic LTI registration and
exact course binding for each simulator fixture (`demo-ai` and `demo-review`),
then automate the complete simulator dashboard -> signed learner launch ->
embedded companion -> selected module -> module-scoped tutor flow for both
fixtures at desktop and mobile sizes.

Preserve all existing security and UX contracts. Use synthetic data only. Do
not contact or mutate the school Canvas, do not deploy, do not redesign the
completed companion, and do not add production shortcuts or hard-coded guessed
database IDs. Keep Canvas-like chrome outside the Workshop Route tool frame.
Every automated finding and answer must retain evidence, confidence/review
state where applicable, exact-course isolation, and safe abstention.

Run focused tests while working. At the batch boundary run full pytest,
frontend lint/build, repo-wide pre-commit, `git diff --check`, and browser QA for
both fixtures, keyboard use, clean console, no horizontal overflow, and bounded
failure states. Use the three reviewer instructions in `development/agents/`
only after implementation, fix P0/P1 findings, run one targeted recheck, and
update `development/STATUS.md` once. Do not commit or push unless I explicitly
ask.

Work autonomously until this vertical slice is complete or a genuine external
blocker is reached.

---
