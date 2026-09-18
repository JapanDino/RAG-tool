# M01 — Identity and roles

Status: completed on 2026-07-13

## User outcome

An authenticated user sees only the organizations and courses assigned to them,
and the application exposes student, teacher, methodologist, program-designer,
and administrator actions according to explicit membership.

## Users and permissions

- Student: read published course evidence and use the student tutor.
- Instructor: manage and audit assigned courses and review drafts.
- Methodologist: review assigned course quality without publishing.
- Program designer: inspect assigned programs and course contributions.
- Administrator: manage organization membership and view aggregate health.

No role receives implicit cross-organization access.

## Context

- Product: `development/PRODUCT.md`.
- Architecture: `development/ARCHITECTURE.md`.
- Security: `development/security/SECURITY_BASELINE.md`.
- Future Canvas mapping: `development/integrations/CANVAS.md`.

## Scope

- Organization, user, course-membership, and role persistence.
- Local development authentication suitable for later replacement by LTI/OIDC.
- Request-level current-user dependency.
- Authorization service and route guards.
- One role-aware frontend entry flow.
- Migration and regression tests.

## Non-goals

- Canvas LTI launch.
- Enterprise SSO.
- Password reset and email delivery.
- Program-level permissions.
- Canvas write-back.
- Student personalization.

## User flow

1. A development user selects or receives a local identity.
2. The backend resolves organization and course memberships.
3. The user sees available courses and the correct role shell.
4. Direct requests to unauthorized courses return a non-disclosing denial.
5. Permission failures produce a clear recovery path in the UI.

## UX contract

- Role and organization context are visible but not dominant.
- The primary page starts with the user’s current job, not system configuration.
- Empty membership explains who can grant access.
- Permission denial does not imply whether a hidden resource exists.
- Desktop and mobile keyboard flows must be complete.

## Data and API

Planned entities:

- organizations;
- users;
- course_memberships.

The authorization layer must be independent of Canvas identifiers. Future LTI
identity is linked to internal users and memberships instead of replacing them.

## Security and privacy

- Deny by default.
- Check membership in backend services, not only UI.
- Do not log tokens, passwords, LTI claims, or course content.
- Protect organization and course identifiers from enumeration.
- Maintain an audit record for role and membership changes.

## Acceptance criteria

- [x] Authorized users can list and open assigned courses.
- [x] Unauthorized users cannot read or mutate another course by direct API.
- [x] Student and instructor see different actions for the same course.
- [x] Organization boundaries are covered by API regression tests.
- [x] Existing course-audit behavior remains available to an authorized
      instructor.
- [x] Local development authentication can later be swapped for LTI/OIDC.

## Verification

- `python -m pytest -q`: 59 passed.
- `npm run lint`: passed.
- `npm run build`: passed.
- Browser flow: development bootstrap, instructor demo course, authorized audit,
  student-safe course summary, desktop 1440 × 900 and mobile 390 × 844.
- Browser console: no errors or warnings after the final pass.

## Deferred risks

- The production `external` adapter is intentionally not implemented until the
  LTI/OIDC contract and Canvas deployment details are available.
- Existing courses require an explicit organization assignment before they are
  visible with authentication enabled.
- Canvas identity still needs host/deployment scoping in the later integration
  milestone.

## Test plan

- Model and migration tests.
- Authorization service matrix.
- API tests for every role and negative cross-course/cross-organization cases.
- Existing 57-test regression suite.
- Frontend role-shell smoke test.
- Manual mobile and permission-state review.
