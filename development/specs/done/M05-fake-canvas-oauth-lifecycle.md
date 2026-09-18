# M05 Fake Canvas OAuth connection lifecycle

Status: complete

## User outcome

An organization administrator can configure the non-secret boundary for
read-only Canvas API access, complete a local fake authorization-code flow, see
that their own registration-scoped connection is ready, and disconnect it. The
same UI states truthfully that production authorization is unavailable.

## Users and permissions

- Organization administrators may inspect and update the non-secret Canvas API
  configuration for an in-scope LTI registration.
- An administrator may start, complete, or disconnect only their own OAuth
  connection for that registration.
- Other organization roles, course-scoped LTI sessions, local users without the
  administrator membership, and cross-organization users receive a
  non-disclosing denial.
- The fake Canvas issuer and fake exchange exist only with safe development
  authentication and disappear in production or external-auth modes.

## Context and evidence

- `development/STATUS.md`
- `development/ARCHITECTURE.md`
- `development/integrations/CANVAS.md`
- `development/security/SECURITY_BASELINE.md`
- `development/design/DESIGN_SYSTEM.md`
- Canvas OAuth2 documentation: authorization-code callbacks return `code` and
  `state`; token exchange repeats the exact redirect URI; one `scope` parameter
  contains space-separated scopes; credentials require secure server custody.
- Current behavior: the current-course preview accepts a registration/user-
  scoped connection provider, while the production provider always reports no
  connection and no real Canvas adapter or credential store exists.

## Scope

- One migration for a registration-scoped non-secret OAuth configuration,
  one-use authorization attempts, user-scoped connection metadata, and
  content-minimal lifecycle events.
- Exact HTTPS Canvas API origin validation with no network request or DNS lookup.
- A server-derived exact callback URI and fixed read-only Course, Modules,
  Pages, and Assignments scopes.
- An encrypted-secret-store protocol with a fail-closed production adapter and
  an in-memory development adapter that receives only runtime-generated fake
  credential material.
- A fake code issuer/exchanger with no Canvas call, real token, roster,
  submission, grade, activity, import, or write path.
- Administrator status/configure/start/callback/disconnect API boundaries.
- A Workshop Route UI panel on the existing Canvas installation page.

## Non-goals

- A real Developer Key, client secret input, real authorization endpoint, token
  exchange, refresh, encrypted production store, or Canvas HTTP adapter.
- Making the existing current-course preview read from the new metadata; a real
  connection provider remains a later audited slice.
- Student or teacher authorization UI, roster sync, submissions, grades,
  learner activity, imports, background sync, or Canvas writes.
- Production activation, deployment, host allow-list changes, or mutation of a
  Canvas instance.

## User flow

1. The administrator opens the Canvas installation route and chooses one of the
   organization's existing LTI registrations.
2. They save the exact Canvas API origin and the separate scoped Developer Key
   Client ID; no secret is requested or accepted.
3. In safe local development they choose `Проверить тестовое подключение`, see
   the fake issuer's explicit read-only consent boundary, and allow or deny it.
4. The callback consumes the state once, completes only a fake exchange, and
   returns to the same route with a connected or denied result.
5. The panel shows who owns the connection, its four scopes, expiry, fake mode,
   exclusions, and a `Отключить тестовое подключение` action.

## UX contract

- Information hierarchy: connection purpose, route station/status, non-secret
  configuration, personal connection evidence, exclusions, then action.
- The signature element is a physical-looking read route from `Canvas API`
  through a sealed `OAuth` checkpoint to `Текущий курс`; it encodes the actual
  trust sequence rather than decorating the panel.
- Desktop uses an asymmetric two-column configuration/evidence bench. Mobile
  stacks it without horizontal scrolling and keeps primary controls at least
  44 px high.
- Required states: loading, no registration, not configured, ready to test,
  authorizing, connected, denied, callback failure, stale vault reference,
  production disabled, permission denial, disconnect confirmation, and retry.
- Visible copy never says that Canvas was contacted in the fake flow. Success
  says that only the custody boundary was tested.
- Keyboard focus moves to actionable errors or callback result; controls have
  visible focus and reduced motion is respected.

## Data and API

- `canvas_oauth_configurations`: one row per LTI registration with organization,
  exact API origin, non-secret OAuth client ID, and optimistic version.
- `canvas_oauth_attempts`: SHA-256 state digest, exact redirect/origin/client and
  scope snapshots, expiry, and consumption timestamp. Raw state/code are never
  persisted.
- `canvas_oauth_connections`: one registration/user row with opaque vault
  reference, fixed granted scopes, fake mode, expiry, connected and revoked
  timestamps. No credential material is serialized.
- `canvas_oauth_events`: content-minimal configured/connected/disconnected event
  metadata without origins, scopes, codes, states, or credentials.
- Admin GET/PUT status/configuration, POST start/disconnect, anonymous callback,
  and development-only fake consent endpoints.
- Configuration updates use an expected version and fail while an active
  connection exists; disconnect is explicit.
- Responses are schema-versioned and `no-store`.

## Security and privacy

- Backend membership checks pin organization, registration, user, and role.
- API origin accepts one canonical HTTPS origin only: no credentials, path,
  params, query, fragment, or implicit normalization of an arbitrary URL.
- Callback URI and frontend return origin are server-derived and exact.
- State is random, stored only as a digest, expires after ten minutes, and is
  consumed under a row lock on allow or deny. Replays fail closed.
- Callback ignores and never reflects provider descriptions; only bounded
  internal result codes reach the frontend.
- Fake authorization validates one exact scope parameter and all OAuth request
  fields. The fake code is bound to the state and callback.
- Secret-store and exchange defaults are unavailable outside safe development;
  no UI or schema accepts a client secret or token-shaped field.
- All pages and API responses use no-store/referrer protections where relevant.

## Acceptance criteria

- [x] An in-scope administrator can save exact non-secret configuration and
  complete the fake allow flow from the product UI back to a connected status.
- [x] Denial consumes the attempt, creates no connection, and returns a clear
  retry path.
- [x] Replayed, expired, duplicated, mismatched, cross-registration, malformed,
  or wrong-scope requests create no connection and disclose no sensitive data.
- [x] Production/external-auth mode exposes no fake issuer and cannot start or
  exchange a connection.
- [x] Status and event payloads contain no raw state, code, credential material,
  client secret, roster, submission, grade, activity, or Canvas content.
- [x] Disconnect removes the fake vault entry, revokes only the current user's
  connection, and leaves the configuration intact.
- [x] Configuration conflict and stale-vault states preserve data and explain
  the recovery action.
- [x] The existing LTI launch, registration, binding, pilot-health, and Canvas
  current-course preview regressions remain green.

## Test plan

- Unit: exact origin, callback and frontend-origin validation; scope and request
  construction; secret-store fail-closed behavior; fake code binding.
- Service/API: permissions, optimistic configuration, one-use/expiry/denial,
  callback mismatches, connection replacement, disconnect, event minimization,
  production disappearance, and schema rejection of unexpected secret fields.
- Browser: configure, allow, deny/retry, connected, disconnect, stale/error,
  production-disabled presentation, desktop/mobile, keyboard, focus, overflow,
  and console.
- Regression: focused LTI/Canvas tests followed by full pytest, frontend lint
  and build, pre-commit, and `git diff --check`.

## Batch review

- General quality and product/UX reviews were repeated after the fix pass and
  reported no remaining P0/P1 findings.
- Fixed before close: callback membership revalidation, configuration/callback
  serialization, malformed-host rejection, and disconnect-confirmation focus.
- `python -m pytest -q` passed 260 tests after all fixes. The focused Canvas/LTI
  suite passed 101 tests; frontend lint/build, repo-wide and targeted
  pre-commit, PostgreSQL migration rehearsal, and `git diff --check` passed.
- Browser QA covered allow/callback, connected, disconnect confirmation/cancel,
  stale-vault recovery, desktop and 390 px mobile, zero overflow, clean console,
  callback-result focus, and disconnect focus recovery.
- Deferred P2 work: production exchange/store/adapter, bounded attempt cleanup,
  uniform cache/referrer headers on all error responses, safer fake-consent
  action semantics, and simpler technical copy/native-select behavior on small
  screens.
