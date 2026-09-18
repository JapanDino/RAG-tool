# M05 Instructor-owned Canvas OAuth handoff

Status: complete

## User outcome

An instructor who opened an exactly bound course from Canvas can authorize their
own read-only connection from the course workspace, return to that same course,
see a clearly labeled local fake snapshot, and disconnect the personal test
connection. Production continues to stop at `oauth_required`.

## Users and permissions

- Only an active instructor in an active LTI product session may inspect, start,
  complete, or disconnect the handoff for that session's exact registration and
  course.
- Students, local development identities, administrators outside an LTI product
  session, another registration/course, expired or revoked sessions, and missing
  context bindings receive a non-disclosing denial.
- An organization administrator still owns the non-secret Developer Key Client
  ID and exact Canvas API origin configuration. The instructor cannot edit it.

## Context and evidence

- `development/STATUS.md`
- `development/ARCHITECTURE.md`
- `development/integrations/CANVAS.md`
- `development/security/SECURITY_BASELINE.md`
- `development/design/DESIGN_SYSTEM.md`
- `development/specs/done/M05-current-course-read-sync-preview.md`
- `development/specs/done/M05-fake-canvas-oauth-lifecycle.md`

Verified current behavior: a product session pins registration, user, course,
and role; the current-course preview already accepts a registration/user-scoped
connection provider; the fake OAuth lifecycle stores only an opaque vault
reference and fixed read scopes. The provider default is unavailable and the
teacher preview currently has no functional authorization action.

## Scope

- Extend OAuth attempts with an explicit administrator/instructor flow kind and,
  for instructor flows, exact product-session, internal-course, and external
  Canvas-course snapshots.
- Add course-scoped handoff status, start, and disconnect endpoints protected by
  the existing LTI session cookie and CSRF boundary.
- Bind start and callback to the same active instructor session, registration,
  user, course, context binding, configured origin, and current course source.
- Return allow, deny, and bounded failure results to the same teacher course URL
  with `lti=1`; do not accept a return URL from the browser.
- Add a safe-development connection provider that recognizes only a live fake
  vault reference and returns a deterministic, explicitly synthetic snapshot.
- Extend the current Workshop Route panel with the personal connect/reconnect and
  disconnect flow.

## Non-goals

- Real Canvas authorization, tokens, refresh, HTTP calls, pagination, approved
  encrypted storage, or private-host access.
- Claiming that fake counts describe the real Canvas course.
- Configuration editing from the teacher workspace.
- Roster, user, enrollment, submission, grade, quiz-answer, analytics, learner
  activity, import, background synchronization, or Canvas write paths.
- Deploying the application or mutating a Canvas instance.

## User flow

1. An instructor opens the tool from the Canvas course navigation placement.
2. The current-course panel checks the exact course source and administrator-
   prepared non-secret OAuth configuration.
3. If safe local authorization is available, the instructor chooses
   `Подключить тестовое чтение`, reviews the four human-readable read scopes, and
   allows or denies the fake issuer.
4. The callback consumes state once, revalidates the same product session and
   course, stores only fake credential material, and returns to the same course.
5. The panel refreshes to an explicitly synthetic ready preview or gives a
   bounded recovery action. The instructor can disconnect their own test access.

## UX contract

- Subject: a Canvas-launched instructor. Single job: open a safe read route for
  the already selected course, without choosing a host, course ID, or token.
- Palette and type reuse Workshop ink `#15315F`, grid paper `#F8FBFF`, route
  cobalt `#2457D6`, evidence mint `#83D8C7`, marker apricot `#FF9B73`, note
  yellow `#FFD95A`, risk red `#B94952`, Segoe UI, and Cascadia Mono utilities.
- Layout keeps the existing source header, three-stop route, snapshot ledger,
  and footer. The OAuth checkpoint becomes the one signature control between
  current course and preview; no generic settings card is introduced.
- Desktop keeps the horizontal route and one evidence/action bench. At 390 px it
  becomes vertical with no horizontal scrolling and 44 px minimum actions.
- Required states: loading, administrator configuration required, exact-origin
  mismatch, ready to connect, authorizing, denied, callback failure, connected
  fake preview, reconnect required after process restart, production disabled,
  disconnect confirmation, session ended, permission denial, and retry.
- Fake success must say `Canvas не вызывался` and label all counts as synthetic.
  Production must not show a button that can never work.
- Callback result and actionable errors receive focus; disconnect confirmation
  takes focus and cancel/success return it predictably. All actions have visible
  focus, busy/disabled states, `aria-live`, and reduced-motion behavior.

## Data and API

- Migration `0038` adds nullable `product_session_id`, `course_id`, and
  `canvas_course_id` plus non-null `flow_kind` to `canvas_oauth_attempts`, with
  checks that instructor fields are all present only for instructor attempts.
- Existing administrator attempt rows remain valid as `flow_kind=admin`.
- `GET /courses/{course_id}/canvas-oauth-handoff` returns one bounded state,
  fake-flow availability, fixed scopes/exclusions, and connection timing/mode;
  it never returns registration, session, user, vault, or token identifiers.
- `POST /courses/{course_id}/canvas-oauth-handoff/start` returns only the server-
  generated fake authorization URL and expiry.
- `POST /courses/{course_id}/canvas-oauth-handoff/disconnect` revokes only the
  current instructor's registration-scoped connection.
- The preview response adds `snapshot_mode`; fake integrated reads use
  `fake_development`, while existing injected test connections use `test`.
- Schemas stay versioned and responses remain `no-store`.

## Security and privacy

- Start requires an exact active instructor product session and context binding;
  unsafe methods require the existing product-session CSRF token.
- The configured API origin must equal the origin derived from the bound course,
  and the external Canvas course ID is snapshotted into the one-use attempt.
- Callback requires the same raw session cookie to resolve to the snapshotted
  product-session row. Session revocation, expiry, relaunch replacement, role or
  binding removal, source change, or configuration change consumes/fails the
  attempt without creating a connection.
- Revalidation occurs before and after fake exchange. No browser-supplied course,
  registration, origin, external course ID, scope, or return URL is trusted.
- The fake provider checks row expiry/revocation, exact origin, fixed scopes, and
  process-local vault presence. It makes no network request and never reads
  credential material.
- API, events, logs, URLs, screenshots, and UI contain no raw state after the
  authorization request, code, token-shaped material, vault reference, roster,
  submission, grade, activity, or Canvas content.

## Acceptance criteria

- [x] A bound Canvas-launched instructor can complete the fake flow and return to
  the same course with a clearly synthetic ready preview.
- [x] The integrated provider reads only the current user's live fake connection
  and makes no Canvas/network call.
- [x] Student, local, wrong-course, wrong-registration, expired/revoked/replaced
  session, removed role/binding, source/config change, and replay fail closed.
- [x] Missing configuration and origin mismatch give an administrator handoff;
  production exposes no functional fake action.
- [x] Denial creates no connection and returns a retry path to the exact course.
- [x] Disconnect revokes only the current instructor connection and keeps admin
  configuration intact.
- [x] Response/event payloads contain no credentials or learner data, and fake
  counts are never presented as Canvas facts.
- [x] Existing admin OAuth, LTI launch/session, Canvas preview, and manual import
  regressions remain green.

## Test plan

- Unit: attempt invariants, exact target binding, session-cookie digest match,
  callback return construction, fake-provider expiry/vault/target checks.
- Service/API: status/start/allow/deny/disconnect; CSRF; all permission, session,
  binding, source, configuration, replay, and mid-exchange changes.
- Migration: clean PostgreSQL apply, second-pass checksum skip, constraints and
  indexes for `0038`.
- Frontend: lint and production build.
- Browser: exact LTI teacher route at 1440 x 900 and 390 x 844; connect, allow,
  deny/retry, synthetic ready, restart/reconnect, disconnect/cancel, keyboard
  focus, clean console, and zero overflow.
- Regression: focused Canvas/OAuth/LTI/teacher tests, then full pytest,
  pre-commit, and `git diff --check`.

## Batch review

- General quality, product/UX, and RAG/isolation reviews passed their targeted
  rechecks with no remaining P0/P1 findings.
- The fix pass standardized PostgreSQL locking as registration -> product
  session -> context -> OAuth configuration -> connection, preserved the exact
  instructor course return for post-consumption exchange/storage failures, and
  required exact equality with the four fixed read scopes.
- `python -m pytest -q` passed 274 tests. The reviewer-focused Canvas/OAuth/LTI
  set passed 83 tests; pre-commit, `git diff --check`, frontend lint, and the
  production build passed.
- Disposable PostgreSQL applied migrations 1-38 twice and passed the concurrent
  callback-versus-LTI-relaunch barrier without a deadlock or connection leak.
- The real local signed LTI browser flow passed connect, allow, exact-course
  return, synthetic ready, disconnect, desktop/mobile, zero-overflow, focus,
  and clean-console checks.
- Deferred P2: bind synthetic provenance into a discriminated snapshot contract
  before another API consumer or real adapter; unify no-store error headers;
  replace the development consent's state-changing GET before broader browser
  automation; deepen migration invariant rehearsal.
