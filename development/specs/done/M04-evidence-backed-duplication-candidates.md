# M04 — Evidence-backed duplication candidates

Status: complete

## User outcome

A methodologist can see when the same explicitly declared learning stage for a
program competency appears in more than one course, inspect every saved basis,
and decide whether the repetition is intentional spiral learning or needs a
curriculum change.

## Users and permissions

- Methodologist, program designer, and administrator: run and inspect the
  existing read-only program audit preview with duplication candidates.
- Instructor and student: no program-level audit access.
- The signal creates no review decision and changes no program, course, Canvas,
  learner, teacher, or organization data.

## Context and evidence

- `development/STATUS.md` names evidence-backed duplication candidates as the
  next M04 batch.
- `development/ROADMAP.md` and `development/PRODUCT.md` require inspectable
  duplication visibility across courses without opaque scores.
- `development/ARCHITECTURE.md` keeps the current program audit as a bounded,
  read-only projection and forbids invented prerequisite relations.
- `development/design/EXPERIENCE.md` requires curriculum signals to drill into
  evidence and confidence to be expressed as actionable language.
- The completed program-audit preview already provides canonical course order,
  stable findings, evidence safety, truncation, and the “Контрольная рейка” UI.

## Scope

- Extend the existing program audit preview with `duplication_check`.
- Emit one candidate per competency only when the same learning stage,
  `introduced` or `developed`, is explicitly declared in at least two distinct
  canonical courses.
- Treat `introduced` followed by `developed` as progression, not duplication;
  repeated `assessed` declarations are outside this slice.
- Show only the contributions for repeated learning stages, ordered by the
  canonical course route, with their current evidence state.
- Add a watch-level finding to the existing inspection rail and evidence sheet.

## Non-goals

- Semantic similarity between different competencies, objectives, assignments,
  pages, or course text.
- A redundancy verdict, recommendation to remove a course, quality score,
  ranking, or personnel judgement.
- Model calls, embeddings, retrieval, prompts, persistence, review workflow,
  notifications, Canvas writes, LTI/OAuth, or deployment.
- Prerequisite inference or learner-specific progression.

## User flow

1. A permitted user opens a program map and runs “Проверить маршрут”.
2. The existing bounded preview lists “Сверить повтор” when one learning stage
   is declared in several courses.
3. The user opens the candidate and sees the competency, repeated stage, exact
   course stops, rationale, evidence state, confidence, and review boundary.
4. The copy asks for a methodical decision and explicitly allows intentional
   spiral learning as a valid explanation.

## UX contract

- Keep “Контрольная рейка” and the existing finding/evidence hierarchy; do not
  add a dashboard, score, comparison table, or separate AI surface.
- `duplication_check` uses the amber watch treatment, marker `↔`, and label
  “Сверить повтор”; red remains reserved for factual missing links.
- The evidence heading states the structural repetition, while detail states
  that repetition can be intentional and is not proof of redundancy.
- Launcher, summary, empty, and boundary copy name repeated declared stages and
  the inability to prove semantic duplication.
- Desktop and mobile retain the existing rail/sheet behavior, keyboard buttons,
  visible focus, `aria-pressed`, focus transfer, `aria-live`, `aria-busy`, and
  plain-text rendering of untrusted program/course content.

## Data and API

- No migration and no new endpoint. Reuse `GET
  /programs/{program_id}/audit-preview`.
- Add `duplication_check` to `ProgramAuditKind` and audit counts; existing
  response fields remain unchanged and clients may ignore the additive field.
- Generate a candidate only when all declared contributions for the analyzed
  competency are inside the bounded canonical course/contribution window.
- Candidate key is stable: `duplication_check:{competency_id}`.
- Confidence is `medium`, attention is `watch`, review status is
  `not_reviewed`, and the label is “Явный повтор — нужна методическая сверка”.
- Existing competency, contribution, finding, and evidence limits apply.
  `evidence_truncated` explicitly marks a finding whose basis list exceeds the
  existing per-finding evidence limit.

## Security and privacy

- Existing route and service role/scope checks remain mandatory and
  non-disclosing.
- The response exposes no people, grades, submissions, conversations, expected
  answers, provider metadata, prompts, credentials, or learner activity.
- Imported rationale and evidence are untrusted plain text, never instructions
  or HTML.
- Evidence ownership is revalidated by the existing resolver; missing sources
  remain visible as missing and never become invented support.
- The preview is read-only and writes no audit/change event.

## Acceptance criteria

- [x] A repeated `introduced` or `developed` stage across distinct canonical
  courses produces one deterministic watch-level candidate with ordered evidence.
- [x] Normal `introduced` → `developed` progression and repeated assessment alone
  do not produce a duplication candidate.
- [x] Incomplete bounded data suppresses the candidate; truncation remains
  explicit and cannot imply absence of duplication.
- [x] Evidence, confidence, review state, and intentional-spiral boundary are
  visible without a redundancy verdict or score.
- [x] Existing authorization, content safety, stable ordering, other findings,
  map, authoring, overview, tutor, course, and Canvas-read workflows regress.
- [x] Backend tests, frontend lint/build, repo-wide pre-commit, browser desktop/
  mobile/state checks, and general/product-UX/RAG reviews pass without P0/P1.

## Test plan

- Service/API: repeated introduced, repeated developed, progression-only,
  assessed-only, multiple repeated stages, canonical evidence order, missing
  evidence, truncation suppression, stable key/count, no writes, content safety,
  and role matrix regression.
- Frontend/browser: launcher copy, populated duplicate candidate, selection,
  evidence sheet, intentional-spiral boundary, no-finding copy, loading/error/
  truncated regression, 1440 × 900, 390 × 844, keyboard, overflow, and console.
- Regression: focused/full pytest, frontend lint/build, repo-wide pre-commit,
  and `git diff --check`.

## Batch review

Closed on 2026-07-17. General quality, product/UX, and RAG/evidence reviewers
reported no P0/P1 findings. The final gate passed 92 backend tests, focused
program tests, frontend lint and production build, repo-wide pre-commit, and
desktop/mobile browser checks. Deferred validation is product-level: measure on
real anonymized maps how often a candidate is an intentional spiral versus a
repeat that methodologists choose to change.
