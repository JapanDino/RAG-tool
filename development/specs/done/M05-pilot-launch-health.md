# M05 — Privacy-safe pilot launch health

Status: done

## User outcome

An organization administrator can open the existing Canvas installation route
and understand whether recent LTI launches are reaching the product, which
aggregate failure family needs attention, and whether unresolved bindings make
the pilot unsafe to continue—without seeing platform identifiers or individual
student/teacher activity.

## Users and permissions

- Organization administrator: may read aggregate pilot health for their exact
  organization and use existing binding/registration actions.
- Instructor, student, methodologist, program designer, cross-organization
  administrator, and LTI course session: receive a non-disclosing denial.
- The health view is read-only and cannot activate, deactivate, bind, or mutate
  Canvas.

## Context and evidence

- `development/ROADMAP.md`: M05 requires reliable teacher/student pilot flows.
- `development/PRODUCT.md`: administrative analytics are aggregate and must not
  become personnel or learner surveillance.
- `development/ARCHITECTURE.md`: LTI audit events are content-minimal and scoped
  to an organization/registration.
- `development/design/DESIGN_SYSTEM.md`: Workshop Route is canonical; the Course
  Route is the single expressive device.
- `development/security/SECURITY_BASELINE.md`: minimize student data and keep
  identifiers, tokens, and signed messages out of logs and UI.

## Scope

- Add an organization-scoped read service and API for a fixed recent window.
- Aggregate accepted/rejected known-registration launches; never return event,
  course, user, platform subject/context, issuer, client, or deployment IDs.
- Group rejection reason codes into bounded operator-safe families.
- Count only unexpired pending subject/context binding candidates.
- Return deterministic `not_started`, `stable`, `review_bindings`, or
  `review_failures` state and explicit non-automatic pause triggers.
- Add a Workshop Route launch-flow panel to the existing administrator Canvas
  installation page with loading, empty, stable, attention, error, and retry.

## Non-goals

- No Canvas API call, OAuth, roster/content sync, grades, submissions, or LMS
  write.
- No per-user, per-course, per-role, or per-registration activity view.
- No teacher/student ranking, adoption score, automatic anomaly verdict, or
  automatic registration deactivation.
- No arbitrary date filter, export, notification, or long-term analytics store.

## User flow

1. Administrator opens `/workspace/integrations/lti` for one organization.
2. The launch route loads beside existing readiness and binding controls.
3. The administrator sees the bounded recent aggregate and one plain-language
   next action.
4. If bindings or repeated failures exist, the screen points to existing
   controls or recommends pausing new pilot launches; it changes nothing itself.

## UX contract

- One Workshop Route strip encodes `known launches → verified → review` with
  labeled counts; no generic KPI-card grid.
- Failure families are ordered by count then stable code and use plain Russian
  operator language, not raw backend reason codes.
- `not_started` explains how to produce the first signed launch.
- A small sample never produces a success rate, score, or “healthy school” claim.
- Attention and pause states use text and shape in addition to color.
- Retry preserves the registration form and existing binding work.
- Desktop 1440×900 and mobile 390×844 remain usable without horizontal scroll;
  keyboard focus and reduced-motion behavior follow the design system.

## Data and API

- No migration or stored aggregate.
- `GET /integrations/lti/organizations/{organization_id}/pilot-health` returns a
  versioned aggregate for the fixed seven-day window.
- Response contains: state, total/accepted/rejected counts, active registration
  count, pending subject/context counts, bounded failure families, pause trigger
  codes, generated time, and last known launch time.
- All queries repeat exact organization scope; deleted/unknown registrations do
  not leak into another organization.

## Security and privacy

- Administrator authorization is enforced in the backend.
- The response has no user/course/event/registration/platform identifiers,
  timestamps tied to individuals, raw reason codes, or launch claims.
- Failure categories use a fixed allow-list; unknown reasons map to `other`.
- Signals are operational recommendations only and never mutate registrations.
- Imported content and model output are not involved.

## Acceptance criteria

- [x] Exact-organization administrator receives correct seven-day aggregates.
- [x] Cross-organization and non-administrator access fails non-disclosingly.
- [x] Response cannot expose identifiers or raw rejection codes.
- [x] Pending backlog excludes resolved, dismissed, and expired candidates.
- [x] Pause triggers require deterministic repeated evidence and never act.
- [x] UI covers loading, no data, stable, attention/pause, error/retry, desktop,
  mobile, keyboard, and reduced motion in Workshop Route style.
- [x] Backend/full regression, frontend lint/build, browser QA, and required
  batch reviews pass.

## Test plan

- Service tests for window boundaries, categories, backlog, ordering, unknown
  reasons, state precedence, and pause thresholds.
- API tests for administrator, role denial, cross-organization isolation, and
  response-key privacy.
- Frontend lint/build plus browser checks for all required states using bounded
  synthetic data only.
- General and product/UX batch reviews; RAG review is not applicable.

## Batch review

- General quality and product/UX targeted rechecks passed with no remaining
  P0/P1 findings.
- Production health joins the exact organization registration and excludes all
  local development registrations, events, and binding candidates.
- Activation and deactivation refresh the aggregate immediately; verified
  history with zero active production registrations recommends reactivation,
  never pilot expansion.
- Operational mobile text is at least 14px, explanatory text is 16px, and the
  390px route has no horizontal overflow.
- Focused LTI suite after fixes: 72 passed. Full backend regression before the
  review fix pass: 239 passed. Frontend lint/build and targeted pre-commit:
  passed. Browser recheck: zero errors/warnings.
- Deferred P2: future-dated audit events are not upper-bounded against the
  generated timestamp; a committed browser E2E for registration-health
  invalidation is still absent.
