# B10B Administrator agent-policy control plane

Status: complete

## User outcome

An organization administrator can decide which school roles may start the
Canvas assistant and whether model-backed tasks may use the approved school AI
host. The administrator previews the exact impact before applying a versioned,
audited change.

## Users and permissions

- Administrators may read, preview, and apply their organization policy.
- Students, instructors, methodologists, and program designers cannot access
  the organization policy route.
- Administrator governance workflows remain available even when other routes
  are paused, so a policy cannot lock its owner out of recovery.

## Context and evidence

- `development/PRODUCT.md`
- `development/ARCHITECTURE.md`
- `development/design/DESIGN_SYSTEM.md`
- `development/specs/done/B10A-learner-agent-conversation.md`
- Existing execution boundary: `backend/app/services/agent_run.py` and
  `backend/app/routers/agent_api.py`.
- Existing model boundary: `backend/app/services/model_gateway.py`.

## Scope

- Organization policy for learner, instructor, and program-team routes.
- Organization model mode: approved school host with safe fallback, or
  deterministic-only.
- GET, preview, and confirmed PATCH API with optimistic versioning.
- Content-free policy change events.
- Enforcement at run admission, immediately before execution, and at the model
  gateway.
- Administrator UI next to the existing agent readiness route.

## Non-goals

- Canvas API credentials, model credentials, host URLs, model IDs, or prompts.
- Enabling Canvas writes or automatic course changes.
- Viewing individual conversations or user activity.
- Connecting to the real Canvas Letovo or school model host.

## User flow

1. Administrator opens the Canvas integration workspace.
2. They edit role routes or choose the model route.
3. `Проверить изменения` opens an exact impact preview.
4. `Применить настройки` records the new version and refreshes effective state.

## UX contract

- Present the policy as a Workshop Route dispatch board, not a generic settings
  table.
- Show effective version and fixed safety boundaries.
- Loading, error/retry, dirty, preview, conflict, success, and permission states
  are explicit.
- Desktop and mobile must preserve one clear primary action and visible focus.
- Native controls have accessible labels and status copy does not rely on color.

## Data and API

- `organization_agent_policies` stores three role gates, model mode, version,
  updater, and timestamps.
- `organization_agent_policy_events` stores previous/new policy state only.
- GET `/organizations/{organization_id}/agent-policy`.
- POST `/organizations/{organization_id}/agent-policy/preview`.
- PATCH `/organizations/{organization_id}/agent-policy` with
  `confirmation=apply_agent_policy` and `expected_version`.
- Missing rows resolve to permissive role defaults and approved-host-with-safe-
  fallback model mode at version zero without writing on GET.

## Security and privacy

- Organization scope and administrator role are rechecked server-side.
- Denials are non-disclosing 404 responses.
- Policy cannot contain arbitrary prompts, URLs, credentials, or model IDs.
- Model mode is enforced centrally even when a caller supplies a gateway.
- Events contain no messages, answers, citations, selected evidence, or secrets.
- Canvas remains read-only and human review remains mandatory for change sets.

## Acceptance criteria

- [x] An administrator can preview and apply an exact versioned policy change.
- [x] A non-administrator and a cross-organization administrator receive a
  non-disclosing denial.
- [x] Paused role routes cannot create or continue executable runs.
- [x] Administrator governance routes remain available.
- [x] Deterministic-only mode never calls the configured model transport.
- [x] Conflict recovery reloads current policy without silently discarding the
  administrator's understanding of what changed.
- [x] UI exposes no provider, model ID, prompt, URL, key, or transcript.

## Test plan

- Service/API tests for defaults, authorization, preview, apply, events, and
  optimistic conflict.
- Agent API tests for admission and execution-time policy enforcement.
- Model gateway test proving deterministic-only bypasses transport.
- Playwright desktop/mobile tests for edit, preview, cancel, apply, error, and
  conflict recovery.
- Backend tests, pre-commit, frontend lint/build, and visual screenshots.

## Batch review

- General quality, product UX, and agent/RAG safety rechecks passed with no
  remaining P0/P1 findings.
- Fixed same-page refresh replacing a reviewed draft by applying the immutable
  preview snapshot and preserving an open draft during background refresh.
- Fixed compatibility-bypass authorization and serialized admission, execution,
  model invocation, and policy updates on the organization row.
- Removed the public write-key path from the complete LTI-page dependency graph;
  a production bundle sentinel scan confirmed the value is absent.
- Added explicit preview/cancel/apply focus recovery and desktop/mobile coverage.
- Final gates: 455 backend tests, 94/94 Canvas Playwright tests, frontend
  lint/build, pre-commit, and desktop/mobile visual inspection passed.
