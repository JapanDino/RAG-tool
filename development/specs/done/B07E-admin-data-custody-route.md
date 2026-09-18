# B07E Administrator data custody route

Status: done

## User outcome

An organization administrator opens the existing Canvas connection workspace
and asks what tutor and agent data the school currently keeps. The assistant
returns one bounded, read-only custody route: the effective organization
retention period, the stricter agent-runtime metadata boundary, policy versions,
and the latest content-free organization cleanup receipt when one exists.

## Users and permissions

- Administrator: inspect the effective policy for one explicitly selected
  organization and reveal the exact retention boundaries in the current view.
- Every other role, anonymous, inactive, wrong-organization, wrong-user, and
  compatibility-bypass contexts receive a non-disclosing denial.

## Context and evidence

- `development/AI_CANVAS_AGENT_PLAN.md` B07.
- `development/agent/API_CONTRACT.md` and `TOOL_CATALOG.md`.
- Existing `OrganizationTutorDataPolicy` and content-free
  `TutorDataDeletionEvent` records.
- Existing signed organization reference and agent state machine from B07B.
- `development/design/EXPERIENCE.md` and `DESIGN_SYSTEM.md` Workshop Route.

## Scope

- Make `get_retention_and_policy_status` executable through one
  `admin.policy_status.v1` workflow and the existing signed organization
  reference.
- Read the effective tutor-data policy and the latest organization-wide
  automatic-retention or administrator-purge receipt independently.
- Expose aggregate deleted-record counts only when the receipt has no course or
  subject association; never expose actor, subject, course, or record content.
- Show the retention contract, agent-runtime metadata cap, version ledger,
  receipt state, explicit limitations, and a progressive-disclosure handoff.
- Recompute the bounded source for projection and abstain after a policy or
  receipt change, including a new receipt with otherwise identical public facts.

## Non-goals

- No policy edit, retention change, purge execution, student deletion, Canvas
  call, model call, provider call, deployment, or infrastructure mutation.
- No person/course breakdown, transcript, prompt, answer, feedback content,
  grade, submission, surveillance signal, or claim about policy compliance.
- No claim that absence of a deletion receipt means cleanup never ran: an
  empty purge may legitimately create no receipt.
- No research or school-production claim in this slice.

## User flow

1. The administrator opens the selected organization connection workspace.
2. They choose `Проверить хранение`.
3. The agent rechecks active membership and the signed organization boundary,
   then reads policy and receipt projections without writing.
4. A retention ruler shows the general boundary, stricter agent-metadata cap,
   version ledger, and latest safe receipt or an honest no-receipt state.
5. `Показать границы очистки` reveals the exact included/excluded data classes
   and limitations in the same Canvas-compatible surface.

## UX contract

- Single job: understand what the system is configured to retain and what
  aggregate cleanup evidence is currently recorded.
- Signature element: a workshop-paper retention ruler from `сейчас` to the
  effective cutoff, with a separate 30-day agent-metadata marker and a stamped
  cleanup receipt below it. It must not become a generic metric-card dashboard.
- Reuse the canonical ink, grid, cobalt, mint, apricot, yellow, red, Segoe, and
  Cascadia tokens. Color always has a text label.
- Desktop uses one horizontal ruler and two-column ledger/receipt evidence;
  mobile stacks the ruler markers and evidence without horizontal page scroll.
- Exact idle action: `Проверить хранение`; exact result handoff:
  `Показать границы очистки`; recovery action: `Повторить проверку`.
- Idle, loading, organization-policy, default-policy, current/previous-policy
  receipt, no-receipt, partial, stale, error/retry, permission, focus, keyboard,
  reduced-motion, console, and overflow states are explicit.
- One primary action per state; status updates use a polite live region; focus
  is visible and disclosure focus is not hidden by the sticky Canvas header.

## Data and API

- Add closed response DTOs for retention source/boundary, policy-version rows,
  bounded purge status, limitations, and read-only mode. No migration.
- Add `organization_ref` to the registry tool input and route the adapter to the
  implemented administrator policy projection.
- Reuse `POST /agent/v1/messages`, the existing execute/status endpoints, and
  the B07B organization selector; no new selection endpoint.
- Execute exactly one fixed tool and record only its name, status, latency, and
  bounded failure class in the existing tool-event table.
- Result freshness includes effective policy values and source row state,
  static agent policy version, and the latest safe receipt identifier/content.

## Security and privacy

- Execution and projection repeat active administrator membership, exact
  organization/user/role context, and signed-reference validation.
- Receipt lookup is fixed to the selected organization, organization-wide
  automatic/admin reasons, and null subject/course boundaries.
- Imported content and user messages cannot select tools or alter trusted query
  scope. The workflow invokes no model.
- SQL failures are isolated: policy and receipt may fail independently, with
  explicit partial/unavailable output and no exception text.
- No request/response content is persisted beyond the existing SHA-256 digest.

## Acceptance criteria

- [x] Only an active administrator can execute and project the exact signed
  organization workflow; changed authorization and wrong contexts fail closed.
- [x] The response exposes effective retention, agent metadata cap, versions,
  and only the latest safe aggregate receipt, with bounded honest limitations.
- [x] No-receipt copy does not claim that cleanup failed or never ran; partial
  policy/receipt failures preserve the other independently available evidence.
- [x] Execution is read-only and produces exactly one content-free tool event.
- [x] A changed policy or any newer safe receipt makes the completed projection
  abstain, even when the new receipt has identical public aggregate facts.
- [x] Desktop/mobile states, disclosure focus, keyboard, reduced motion,
  console, and overflow checks pass.
- [x] Batch-quality, product-UX, and agent-safety reviews have no open P0/P1.

## Test plan

- Unit/service: default/custom policy, current/previous receipt policy, absent
  receipt, unsafe receipt exclusion, aggregate bounds, independent source
  failures, stable/stale digest, new-identical-receipt staleness, and no writes.
- API/permission: administrator success, every non-admin role, wrong user/org,
  inactive membership, compatibility bypass, idempotency, and exact tool event.
- Browser: idle/loading, default/no receipt, custom/current receipt,
  previous-policy attention, partial, error/retry, stale/rerun, disclosure,
  focus, keyboard, reduced motion, desktop/mobile, clean console, and overflow.
- Regression: focused tests during development, then full pytest, frontend
  lint/build, full Canvas simulator, repo-wide pre-commit, and
  `git diff --check`.

## Batch review

- Batch-quality, product-UX, and agent-safety reviewers completed independent
  reviews. Safety passed initially; quality and UX both identified the same P1:
  error/stale states retained the header primary alongside the recovery action.
- The header action is now absent whenever an error is shown, leaving exactly
  one recovery action. Targeted desktop/mobile E2E and both reviewer rechecks
  passed with no remaining P0/P1.
- Final gates on 2026-08-03: 452 backend tests, frontend lint and production
  build, 82/82 desktop/mobile Canvas simulator tests, repo-wide pre-commit, and
  `git diff --check` passed. The first all-suite browser attempt hit a transient
  local Next/OneDrive `ENOENT` for an existing generated page after 11 tests;
  the unchanged full rerun passed all 82 tests.
