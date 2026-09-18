# M02 — Teacher attention queue

Status: completed on 2026-07-13

## User outcome

An authorized teacher opens a course from the role-aware workspace, immediately
sees the most important verified issues, opens the supporting evidence, and
records a review decision without navigating through the ML laboratory.

## Users and permissions

- Instructor: inspect and review findings for an assigned course.
- Methodologist: inspect and review findings for an assigned course.
- Administrator: inspect and review when organization policy permits.
- Student and program designer: no access to the teacher attention queue.

## Context

- Completed identity slice: `../done/M01-identity-and-roles.md`.
- Teacher flow: `../../design/USER_FLOWS.md`.
- Evidence UX: `../../design/EXPERIENCE.md`.
- Security baseline: `../../security/SECURITY_BASELINE.md`.

## Scope

- A course workspace summary with latest audit state and inspectable metrics.
- Findings ordered by severity, uncertainty, and review status.
- A finding detail view with source evidence and confidence language.
- Confirm and reject actions attributed to the authenticated reviewer.
- Empty, loading, permission, failed-audit, and no-finding states.
- Desktop and mobile rendered review.

## Non-goals

- Generating remediation drafts.
- Editing course source content.
- Applying Canvas changes.
- Program-level analytics.
- Student tutoring.
- Replacing the existing ML laboratory.

## User flow

1. Open an assigned course from `/workspace`.
2. See the latest audit status and the highest-impact unresolved issue.
3. Select a finding and inspect its description, recommendation, confidence,
   uncertainty, and source evidence.
4. Confirm or reject the finding.
5. See the decision reflected in the queue and review history.

## UX contract

- The first screen answers “what needs my attention?”
- Severity and confidence are expressed in words, not color or percentages alone.
- Evidence is visible before a consequential review action.
- Review actions use the same verb in button, progress, and confirmation copy.
- The Course Thread shows whether the finding concerns a goal, material, or
  assessment relationship.
- The ML laboratory remains a secondary expert path.

## Data and API

- Add a teacher-oriented workspace summary response derived from existing
  `AuditRun`, `CourseFinding`, and course objects.
- Reuse existing finding review history persistence.
- Derive `reviewed_by` from the authenticated principal whenever authentication
  is enabled; do not trust a client-supplied reviewer identity.

## Security and privacy

- Apply the existing course route guard to every new endpoint.
- Return non-disclosing denial for unassigned courses.
- Do not include raw document bodies in summary payloads.
- Limit evidence quotes and preserve source identifiers needed for inspection.
- Do not expose hidden student content.

## Acceptance criteria

- [x] Authorized instructor can open a course attention queue from `/workspace`.
- [x] Latest audit status and prioritized findings are understandable without ML
      terminology.
- [x] A finding exposes evidence, recommendation, confidence, and uncertainty.
- [x] Confirm/reject uses the authenticated reviewer identity and writes history.
- [x] Student and cross-organization requests receive a non-disclosing denial.
- [x] Empty and failed-audit states provide one valid next action.
- [x] Desktop and mobile browser checks pass without console errors.

## Verification

- `python -m pytest -q`: 61 passed.
- `npm run lint`: passed.
- `npm run build`: passed.
- Browser: prioritized queue, evidence, confirm action, server-derived reviewer,
  permission denial, 1440 × 900 and 390 × 844.
- Browser console: no errors or warnings in final instructor and permission runs.

## Deferred risks

- The queue currently shows one latest audit, not a merged multi-version history.
- Browser checks are reproducible manually but not yet committed as an E2E suite.
- Filtering and bulk review are deferred until real pilot queue sizes are known.

## Test plan

- Summary service ordering and empty-state tests.
- API role matrix and reviewer-attribution tests.
- Existing regression suite.
- Frontend lint and production build.
- Rendered instructor, empty, permission, and mobile states.
