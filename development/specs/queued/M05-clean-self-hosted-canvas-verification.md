# M05 clean self-hosted Canvas verification

Status: queued

## User outcome

A synthetic learner and instructor can open the development tool from an
official clean self-hosted Canvas course and receive the exact role-specific,
course-scoped experience already verified by the local simulator.

## Users and permissions

- Synthetic learner: launch the exact published course companion and use only
  learner tools for that course.
- Synthetic instructor: launch the exact teacher workspace and use only
  instructor read-only tools for that course.
- Canvas test administrator: install and remove only the development LTI
  registration and create synthetic test identities/content.
- No role may access school Canvas data or mutate a non-test Canvas instance.

## Context and evidence

- `development/PRODUCT.md`
- `development/ROADMAP.md`
- `development/ARCHITECTURE.md`
- `development/integrations/CANVAS.md`
- `development/security/SECURITY_BASELINE.md`
- `development/specs/done/M05-letovo-embedded-course-companion.md`
- `development/specs/done/M05-synthetic-instructor-role-matrix.md`

The signed simulator provides deterministic product evidence but cannot prove
official Canvas placement, OIDC redirects, iframe/cookie behavior, browser
storage policy, or Canvas REST/OAuth compatibility. Docker CLI is installed but
the local Docker Engine was unavailable on 2026-08-02.

## Scope

- Start a separate official open-source Canvas LMS deployment containing only
  synthetic users, courses, modules, pages, files, assignments, and links.
- Install the development LTI 1.3 Course Navigation registration.
- Verify exact learner/instructor launches, issuer/client/deployment/JWKS,
  state/nonce/signature/audience, product sessions, expiry, logout, and replay.
- Verify iframe, third-party cookie/storage, responsive, and failure behavior.
- Exercise one explicitly scoped read-only Canvas API/OAuth connection and
  compare ordered topology/provenance with the internal course map.
- Document reproducible setup, teardown, rollback, and evidence collection.

## Non-goals

- Copying the school Canvas database, files, branding, HTML, users, credentials,
  cookies, or private content.
- Connecting to or changing `canvas.letovo.ru`.
- Production credential custody, school TLS/DNS policy, write-back, grades,
  submissions, messages, rosters, or Live Events.
- Redesigning learner or instructor product workflows.

## User flow

1. A synthetic user opens an exact synthetic Canvas course.
2. The user selects the registered Course Navigation placement.
3. Canvas completes OIDC/LTI launch into the embedded product frame.
4. The product derives the exact course and role and opens the bounded surface.
5. The tester verifies source return, expiry/logout, denial, and rollback.

## UX contract

- Canvas chrome remains authoritative around the tool iframe.
- Exact course and task precede product branding.
- Learner copy contains no integration jargon.
- Loading, blocked-cookie, expired-session, wrong-role, unavailable-tool, empty,
  and success states explain one safe recovery action.
- Desktop and 390 px iframe views have visible focus and no horizontal overflow.

## Data and API

- No school or production data.
- Reuse existing LTI registration, subject/context binding, product-session,
  course-map, teacher-workspace, OAuth, and Canvas import contracts.
- Any deployment-only configuration stays secret-safe and outside committed
  fixtures.
- Record Canvas/version/configuration evidence without credentials.

## Security and privacy

- Treat Canvas claims, course HTML, URLs, and API responses as untrusted.
- Require exact issuer/client/deployment/host and active internal membership.
- Reject replay, cross-course, cross-role, expired, revoked, and unsafe-host
  paths without revealing resource existence.
- Never pass Canvas/provider credentials to a model, browser bundle, log, or
  Markdown file.

## Acceptance criteria

- [ ] Official clean Canvas launches both synthetic roles into their exact
  protected product routes.
- [ ] OIDC/LTI, iframe/cookie/storage, expiry/logout/replay, and mobile behavior
  have captured positive and negative evidence.
- [ ] Read-only Canvas topology preserves order, visibility, type, and source
  provenance for both synthetic course shapes.
- [ ] Cross-role/course and unsafe host/claim/token cases fail closed.
- [ ] Setup, teardown, rollback, and limitations are reproducible and contain no
  credential or school-data material.

## Test plan

- Service/API: LTI/OAuth/host/session positive and negative matrix.
- Browser: Canvas course -> placement -> exact tool -> source return for learner
  and instructor at desktop and 390 px.
- Integration: one read-only course sync, expiry, disconnect, and rollback.
- Regression: full backend, frontend lint/build, simulator Playwright, pre-commit,
  and `git diff --check`.
- Batch review: Canvas integration, batch quality, and product UX.

## Batch review

Pending environment availability and implementation.
