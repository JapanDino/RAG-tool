# M03 — Tutor data lifecycle

Status: done

## User outcome

A student can see how long tutor conversations are kept and permanently delete
their own history for a course. A school administrator can set one transparent
organization-wide retention period, and expired tutor data is removed without
exposing conversation content to administrators.

## Users and permissions

- Student: read the effective policy for an assigned course and delete only
  their own course history.
- Instructor and methodologist: read the effective course policy; they cannot
  delete student history or change the organization policy.
- Administrator: read and update the organization policy and trigger an
  expired-data purge; they cannot select or inspect individual transcripts
  through the lifecycle API.
- Program designer, other students, and outsiders: no access to individual
  lifecycle actions or deletion receipts.

## Context and evidence

- `development/security/SECURITY_BASELINE.md` requires retention and deletion rules before
  a student pilot and data minimization for minors.
- `development/PRODUCT.md` requires aggregate administration rather than student
  surveillance.
- `development/specs/done/M03-grounded-student-tutor.md` scopes history and
  feedback to the authenticated answer owner.
- `development/specs/done/M03-teacher-tutor-quality.md` derives 30-day aggregate
  service metrics without transcript payloads.
- Existing answers contain question, answer, citations, feedback, ownership, and
  timestamps; feedback events already cascade conceptually with an answer.

## Product decisions

- The default retention period is 90 days: long enough for the existing 30-day
  service-quality window, but not indefinite.
- An administrator may choose only 30, 90, 180, or 365 days. The UI/API does not
  accept arbitrary or unlimited retention.
- Student self-deletion is always available and cannot be disabled by a school.
- Deletion is hard deletion of stored tutor content, not a hidden soft-delete.
- A deletion receipt may retain actor/subject IDs, scope, reason, policy version,
  cutoff, timestamp, and counts. It never stores question, answer, citation,
  feedback comment, model prompt, or source text.
- Evaluation protocols and aggregate values are not rewritten. Future aggregate
  views are calculated from the remaining source rows.

## Scope

- Add an organization tutor-data policy with optimistic concurrency and an
  append-only policy event.
- Add a content-free deletion receipt.
- Add service functions for owner deletion and retention-based purge.
- Add a daily Celery task plus an explicit administrator purge endpoint so the
  same behavior is testable before deployment scheduling is available.
- Add a course-scoped policy endpoint and an owner-only history deletion endpoint.
- Add the student “Ваши данные” lifecycle flow to the existing tutor page.
- Add an administrator-only retention control to the existing teacher course
  workspace; instructor and methodologist views do not show it.

## Non-goals

- Deleting user accounts, Canvas enrollments, course content, audit findings, or
  immutable evaluation protocols.
- Legal holds, parent/guardian workflows, or exporting a data-subject archive.
- A transcript browser, per-student administrator action, or bulk manual student
  selection.
- Claiming GDPR or local-law compliance without the school's documented lawful
  basis and policy review.
- LTI, OAuth, live Canvas mutation, or deployment to the organization host.

## User flow

### Student

1. Open the tutor and see “Ваши данные” below personal history.
2. Read the effective retention period and the two-step lifecycle: available now,
   automatically deleted after the policy window.
3. Choose “Удалить мою историю”.
4. Review exactly what is deleted and what is preserved, then choose “Удалить
   историю” or “Оставить историю”.
5. On success, history and the selected answer disappear and a same-word success
   message confirms deletion. The student may ask a new question immediately.

### Administrator

1. Open an assigned course and read the current organization policy and version.
2. Select an allowed retention period and save with the expected version.
3. See that daily cleanup and student self-deletion stay active.
4. Optionally trigger the same expired-data purge through the protected API used
   for operational testing before deployment.
5. Receive aggregate deletion counts only, never transcript content or identities.

## UX contract

- Keep the current calm study-desk direction and design-system tokens.
- Extend the Course Thread into a compact lifecycle line: “Сейчас — доступно вам”
  to “Через N дней — удаляется”. This is the one expressive element.
- Primary study action remains “Разобраться”; deletion stays secondary until the
  explicit confirmation dialog.
- Confirmation title: “Удалить всю историю этого курса?”
- Confirm: “Удалить историю”. Cancel: “Оставить историю”. Busy: “Удаляем…”.
- Success: “История удалена. Новые вопросы можно задать в любой момент.”
- Failure states say that deletion failed and the existing history was preserved.
- Empty history still shows the retention rule but not an active destructive
  action.
- Dialog traps the decision visually, receives keyboard focus, closes on Escape,
  returns focus to its trigger, and does not rely on color alone.
- Desktop reference: 1440 × 900. Mobile reference: 390 × 844. No horizontal
  scrolling or hover-only action.

## Data and API

- Migration adds `organization_tutor_data_policies`, policy events, and
  `tutor_data_deletion_events`.
- Absence of a policy row means 90 days and version 0.
- `GET /courses/{course_id}/tutor-data-policy` returns the effective policy.
- `DELETE /courses/{course_id}/qa/history` requires the fixed confirmation token
  and deletes only rows owned by the authenticated student in that course.
- `GET/PATCH /organizations/{organization_id}/tutor-data-policy` is
  administrator-only; PATCH requires `expected_version`.
- `POST /organizations/{organization_id}/tutor-data-policy/purge` is
  administrator-only and requires the current version plus a fixed confirmation.
- The periodic task calls the same purge service for every organization.
- Existing tutor answer/history schemas remain backward compatible.

## Security and privacy

- Authorization is enforced in backend routes and services; frontend state is not
  a permission boundary.
- Course and organization mismatches return a non-disclosing denial.
- Confirmation tokens are fixed enum values, not free-form text or prompts.
- Deletion and purge never serialize transcript data into responses, events, or
  logs.
- Feedback rows are explicitly removed before answers so SQLite tests and
  PostgreSQL behave consistently even when FK cascade settings differ.
- Concurrent questions are not silently claimed as deleted: the UI disables
  deletion while its own request is running, and a separately in-flight request
  may require a second deletion. Cross-tab transaction coordination is deferred.

## Acceptance criteria

- [x] Default policy is 90 days/version 0 and only allowed periods validate.
- [x] Administrator can update with optimistic concurrency and a content-free
  audit event; other roles receive non-disclosing denial.
- [x] Assigned student can read the policy and permanently delete only their own
  course answers, citations, comments, and feedback events.
- [x] Other students, staff, designers, and outsiders cannot use owner deletion.
- [x] Deletion is idempotent and its response/receipt contains counts but no
  transcript or source content.
- [x] Retention purge removes only expired answers in the selected organization
  and uses the effective policy/version.
- [x] Daily task and explicit administrator purge call the same service.
- [x] Student UI covers populated, confirmation, busy, success, empty, error, and
  mobile/keyboard states.
- [x] Administrator UI can update the organization period; instructor and
  methodologist UI does not expose the control.
- [x] Existing tutor quality, evidence, evaluation, and authorization regressions
  pass after deletions.
- [x] Focused/full tests, frontend lint/build, targeted pre-commit, browser checks,
  and batch/UX reviews pass.

## Test plan

- Unit/service tests for default policy, validation, version conflict, cutoff,
  organization scope, idempotence, and content-free receipts.
- API tests for administrator update/purge and student read/delete permissions.
- Regression assertions that teacher aggregates and evidence exports no longer
  include deleted rows.
- Celery task test against the same purge service.
- Frontend lint/build and browser checks at desktop/mobile widths for populated,
  confirmation, success, empty, and failure states; inspect console and keyboard.

## Batch review

Completed on 2026-07-14.

- The first general review found two P1 issues: purge could race a policy update,
  and the owner-deletion service trusted organization/membership scope supplied by
  its caller. Policy update and purge now lock the same organization row, version
  validation happens inside the locked purge transaction, and owner deletion
  repeats course-organization and active-student checks at the service boundary.
- The first UX review found two P1 issues: privacy copy overstated staff access to
  transcript text, and the dialog had no stable focus target while both actions
  were disabled. Copy now matches the aggregate-only boundary; the busy dialog is
  focusable, exposes `aria-busy`, and retains Tab/Shift+Tab focus.
- Targeted general and UX rechecks both passed with no remaining P0/P1 findings.
- Verification: `python -m pytest -q` passed 84 tests; the focused integration
  cluster passed 16 tests; frontend lint and production build passed; the complete
  M03 lifecycle file set passed targeted pre-commit; development and production
  Compose configs validated.
- Browser checks covered populated, confirmation, busy, success, empty, failure,
  desktop/mobile, console, and keyboard states. Busy focus remained on the dialog
  before and after Tab; normal student/admin states had no console errors or
  warnings. The mocked deletion failure produced only its expected network error.
- Deferred P2: exercise row-lock semantics against PostgreSQL, isolate/retry
  per-organization scheduler failures, mirror migration checks in ORM metadata,
  expand negative rollback coverage, and add committed browser E2E coverage.
