# M05 — Explicit LTI binding readiness

Status: done

## User outcome

An organization administrator can review a verified but unbound Canvas launch
request and explicitly map its opaque platform subject and course context to an
existing active user and course. A later signed launch can resolve through the
existing role and membership checks without auto-provisioning anything.

## Users and permissions

- Organization administrators can list and resolve candidates for their exact
  organization and production registration.
- Other roles, cross-organization administrators, and course-scoped LTI
  sessions receive a non-disclosing denial.
- A launch claim never creates users, courses, organization memberships, course
  memberships, or bindings automatically.

## Context and evidence

- `development/specs/done/M05-local-lti-launch-boundary.md`
- `development/specs/done/M05-role-scoped-product-session.md`
- `development/specs/done/M05-production-registration-readiness.md`
- `development/ARCHITECTURE.md`
- `development/integrations/CANVAS.md`
- `development/design/SCREEN_STATES.md`

## Scope

- Quarantine missing `sub` and `context.id` values only after the signed launch
  passes issuer, audience, deployment, nonce, message, version, target-link,
  resource-link, context, and supported-role validation.
- Store a bounded pending identifier plus SHA-256 fingerprint, first/last seen,
  count, expiry, and resolution state. Do not store email, name, course title,
  resource title, or arbitrary claim payload.
- List pending candidates together with organization-scoped eligible existing
  users and courses.
- Bind a subject candidate to one active organization user or a context
  candidate to one existing organization course.
- Clear the quarantined plaintext after binding or dismissal and record a
  content-minimal binding event.
- Add the administrator review surface to the existing Canvas installation page.

## Non-goals

- Canvas API reads, roster sync, course import, or Canvas writes.
- Creating users, courses, or memberships from launch claims.
- Email/name matching or suggested automatic matches.
- Changing the existing role intersection or product-session policy.
- Bulk mapping or CSV import.

## User flow

1. An active production registration receives a cryptographically valid launch
   with an unknown subject or course context.
2. The launch still fails closed; only the missing opaque identifiers enter the
   bounded quarantine.
3. An administrator opens Canvas installation and sees masked subject/context
   requests with first/last seen and repeat count.
4. The administrator selects an existing user or course and confirms `Привязать`.
5. The UI confirms that only the identifier binding changed and that a new
   signed launch is still required.

## UX contract

- Binding readiness appears after registration state, not as proof that Canvas
  is connected.
- Candidate labels are `Пользователь Canvas` and `Курс Canvas`; raw identifiers
  are never rendered.
- Empty state explains how candidates appear and that no account/course is
  created automatically.
- Binding requires an explicit target selection and confirmation.
- Success says `Привязка сохранена. Запустите курс из Canvas ещё раз.`
- Error says what was preserved and offers refresh/retry.
- Mobile stacks candidate, target, evidence, and action without overflow.

## Data and API

- Migration `0036_lti_binding_candidates.sql` adds candidate and event tables.
- `GET /integrations/lti/organizations/{organization_id}/registrations/{registration_id}/binding-candidates`
  returns pending masked candidates plus bounded eligible targets.
- `POST .../binding-candidates/{candidate_id}/bind` accepts `target_id`.
- `POST .../binding-candidates/{candidate_id}/dismiss` clears the pending raw
  identifier without creating a binding.
- Candidate resolution is serialized; unique binding constraints remain the
  final conflict guard.

## Security and privacy

- Quarantine occurs only after token signature and mandatory launch-claim
  validation. Invalid, replayed, wrong-target, wrong-deployment, unsupported-role,
  or malformed tokens never create candidates.
- Responses expose a fingerprint prefix, never the platform identifier.
- Pending plaintext expires after 30 days and is cleared on resolution.
- Target users require an active organization membership; target courses must
  belong to the registration organization.
- Events record IDs and action only, not platform identifiers or claim content.

## Acceptance criteria

- [x] A verified unbound launch fails closed and creates only the missing subject/context candidates.
- [x] Invalid or unsupported launches create no candidates.
- [x] An authorized administrator can map candidates only to existing in-scope active targets.
- [x] Binding creates no user, course, or membership and clears candidate plaintext.
- [x] Cross-organization, stale, expired, dismissed, or repeated resolution fails closed.
- [x] A later valid launch resolves through the existing membership/role checks.
- [x] The Canvas UI exposes masked evidence, explicit confirmation, and honest success/error states.

## Test plan

- Service: capture gating, deduplication, expiry, target scope, binding, dismissal, concurrency conflict.
- API: administrator success, role denial, cross-organization denial, masked output.
- Launch regression: invalid tokens do not quarantine; verified unbound launch does; bound relaunch succeeds.
- Frontend: empty, candidates, bind confirmation, success, error, permission, desktop/mobile, keyboard.
- Full backend tests, frontend lint/build, migration and diff checks.

## Batch review

Passed after one fix pass. The general and product/UX targeted rechecks reported
no remaining P0/P1 findings. Final verification: 160 backend tests, frontend
lint/build, repo-wide pre-commit, desktop/mobile/confirmation browser checks,
and a clean populated-state browser console. PostgreSQL migration and
concurrency rehearsal remains a documented production-readiness gap.
