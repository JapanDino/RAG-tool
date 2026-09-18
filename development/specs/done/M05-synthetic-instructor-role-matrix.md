# M05 synthetic instructor role matrix

Status: done

## User outcome

A teacher launched from a synthetic Canvas course reaches the exact protected
teacher workspace for that course, while a learner continues to reach only the
learner companion and cannot acquire teacher capabilities.

## Users and permissions

- Learner: open the exact published synthetic course map and cited tutor only.
- Instructor: open the exact existing teacher workspace for the bound course.
- Administrator and other roles: no new simulator path in this slice.
- The simulator does not grant a role that is absent from internal organization
  and course memberships.

## Context and evidence

- `development/ROADMAP.md`
- `development/ARCHITECTURE.md`
- `development/integrations/CANVAS.md`
- `development/security/SECURITY_BASELINE.md`
- `development/design/DESIGN_SYSTEM.md`
- `development/specs/active/M05-letovo-embedded-course-companion.md`
- Existing LTI launch routing already sends an internally bound instructor to
  `/workspace/courses/{course_id}?lti=1`; the current simulator bootstrap creates
  only a learner binding.

Docker CLI is installed locally, but the Docker Engine is not available on
2026-08-02. This slice prepares the role matrix offline; it is not evidence from
a real self-hosted Canvas LMS.

## Scope

- Add one visibly synthetic instructor identity to the development-only Canvas
  simulator organization and both synthetic courses.
- Create exact subject bindings for learner and instructor on each existing
  synthetic LTI registration.
- Resolve a launch only for an allow-listed `learner` or `instructor` actor whose
  active internal organization and course roles match the requested actor.
- Preserve the current learner resolver behavior when no actor is supplied.
- Let the local Canvas course frame switch between learner and instructor test
  launches with plain role labels and explicit synthetic-environment copy.
- Extend browser coverage through the real signed LTI redirect chain into the
  existing teacher workspace.

## Non-goals

- Running, vendoring, copying, or modifying official Canvas LMS code.
- Claiming real Canvas cookie, placement, TLS, DNS, or browser-storage evidence.
- Redesigning the teacher workspace, adding administrator UX, or connecting
  OAuth/API credentials.
- Reading grades, submissions, rosters, messages, hidden material, or school
  data; performing Canvas writes; changing production enablement.

## User flow

1. Open a synthetic course from the local Canvas dashboard.
2. Open `Помощник курса` and choose the synthetic teacher check.
3. Complete the same signed LTI launch used by the learner flow.
4. See the exact course name and `Очередь внимания преподавателя` workspace.
5. Switch back to the learner check and confirm the learner companion remains
   unchanged.

## UX contract

- Role selection is visibly labeled as local synthetic verification and never
  appears outside the gated Canvas simulator.
- Use `Ученик` and `Преподаватель`, not LTI claims or internal role identifiers.
- The selected role has programmatic current-state indication and keyboard focus.
- The tool frame keeps the Canvas shell visible at desktop and 390 px.
- Loading, unavailable actor, expired session, and permission failure remain
  fail-closed and explain the safe next action.

## Data and API

- No migration; simulator rows remain deterministic synthetic development data.
- Bootstrap response adds instructor identity, subject, and launch URL while
  retaining existing learner fields.
- `GET /integrations/lti/development/simulator/{fixture_id}` accepts only an
  allow-listed actor and defaults to the learner for backward compatibility.
- The resolved response contains only the selected actor subject and launch URL,
  course/registration identifiers, and the existing chooser URL.

## Security and privacy

- Keep all routes behind the existing development-auth and four-part simulator
  gate; production returns 404.
- Validate exact registration, organization, course, subject, active user,
  active organization membership, active course membership, and matching role
  before returning a launch URL.
- Treat query values as untrusted and reject unsupported actors without falling
  back to a more privileged role.
- Synthetic role switching never mutates a real Canvas session or registration.

## Acceptance criteria

- [x] Bootstrap is idempotent with exactly two users, four subject bindings, and
  four course memberships across the two fixtures.
- [x] Learner and instructor resolver calls return different exact subjects and
  preserve the same bound course and registration.
- [x] Signed instructor launch opens the exact teacher workspace; signed learner
  launch still opens the learner companion.
- [x] Missing, inactive, cross-course, or role-mismatched bindings fail closed
  and unsupported actor values are rejected.
- [x] Desktop and 390 px browser flows cover both roles with clean console,
  visible focus, and no page-level horizontal overflow.
- [x] Existing Canvas/LTI/tutor behavior remains green.

## Test plan

- Unit/service: deterministic users, memberships, subject bindings, actor
  resolver, mismatch and inactive cases.
- API: bootstrap compatibility, learner default, instructor selection, invalid
  actor, disabled gate.
- Browser: dashboard -> exact course -> learner/instructor selection -> signed
  launch -> exact role-specific product route.
- Regression: focused LTI/simulator/identity/teacher/tutor tests, full pytest,
  frontend lint/build, pre-commit, and `git diff --check`.
- Batch review: general, product/UX, and LTI isolation reviewers.

## Batch review

Completed on 2026-08-02. The gated bootstrap now creates one exact synthetic
learner and instructor per organization, course memberships for both fixtures,
and actor-specific subject bindings without adding a migration. The resolver
defaults to learner for compatibility but accepts only learner or instructor
and revalidates registration, context, course, user, organization membership,
course membership, role, and exact platform subject before returning a launch.

The Canvas shell exposes a keyboard-accessible local role selector and keeps the
existing signed LTI chain. Learners reach the module-scoped companion and receive
404 for teacher workspace data; instructors reach the exact teacher workspace
and receive 404 for the learner course map. Synthetic courses report OAuth as
production-disabled with a normal 200 status, avoiding expected 404 console
noise while start/disconnect remain unavailable.

Two review findings were fixed before acceptance: resolver denial now renders a
bounded unavailable state instead of silently falling back to the unsigned
assistant, and the legacy registration map can no longer open a multi-subject
chooser that bypasses the selected actor. Unsigned preview is explicit and
learner-only. Desktop role actions are at least 44 px.

The production Playwright matrix passed 12 tests without retries across both
courses, roles, and desktop/mobile viewports, including a resolver-denial
regression and a legacy-map trap. The full backend suite passed 313 tests;
frontend lint/build, repo-wide pre-commit, and `git diff --check` passed. General,
product/UX, and LTI-isolation rechecks found no remaining P0/P1. Real Canvas
iframe, cookie, placement, TLS/DNS, and role-account evidence remains outside
this completed synthetic slice.
