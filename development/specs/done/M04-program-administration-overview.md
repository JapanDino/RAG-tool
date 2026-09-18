# M04 — Aggregate program administration overview

Status: complete

## User outcome

An organization administrator can see which saved program maps need a
methodological check, understand the exact structural counts behind that state,
and open the selected program's evidence-backed audit without seeing teacher or
student activity.

## Users and permissions

- Administrator: read one bounded overview for an organization and open an
  existing program map/audit.
- Methodologist and program designer: keep their current program map access but
  do not receive the organization-wide administration overview in this slice.
- Instructor and student: no program portfolio access.
- The overview changes no program, course, Canvas, membership, learner, or staff
  data and records no personnel judgement.

## Context and evidence

- `development/STATUS.md` names the aggregate administration view as the next
  M04 batch.
- `development/ROADMAP.md` requires an aggregate administration view to close
  the current Program Intelligence gate.
- `development/PRODUCT.md` allows aggregate program health but forbids automatic
  personnel or disciplinary decisions.
- `development/ARCHITECTURE.md` requires administrative analytics to stay
  aggregated unless a documented operational purpose permits drill-down.
- `development/design/EXPERIENCE.md` separates operational overview from
  pedagogical quality and requires aggregate signals to drill into evidence.
- The completed program-audit spec defines the deterministic finding rules and
  the existing evidence-first drill-down.

## Scope

- Add one administrator-only, organization-scoped endpoint that returns bounded
  structural counts for active programs.
- Count canonical courses, competencies, competencies with any valid declared
  course contribution, and competencies with a valid assessed contribution.
- Derive a plain structural state per program: route not started, mapping needs
  review, assessment declarations need review, or all competencies have a
  declared assessment.
- Add `/workspace/programs/overview` as a calm portfolio ledger, not a KPI
  dashboard or quality ranking.
- Link every program row to the existing selected program map. Automatically
  open its bounded audit preview when the route contains competencies; a route
  that has not started opens the map without promising unavailable evidence.
- Add the administration overview entry point to the role-aware workspace.

## Non-goals

- A score, league table, pass/fail decision, accreditation judgement, or staff
  performance indicator.
- Program comparison by teacher, student, grade, submission, conversation,
  completion, demographic attribute, cost, latency, or model usage.
- Persisted review decisions, assignments, comments, notifications, trends, or
  snapshots.
- Semantic prerequisite/duplication inference, model calls, prompts, retrieval,
  or new audit rules.
- Editing programs from the overview, Canvas writes, LTI/OAuth, or deployment.

## User flow

1. An administrator opens “Обзор программ” from the organization workspace.
2. A compact summary states how many saved maps and competencies were analyzed.
3. Alphabetical program rows expose exact course/mapping/assessment counts and
   one factual next-check label.
4. The administrator chooses “Открыть карту и основания”; an unstarted route
   uses the honest action “Открыть карту”.
5. The selected program opens in the existing curriculum workspace and, when
   there is something to inspect, its bounded “Контрольная рейка” audit loads
   automatically.
6. The link carries the exact organization and program identifiers. A stale or
   cross-organization target fails closed instead of selecting another program.

## UX contract

Subject: a school administrator reviewing a portfolio of curriculum maps at a
methodical dispatch desk. The single job is to choose the next map for a
methodologist to inspect, not to judge a program or person.

- Reuse Ink `#172033`, Slate `#536078`, Canvas `#F6F8FC`, Paper `#FFFFFF`,
  Learning blue `#356AE6`, Evidence teal `#178C7E`, Review amber `#C77B16`, and
  Risk red `#C34E57`.
- Signature: “Сводная нить” — each program is a ruled ledger row with one
  segmented route line for assessed, mapped-only, and unmapped competencies.
  The line encodes declared map structure and never becomes a score gauge.
- Keep totals in one sentence and avoid KPI cards, leaderboards, rank numbers,
  trend arrows, celebratory success color, or red/green quality verdicts.
- Alphabetical order is stable and does not imply priority or quality.
- Desktop rows align title, factual route state, thread, counts, and action;
  mobile rows stack without horizontal page scrolling.
- Primary row action: “Открыть карту и основания”; for a route without
  competencies: “Открыть карту”. Refresh: “Обновить сводку”. Retry: “Повторить
  загрузку”.
- Loading preserves the ledger frame. Empty, error, permission, truncated,
  not-started, mapping-gap, assessment-gap, and all-declared states explain what
  is and is not known.
- Rows and links have visible keyboard focus. Loading uses `aria-busy`; summary
  updates use `aria-live`; the segmented thread has an exact accessible label.
- Program titles/descriptions render only as plain text.

## Data and API

- No migration. Reuse `Program`, `ProgramCourse`, `Competency`,
  `CourseContribution`, and `Course`.
- `GET /organizations/{organization_id}/program-administration-overview` is
  administrator-only at both route and service boundaries.
- Analyze at most 200 active programs, ordered by title then ID. Return an
  explicit `analysis_truncated` flag when more exist.
- Use bounded grouped queries across returned program IDs; do not call the full
  per-program audit in a loop.
- A valid mapped/assessed declaration must join the same program competency, a
  canonical program course, and a course in the same organization.
- Each item returns program identity/version/update time, exact structural
  counts, a route-state code/label, confidence language “Факт по сохранённой
  карте”, and `review_status=not_reviewed`.
- Totals describe only returned programs and declare this boundary in the UI.
- Existing program list/map/audit/authoring responses remain backward compatible.

## Security and privacy

- Route and service authorization independently require an active administrator
  membership in the requested organization; denied roles receive non-disclosing
  404 responses.
- The response contains no users, teachers, students, memberships, grades,
  submissions, conversations, expected answers, evidence excerpts, prompts,
  provider metadata, secrets, or Canvas tokens.
- Program text is untrusted data and is never rendered as HTML or interpreted as
  instructions.
- The overview is read-only and creates no audit/change event.
- Copy explicitly states that structural declarations are not evidence of
  educational quality or staff performance.

## Acceptance criteria

- [x] Administrator receives a deterministic bounded alphabetical overview;
  all other roles and cross-organization access are non-disclosing.
- [x] Counts include only canonical same-organization course contributions and
  expose mapping/assessment gaps without a numeric quality score.
- [x] Overview actions pin the requested organization; a missing explicit
  program never falls back to another readable program or starts its audit.
- [x] The API uses grouped bounded queries, explicit truncation, no writes, and
  serializes no people, learner activity, expected answers, or model metadata.
- [x] The workspace provides an administrator entry point and a one-action
  drill-down to the selected program's existing evidence-backed audit.
- [x] Loading, populated, empty, error/retry, permission, truncated, not-started,
  mixed-gap, all-declared, desktop/mobile, keyboard, and clean-console states
  pass.
- [x] Full backend regressions, frontend lint/build, repo-wide pre-commit, and
  general/product-UX batch reviews pass.

## Test plan

- Service/API: role matrix, other-organization denial, stable alphabetical
  order, empty organization, every route state, canonical-course/org filtering,
  200-program truncation, no writes, and content-safe response.
- Frontend/browser: administrator entry, loading frame, populated ledger, empty,
  retained-data error/retry, truncated warning, deep-link audit, keyboard focus,
  stale deep-link denial, 1440 × 900, 390 × 844, no overflow, and clean console.
- Regression: full backend suite, frontend lint/build, and repo-wide pre-commit.

## Batch review

Closed on 2026-07-17. General quality and product/UX reviewers reported no
remaining P0/P1 findings after targeted rechecks. The final gate passed 92
backend tests, frontend lint and production build, repo-wide pre-commit, and
desktop/mobile browser checks including exact and stale deep links.
