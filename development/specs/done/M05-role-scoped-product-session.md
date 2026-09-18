# M05 — Role-scoped product session handoff

Status: done

## User outcome

After a verified LTI launch, an existing learner or instructor opens the exact
bound course in the current product experience without selecting a development
identity. The session is short-lived, revocable, course-scoped, and never places
its credential in JavaScript, a URL, HTML, logs, or model input.

## Users and permissions

- A verified `student` receives a session scoped to one course and opens that
  course's tutor experience.
- A verified `instructor` receives a session scoped to one course and opens the
  teacher workspace.
- The session reuses current internal memberships and route authorization; it
  cannot access another course even if the same user has another membership.
- Methodologist, designer, and administrator session routing are excluded from
  this slice; their verified launch confirmation remains unchanged.
- Development identity headers continue to work only in safe development mode
  and are not written by the LTI frontend path.

## Context and evidence

- `development/specs/done/M05-local-lti-launch-boundary.md`: signed launch and
  exact identity/course/role mapping are already verified.
- `development/ARCHITECTURE.md`: authentication does not replace internal
  authorization; organization and course boundaries stay authoritative.
- `development/security/SECURITY_BASELINE.md`: secrets must not enter URLs,
  logs, prompts, fixtures, or committed configuration.
- [OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html):
  high-entropy server-side sessions and explicit Secure/HttpOnly/SameSite cookie
  attributes.
- [OWASP CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html):
  state-changing requests need a validated token/custom header and credentialed
  CORS must use exact trusted origins rather than `*`.
- [Canvas LTI launch overview](https://canvas.instructure.com/doc/api/file.lti_launch_overview.html):
  launches normally render in an iframe and third-party cookie behavior requires
  real-browser validation.

## Scope

- Persist revocable LTI product sessions containing only a token digest,
  registration/user/course IDs, resolved role, expiry, revocation, and times.
- Issue a 60-minute absolute session after a verified learner/instructor launch;
  revoke prior active sessions for the same registration/user/course.
- Set an HttpOnly host-only cookie. Production uses the `__Host-` prefix,
  `Secure`, `Path=/`, and `SameSite=None`; local HTTP development uses an
  unprefixed `SameSite=Lax` cookie.
- Resolve backend principals from the session while preserving current internal
  membership checks and restricting all course access to the bound course.
- Derive an HMAC CSRF token from the opaque session credential and a server
  secret; require it on every unsafe request authenticated by the cookie.
- Add session context and logout endpoints.
- Add an `Открыть курс` action on successful learner/instructor launches and
  route to the existing tutor or teacher page with no credential in the URL.
- Adapt only the teacher and student course pages plus a small shared frontend
  request helper to use credentialed requests and CSRF.

## Non-goals

- No Canvas API, OAuth, roster/content sync, LTI Advantage service, or LMS write.
- No long-lived login, refresh token, sliding expiry, remember-me, SSO outside
  the verified LTI launch, or automatic account provisioning.
- No organization/program administration through a course-scoped session.
- No session routing for designer, administrator, or methodologist in this slice.
- No claim that Safari/Chrome third-party-cookie behavior works inside the real
  Canvas iframe before testing the actual self-hosted instance and TLS topology.
- No Platform Storage implementation; M05 state/nonce already use server-side
  storage rather than a cookie.
- No repository-wide frontend API rewrite.

## User flow

1. Canvas or the local issuer completes the verified LTI launch.
2. The backend creates one opaque, revocable, course-scoped session and returns
   it only in an HttpOnly cookie.
3. The result screen offers `Открыть курс`; no token or internal identity is
   present in its URL.
4. The teacher or learner page requests `/identity/me` with credentials, receives
   only the bound course, and loads the existing role-specific experience.
5. Unsafe API calls first obtain the session context and send `X-CSRF-Token`.
6. `Выйти` revokes the row, clears the cookie, and returns to a neutral state.

## UX contract

- `Открыть курс` is the primary success action for supported roles;
  `Вернуться к выбору` remains secondary in the local test flow.
- The target page keeps the current teacher/student design and does not expose a
  technical authentication dashboard.
- Loading copy says the course access is being checked. Expired/revoked/denied
  states say the session ended and direct the user to relaunch from Canvas.
- A visible `Выйти` action is keyboard accessible and confirms completion.
- Mobile 390 px must have no horizontal overflow; no critical action requires
  hover.
- The interface must not imply Canvas content synchronization or write-back.

## Data and API

- Migration `0034_lti_product_sessions.sql` adds `lti_product_sessions` with a
  unique 64-character token digest and foreign keys to registration, user, and
  course.
- `GET /identity/session` returns safe session context plus the CSRF token; it
  returns 401 for missing/expired/revoked sessions.
- `POST /identity/session/logout` requires CSRF, revokes the current session, and
  clears the cookie.
- `GET /identity/me` and existing course APIs accept either explicit safe
  development identity or the product session.
- No raw session or CSRF token is persisted. No token appears in response JSON
  except the non-session CSRF value.
- The frontend uses `credentials: include`; credentialed CORS reflects only exact
  configured origins.

## Security and privacy

- Generate at least 256 bits of session entropy and persist SHA-256 only.
- Compare token and CSRF values in constant time where values are compared in
  application code.
- Require a dedicated production secret of at least 32 characters for HMAC CSRF.
- Restrict the principal to `course_scope_id`; organization-level actions and
  other courses fail closed even for organization administrators.
- Re-check active user, registration, organization, course, and memberships on
  every request; session role is audit context, not the authorization source.
- Never accept session IDs from query parameters, request bodies, localStorage,
  or arbitrary headers.
- Never allow `Access-Control-Allow-Origin: *` together with credentials.
- Logout is POST-only and CSRF-protected. Expiry/revocation does not reveal
  whether another user/course exists.
- Treat real iframe cookie availability as an external compatibility risk, not a
  reason to weaken HttpOnly, Secure, CSRF, or origin controls.

## Acceptance criteria

- [x] A local verified learner launch opens the exact tutor page and loads only
      the bound course without `X-Dev-User` or a credential in the URL.
- [x] A local verified instructor launch opens the exact teacher page under the
      same constraints.
- [x] The cookie is HttpOnly, host-only, path `/`, bounded to 60 minutes, and has
      environment-appropriate Secure/SameSite/name attributes.
- [x] Missing, random, expired, or revoked sessions return 401 and disclose no
      user/course facts.
- [x] A valid session cannot open another accessible course or perform an
      organization-level action.
- [x] Unsafe cookie-authenticated requests without the correct CSRF header fail;
      valid same-session CSRF succeeds and another session's token fails.
- [x] Logout revokes the database row, clears the cookie, and prevents reuse.
- [x] Designer/admin launches do not accidentally receive the unsupported
      learner/instructor handoff.
- [x] Development header identity and its existing tests remain functional.
- [x] Desktop/mobile, keyboard, expiry/permission, and clean-console states pass.

## Test plan

- Unit: entropy/digests, cookie policy, HMAC CSRF, TTL bounds.
- Service: issuance, prior-session revocation, expiry, revocation, active entity
  checks, course scope, role/membership drift.
- API: session/me/logout, CSRF negative and cross-session cases, CORS exact-origin
  behavior, development-auth regression.
- Browser: learner and instructor local issuer → result → exact frontend page;
  no local identity; logout; 390 px; keyboard; console and network inspection.
- Regression: full backend suite, frontend lint/build, pre-commit, diff check.

## Batch review

Passed after one targeted fix/recheck cycle. General security/quality and
product-UX reviews reported no remaining P0/P1 findings. The RAG evaluator
confirmed that no retrieval/model behavior changed and accepted the preserved
course isolation without a benchmark rerun.

Final gate: 127 backend tests, frontend lint and production build, repo-wide
pre-commit, `git diff --check`, signed learner/instructor browser flows,
credentialed CSRF mutation, logout, expiry, 1440 px and 390 px rendering,
keyboard focus, and successful-flow console checks passed.
