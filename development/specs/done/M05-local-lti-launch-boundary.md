# M05 — Local LTI 1.3 launch boundary

Status: done

## User outcome

An already-authorized school user can follow the same browser-mediated LTI 1.3
launch sequence that Canvas will use and reach a calm confirmation screen for
the exact internal course and role. The screen makes clear that the launch was
verified and that Canvas was not read from or modified.

## Users and permissions

- A bound learner may launch only as the existing `student` member of the bound
  course.
- A bound instructor may launch only as the existing `instructor` member.
- A bound Canvas designer may launch only as the existing `program_designer`
  member.
- A bound administrator may launch only when an active administrator membership
  exists in the bound course organization.
- Anonymous, mentor/observer, unknown, inactive, cross-organization, unbound, or
  role-mismatched users receive a non-disclosing refusal.
- Only an authenticated local administrator may create the development-only
  registration and explicit bindings used by the test issuer.

## Context and evidence

- `development/ROADMAP.md`: M05 requires LTI 1.3 launch, identity/role mapping,
  automatic course context, read-only behavior, and teacher/student flows.
- `development/ARCHITECTURE.md`: Canvas data and identifiers cross a trust
  boundary; tokens and signed messages must not enter logs or prompts.
- `development/security/SECURITY_BASELINE.md`: internal Canvas access requires
  exact configuration and TLS trust rather than a broad private-network bypass.
- [1EdTech LTI Core 1.3](https://www.imsglobal.org/spec/lti/v1p3/): resource-link
  claims, deployment, target link, subject, roles, context, and version contract.
- [Canvas LTI launch overview](https://canvas.instructure.com/doc/api/file.lti_launch_overview.html):
  Canvas-specific issuer, OIDC redirect, public-JWK validation, and state flow.
- [Canvas role mapping](https://www.canvas.instructure.com/doc/api/file.canvas_roles.html):
  current Canvas LTI 1.3 role URIs.

## Scope

- Persist a registered issuer/client/deployment, explicit platform-subject to
  internal-user bindings, and explicit platform-context to internal-course
  bindings.
- Persist short-lived, one-use login state and nonce digests; never persist the
  raw ID token, state, nonce, login hint, or optional profile claims.
- Implement third-party login initiation, authorization redirect, JWT/JWKS
  verification, required LTI claim checks, replay protection, and exact
  authorization mapping.
- Add a development-only issuer with an ephemeral RSA key and a small launch
  chooser so the entire browser flow works without Canvas access.
- Render success and refusal screens that are usable in an iframe, on desktop,
  and on mobile.
- Add focused service/API tests for successful and fail-closed flows.

## Non-goals

- No Canvas API, OAuth client-credentials, roster, grade, submission, module, or
  content access.
- No creation or update of users, memberships, organizations, or courses from
  launch claims.
- No application-wide external session or replacement of the current local
  identity selector; that is the next vertical slice after the launch boundary.
- No Canvas write, deep linking, Assignment and Grade Services, or Names and
  Role Provisioning Services.
- No acceptance of arbitrary private JWKS hosts. Real self-hosted Canvas TLS and
  DNS allow-list work remains blocked until deployment facts are known.
- No production use of the development issuer or HTTP endpoints.

## User flow

1. A local administrator opens the development launch chooser for one explicitly
   bound course and selects a bound scenario.
2. The local issuer starts OIDC login at the tool; the tool creates state and
   nonce digests and redirects the browser back to the registered authorization
   endpoint.
3. The issuer returns a signed `LtiResourceLinkRequest`; the tool verifies the
   state, nonce, signature, issuer, audience, deployment, target, message type,
   version, subject, context, and resource-link claims.
4. The tool intersects Canvas roles with existing internal permissions and
   renders the exact course/role confirmation. No Canvas read or write occurs.

## UX contract

- The chooser is explicitly labelled as a local integration check, not Canvas.
- The result hierarchy is: verification state, course, resolved role, privacy
  boundary, next step.
- Primary actions are `Проверить запуск` and `Вернуться к выбору`.
- Busy state relies on native navigation; no control remains deceptively active.
- Empty state explains that an administrator must first create explicit bindings.
- Error/permission states reveal no internal user, course, registration, or
  organization IDs and never echo JWT content.
- Success states say `Canvas не изменён` and do not imply that synchronization or
  a product session has happened.
- Keyboard focus is visible; form controls have labels; status is textual as
  well as colored; no horizontal page scrolling at 390 px.

## Data and API

- Migration `0033_lti_launch_boundary.sql` adds registrations, subject bindings,
  context bindings, launch attempts, and privacy-minimal launch audit events.
- `POST /integrations/lti/login` accepts the standard form/query initiation
  parameters and returns a redirect only for one exact active registration.
- `POST /integrations/lti/launch` consumes `state` and `id_token` as form data and
  returns a no-store HTML result.
- Development-only endpoints provide bootstrap, chooser, authorize, and JWKS.
- Registrations are unique by issuer/client/deployment. Subject and context
  bindings are case-sensitive and unique within a registration.
- Launch attempts expire after five minutes and can be consumed exactly once.
- Audit events store outcome/reason and bound internal IDs when known, but no
  token, state, nonce, login hint, names, email, or raw role list.

## Security and privacy

- Allow only `RS256`; select a key by a non-empty `kid`; reject missing/unknown
  keys and malformed JWK sets.
- Verify signature, `iss`, `aud`/`azp`, expiry, issued-at, and nonce with a small
  clock-skew allowance. Require exact LTI 1.3 resource-link claims.
- Hash state and nonce with SHA-256 and compare digests; consume state in the
  database before authorization mapping so a failed launch cannot be replayed.
- Use only the stable `(issuer, subject)` identity. Never use email or name to
  bind or provision a user.
- Treat all claims and issuer responses as untrusted input; escape every value
  rendered into HTML and cap identifier lengths.
- Follow redirects neither for JWKS nor authorization endpoints. Production
  registration requires HTTPS; loopback HTTP is development-only.
- Ignore unknown claims and roles. Do not infer methodologist roles.
- Return generic public refusal copy while retaining a bounded reason code in an
  audit event.

## Acceptance criteria

- [x] A bound learner and instructor each complete a standards-shaped local
      launch and see the correct existing course and role.
- [x] State and nonce are one-use, expire, and reject tampering or replay.
- [x] Wrong signature, issuer, audience, deployment, target, message type,
      version, subject, context, resource link, or role fails closed.
- [x] An LTI role cannot elevate or replace the stored internal membership.
- [x] Unknown subjects and contexts do not create records or disclose whether an
      internal course/user exists.
- [x] Raw tokens, state, nonce, login hints, email, and names are absent from
      persisted launch/audit rows and ordinary error responses.
- [x] Development issuer endpoints return 404 outside safe development auth.
- [x] The successful screen explicitly says the launch is verified and Canvas
      was not changed; the refusal screen offers a safe return action.

## Test plan

- Unit: role URI intersection, claim validation, identifier bounds, state/nonce
  hashing, JWKS key selection, URL policy.
- Service: active/inactive/cross-organization bindings and replay consumption.
- API: OIDC redirect shape, signed learner/instructor launch, malformed and
  adversarial claims, production-disabled local issuer.
- Browser: chooser through auto-posted launch on desktop and mobile; keyboard,
  success, empty, refusal, console, and overflow checks.
- Regression: full backend suite, frontend lint/build, pre-commit, diff check.

## Batch review

General and product-UX reviews passed after one targeted fix pass with no
remaining P0/P1 findings. The pass added safe same-origin return actions,
strict organization-administrator resolution, exact development chooser
eligibility, and a regression for the live-server JWKS/event-loop boundary.

Deferred P2 work: pin the connected JWKS address against DNS rebinding, add
rate limiting and expired-attempt cleanup, cache issuer keys with bounded
rotation behavior, and rehearse migration/replay concurrency on PostgreSQL.
The real Canvas issuer, internal TLS/DNS, iframe policy, and multi-node behavior
remain external pilot checks rather than locally verified facts.
