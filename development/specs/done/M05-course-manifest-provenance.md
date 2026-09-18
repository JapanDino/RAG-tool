# M05 Bounded course manifest and provenance

Status: complete

## User outcome

A Canvas-launched instructor with an active read connection can review the
bounded course structure that would enter a later audit before anything is
persisted: module, page, and assignment totals, representative items, read
limits, and evidence of whether the data is synthetic or came from Canvas.

## Users and permissions

- Only an active instructor product session for the exact bound registration
  and course may inspect the manifest.
- Students, local identities, other courses or registrations, expired/revoked
  sessions, removed memberships/bindings, and absent connections receive the
  existing non-disclosing or bounded unavailable states.
- No role can import, persist, publish, or write to Canvas in this batch.

## Context and evidence

- `development/STATUS.md`
- `development/ARCHITECTURE.md`
- `development/integrations/CANVAS.md`
- `development/security/SECURITY_BASELINE.md`
- `development/design/DESIGN_SYSTEM.md`
- `development/specs/done/M05-current-course-read-sync-preview.md`
- `development/specs/done/M05-instructor-oauth-handoff.md`

Verified behavior: the exact LTI instructor boundary and personal fake OAuth
handoff are complete. The current preview returns count-only `snapshot` data and
a sibling `snapshot_mode`; this lets future consumers ignore provenance. The
development provider is network-free and the production provider is unavailable.

## Scope

- Replace the count-only preview with a schema-version 2 bounded manifest.
- Bind provenance inside the manifest as a discriminated
  `synthetic_development` or `test_fixture` contract; both require
  `canvas_contacted=false`.
- Return exactly three canonical groups: modules, pages, and assignments. Each
  contains a non-negative total, at most five representative items, stable
  source references, published state when known, preview/read truncation, and
  no body HTML.
- Expose fixed read limits: ten source pages and 500 objects per collection,
  five preview items per group, and 200 characters per displayed title.
- Validate adapter output at the service boundary and fail to
  `source_unavailable` on malformed, oversized, duplicate, inconsistent, or
  provenance-ambiguous manifests.
- Extend the Workshop Route ready state with a three-part review ledger and
  clear synthetic provenance.

## Non-goals

- Real Canvas HTTP, tokens, pagination execution, private-host access, TLS, or
  approved encrypted secret storage.
- Persisting/importing the manifest or changing the existing course dataset.
- Reading page bodies, assignment descriptions, files, quizzes, outcomes,
  rosters, users, submissions, grades, activity, or unpublished answers.
- Comparing manifest content, running RAG/audit/model jobs, detecting changes,
  background sync, or Canvas writes.
- Claiming that the deterministic development manifest describes a real course.

## User flow

1. The instructor enters the exact course through a signed LTI launch and has a
   live personal read connection.
2. The existing Course Route verifies the course, scopes, and connection.
3. A review ledger shows totals and bounded representative objects for modules,
   pages, and assignments together with the provenance and read limits.
4. The instructor can refresh the manifest or disconnect. No import action is
   offered in this batch.

## UX contract

- Subject: a teacher checking the intake boundary of one Canvas course. The
  single job is to understand what categories and representative objects would
  be read before a later import.
- Preserve Workshop Route tokens and the current Canvas -> course -> snapshot
  route. Extend the route into one tactile intake ledger; avoid generic KPI or
  settings cards.
- The ledger uses three canonically ordered paper strips with totals, up to five
  item rows, publication state, and explicit `Показано N из M`. Synthetic
  development uses the yellow review note and the phrases `Canvas не вызывался`
  and `Синтетический состав`.
- Desktop uses three columns below the route. At 390 px they stack vertically,
  retain 16 px body text and 44 px actions, and produce no horizontal scroll.
- Loading, OAuth/configuration, scope mismatch, unverified source, unavailable,
  malformed manifest, ready synthetic, refresh, reconnect, disconnect, expired
  session, and permission denial remain bounded and actionable.
- Manifest changes are announced politely; focus behavior from the OAuth batch
  remains intact. Untrusted titles render as text only. Reduced motion applies.

## Data and API

- No migration or persistence change.
- `GET /courses/{course_id}/canvas-sync-preview` moves to `schema_version=2`.
- Ready responses contain `manifest`; all other states contain `manifest=null`.
  The old `snapshot` and `snapshot_mode` fields are removed.
- `manifest.provenance` is a discriminated union. The two currently allowed
  kinds require `canvas_contacted=false`; a future real adapter must add a new
  schema branch rather than reusing a synthetic kind.
- `manifest.groups` contains exactly modules, pages, assignments in order.
  Source references are bounded opaque adapter references, not credentials or
  browser-supplied URLs.
- Existing endpoint authorization, no-store behavior, boundary, scopes, and
  exclusion fields remain unchanged.

## Security and privacy

- Reuse exact LTI course/registration/user/instructor/binding checks before
  connection lookup or manifest read.
- Require exact equality with the fixed four read scopes.
- Treat adapter titles and references as untrusted data: bound length and count,
  reject control characters/duplicates, serialize as text, and never render HTML.
- Do not include tokens, state/code, vault references, learner data, page or
  assignment bodies, or model prompts in API, UI, events, logs, or screenshots.
- The development adapter remains deterministic and network-free; production
  remains unavailable.

## Acceptance criteria

- [x] A connected exact instructor receives a schema-version 2 manifest with
  embedded synthetic provenance and three bounded canonical groups.
- [x] The UI clearly distinguishes totals from representative items and says
  that Canvas was not contacted and nothing was imported.
- [x] Malformed provenance, group order/kind, counts, duplicate references,
  oversized titles/items, or inconsistent truncation fail closed without data.
- [x] Missing/extra scopes, wrong target/role/session/binding, unavailable
  custody, and production default perform no manifest read.
- [x] Refresh preserves exact-course selection and disconnect still removes only
  the instructor's fake access.
- [x] Existing OAuth/LTI/teacher/manual-import behavior remains green.

## Test plan

- Unit: deterministic manifest, provenance discriminator, bounds, canonical
  groups, duplicate and truncation validation.
- Service/API: exact instructor ready output and every bounded failure state.
- Frontend: lint and production build.
- Browser: local signed LTI teacher at 1440 x 900 and 390 x 844; connected
  ledger, refresh, disconnect/reconnect, focus, clean console, zero overflow.
- Regression: focused Canvas/OAuth/LTI tests, full pytest, pre-commit, and
  `git diff --check`.

## Batch review

- Outcome: the exact Canvas-launched instructor can inspect a non-persisted
  schema-version 2 manifest with embedded provenance, canonical modules/pages/
  assignments groups, representative items, source references, and hard limits.
- Automated checks: 45 focused Canvas preview/handoff tests and 296 full backend
  tests passed; frontend lint and production build, repo-wide pre-commit, and
  `git diff --check` passed. No migration was added.
- Browser checks: signed LTI -> fake OAuth -> exact course passed at 1440 x 900
  and 390 x 844. Refresh, disconnect/reconnect, clean console, source wrapping,
  5.65:1 source-reference contrast, and zero mobile overflow were verified.
- Reviews: general quality and RAG/isolation reviews passed. Product/UX passed
  after the bounded fix pass raised evidence text to 14 px, shortened the live
  announcement, and made repeated refresh announcements distinct.
- P0/P1: none remain.
- Deferred by scope: a real Canvas transport adapter, production credential
  custody, institutional private-host/TLS evidence, and committed browser E2E.
