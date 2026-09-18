# B07A Program route brief

Status: done

## User outcome

A methodologist, program designer, or administrator opens a selected program
and asks the assistant where to begin the methodological review. The assistant
returns one bounded, read-only route brief derived from aggregate map counts
and the current deterministic program audit, with evidence status, review
state, uncertainty, and a direct handoff to the existing audit surface.

## Users and permissions

- Methodologist: inspect a route brief and open the evidence review.
- Program designer: same read-only assistant outcome; existing authoring rights
  remain separate.
- Administrator: same program brief; organization health tools follow in later
  B07 slices.
- Instructor, student, anonymous, inactive, wrong-organization, and stale
  program contexts receive non-disclosing denial.

## Context and evidence

- `development/AI_CANVAS_AGENT_PLAN.md` B07.
- `development/agent/API_CONTRACT.md` and `TOOL_CATALOG.md`.
- Existing program map, audit preview, prerequisite, and portfolio services.
- Workshop Route in `development/design/DESIGN_SYSTEM.md`.
- B07 remains offline-capable and will later enter self-hosted Canvas Letovo
  through the approved organization/account navigation and identity boundary.

## Scope

- Issue bounded, signed program references for the authenticated organization.
- Execute `program.inspect_map.v1` through the existing agent state machine.
- Return a concise current-map summary and at most three review priorities.
- Add the route brief to the selected program workspace with loading, empty,
  stale, error/retry, success, and keyboard-focus behavior.

## Non-goals

- No generative review note, automatic map edit, Canvas write, student data,
  grades, transcripts, teacher ranking, or cross-program comparison.
- No production Canvas/SSO deployment or research benchmark in this slice.
- No administrator adoption/runtime dashboards yet.

## User flow

1. The user selects an authorized program.
2. The user chooses `Собрать маршрут проверки`.
3. The assistant rechecks the signed program reference, organization, role,
   exact saved-map version, and a content-free digest of the visible current
   audit result.
4. The result names one next review step and hands off to the existing evidence
   panel; nothing is written.

## UX contract

- Single job: choose where to start reviewing the selected program.
- Continue Workshop Route rather than adding a chat window.
- Signature element: a `route compass` that converts the current saved program
  structure into one start marker and a short evidence trail.
- Use plain Russian and label the result as a review route, not a quality score.
- Desktop and mobile expose idle, loading, empty, result, stale, error/retry,
  permission, and program-switch states.
- Focus moves to the result or alert; reduced motion and visible focus remain.

## Data and API

- Extend `AgentSelectionIn` with one signed `program_ref`.
- Add a no-store organization-scoped program-option projection with a bounded
  query and selected-program recovery beyond the first page.
- Add bounded program route-brief DTOs to `AgentRunOut`.
- Reuse `AgentRun` and content-safe `AgentToolEvent`; add only a nullable
  SHA-256 result digest, never a persisted curriculum response snapshot.
- Recompute the bounded current projection and revalidate its digest during
  projection so map or evidence changes abstain instead of serving stale data.

## Security and privacy

- Program references are signed for organization, user, role, and program.
- Every execution and projection repeats organization membership and active
  program checks.
- Output is aggregate curriculum structure only. It excludes people, learner
  activity, grades, submissions, conversations, credentials, and model data.
- Saved evidence is untrusted content and is never interpreted as an
  instruction; this slice is deterministic and model-free.
- Tool events contain only run/tool/status/latency/failure metadata.
- Counts are SQL aggregates; audit analysis is capped before materialization
  and exposes truncation instead of silently scanning an unbounded program.

## Acceptance criteria

- [x] Each authorized program option has a signed role-bound reference.
- [x] All three program roles can complete select -> execute -> route brief.
- [x] Wrong role, organization, user, stale ref, and changed program fail closed.
- [x] The result contains bounded counts, at most three priorities, explicit
  evidence/review/uncertainty language, and no person-level or transcript data.
- [x] The existing deterministic audit remains authoritative, is also the
  handoff destination, and no program or Canvas write occurs.
- [x] Desktop/mobile loading, error/retry, empty, result, switch, focus, and
  overflow checks pass.
- [x] Batch-quality, product-UX, and agent-safety reviews have no open P0/P1.

## Test plan

- Unit: reference signing/resolution, projection bounds, stale version.
- API: three allowed roles, wrong role/org/user, no-store, events, idempotency.
- Browser: selected program -> route brief -> review handoff on desktop/mobile;
  loading, error/retry, empty, program switch, focus, overflow, clean console.
- Regression: full pytest, frontend lint/build, repo-wide pre-commit, and
  `git diff --check`.

## Batch review

- Initial batch-quality, product-UX, and agent-safety reviews found P1 issues
  around authoritative audit reuse, stale evidence, multi-organization scope,
  empty-state actions, focus contrast, reduced motion, and bounded analysis.
- The implementation was corrected and the product-UX and agent-safety targeted
  rechecks passed with no open P0/P1. The remaining batch-quality truncation
  finding was fixed with a cautious headline, an always-visible warning, and
  direct unit and browser regressions.
- Final gate: 409 backend tests, frontend lint/build, 34 Canvas simulator tests,
  repo-wide pre-commit, and `git diff --check` passed on 2026-08-03.
- Residual P2 follow-up: add approved PostgreSQL load/statement-timeout evidence,
  a high-cardinality selected-option regression, and manual assistive-technology
  validation before a production pilot.
