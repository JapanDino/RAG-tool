# Current status

Last verified: 2026-09-18 (source transfer checks; live readiness unchanged)

## 2026-09-18 AURUS transfer checkpoint

- Complete source checkpoint prepared on `J-D-polish-ui-and-stability` for
  `JapanDino/RAG-tool`, including migrations through 0049, synthetic fixtures,
  tests, development records, and the frozen research protocol.
- Continue using `development/handoffs/AURUS_HANDOFF.md`. August 2 online
  handoffs are historical and must not restart completed simulator work.
- Fresh backend verification after formatting/import cleanup: 485 tests passed.
  Frontend lint and production build passed. Repo-wide pre-commit and staged
  whitespace checks passed. No product behavior changes were intended in this
  transfer; formatting hooks normalized files and nine unused imports were removed.
- Gitleaks 8.30.1 scanned the complete staged source snapshot: three reviewed
  false positives (two synthetic idempotency keys and one test-only CSRF value),
  no confirmed credentials. Exact comparison against locally discovered secret
  values found no matches. The full `.secrets/` directory is now ignored.
- Independent transfer review found no P0/P1 issues. This was a scoped
  publication/continuation review, not a new product security audit. Browser E2E,
  PostgreSQL concurrency, real Canvas and production checks were not rerun.
- Local environment files, credentials, database volumes, browser state, QA
  screenshots, generated output and dependency caches are outside this Git
  checkpoint. Configure them separately on AURUS; do not assume database transfer.
- Commit and remote verification identifiers are supplied in the transfer
  response. Known product limitations and external approval gates below remain.

## Active milestone

Active — approved-environment readiness for the role-aware Canvas agent. B07A
through B07F, B09, and B10A through B10C are complete offline: the signed
learner companion supports a bounded multi-turn route; administrators control
organization role and model-host policy; program authors can record one human
evidence-linked decision; and the bilingual research protocol is frozen before
real outcomes. Production model-host calls, real Canvas transport, participant
collection, and school Canvas remain fail-closed until approved infrastructure,
trusted approvals, and real manifests are available.

## Verified

- FastAPI, PostgreSQL/pgvector, Redis/Celery, and Next.js architecture exists.
- Course audit, remediation Copilot, course Q&A, Canvas import, Canvas alignment
  evaluation, feedback export, and evaluation protocol code exists.
- Canvas integration is currently read-only and token-driven.
- Canvas change sets describe `create_page`, `create_assignment`, and
  `update_assignment` operations without applying them.
- `python -m pytest -q` passed 57 tests on 2026-07-13.
- The model client supports an OpenAI-compatible base URL.
- M01 identity and roles is complete: local development identities,
  organizations, course memberships, backend authorization, audit events, and a
  role-aware `/workspace`.
- The authenticated course boundary returns non-disclosing denials and removes
  staff-only course metadata from student summaries.
- `python -m pytest -q` passed 59 tests on 2026-07-13.
- Frontend lint and production build passed; `/workspace` was checked at
  1440 × 900 and 390 × 844 with no browser console errors or warnings.
- The teacher attention queue is complete: latest audit health, prioritized
  findings, inspectable evidence, confidence language, and authenticated review.
- The grounded remediation flow is complete: confirmed findings can produce a
  cited, editable draft; acceptance records the authenticated reviewer and never
  mutates Canvas.
- `python -m pytest -q` passed 61 tests on 2026-07-13.
- The remediation UI passed lint/build and desktop/mobile browser checks with no
  console errors or warnings.
- The first safe student-tutor slice is complete: student-owned history,
  published-content boundaries, assessment guidance, deterministic abstention,
  visible citations, and redacted reviewer/source metadata.
- `python -m pytest -q` passed 66 tests on 2026-07-13.
- The student tutor passed frontend lint/build and browser checks for normal,
  guidance, and abstention states at 1440 × 900 and 390 × 844 with no console
  errors or warnings.
- Batch quality, product UX, and RAG reviews reported no P0/P1 findings.
- Teacher-facing tutor quality is complete: 30-day active-student aggregates,
  validated citation integrity, owner-only feedback provenance, small-sample
  suppression, and server-defined operational signals without transcripts.
- `python -m pytest -q` passed 72 tests on 2026-07-13.
- The tutor quality panel passed lint/build and populated desktop, populated
  mobile, and empty-state browser checks with no console errors or warnings.
- Batch quality, product UX, and RAG/metrics repeat reviews reported no P0/P1
  findings.
- Teacher-configurable tutor policy is complete: instructor/admin updates use
  optimistic concurrency and authenticated audit events; student/methodologist
  access is read-only; arbitrary prompts and safety overrides are not accepted.
- Pausing blocks new questions without removing history. Balanced, guided, and
  concise styles change presentation only; retrieval eligibility, assessment
  guidance, citation validation, and abstention remain immutable.
- Stored answers snapshot policy version/style, and the teacher/student UI shows
  the active policy plus permanent safety boundaries.
- `python -m pytest -q` passed 74 tests on 2026-07-13.
- Frontend lint/build and teacher/student desktop/mobile browser checks passed
  with no console errors; implementation, UX, and RAG/safety reviews reported
  no P0/P1 findings.
- Student tutor readiness benchmark v1 is complete: 18 committed synthetic RU/EN
  cases cover supported and unsupported retrieval, assessment protection,
  normal help, and prompt-injection-shaped questions.
- Evaluation Protocol v2 now requires Recall@K, MRR, abstention, guard accuracy,
  labeled citation support, offline p95, and a course-scoped runtime retrieval
  smoke. It records the dataset SHA-256, ranking-pipeline version, fixed benchmark
  config, and effective deployment retrieval config separately.
- Empty, hidden-only, non-queryable, and effectively non-retrievable courses fail
  readiness. The production retrieval selection adapter is shared with the
  deterministic benchmark, while the course smoke uses the deployed provider
  and limits.
- `python -m pytest -q` passed 81 tests on 2026-07-14. Frontend lint/build,
  strict benchmark CLI, targeted pre-commit, general batch review, and final RAG
  recheck passed with no remaining P0/P1 findings.
- M03 tutor data lifecycle is complete: students see the effective retention
  period and can hard-delete only their own course history; administrators can
  set one of four bounded organization periods and trigger content-free purge
  results without transcript access.
- Daily Celery cleanup and explicit administrator purge use the same service.
  Policy changes and purge serialize on the organization row; owner deletion
  repeats organization and active-student scope checks inside the service.
- Student and administrator lifecycle UI passed populated, confirmation, busy,
  success, empty, error, desktop/mobile, console, and keyboard checks. General
  and product-UX targeted rechecks reported no remaining P0/P1 findings.
- `python -m pytest -q` passed 84 tests on 2026-07-14. Frontend lint/build,
  targeted pre-commit, and development/production Compose validation passed.
- M04 program foundations are complete: organization-scoped programs, canonical
  program-course order, competencies, course contributions, optimistic versions,
  and content-safe change events are covered by one migration and service/API
  boundaries.
- Program designers and administrators can author through the protected API;
  methodologists can inspect; instructors and students receive non-disclosing
  denials. Cross-organization courses and evidence are rejected before writes.
- `/workspace/programs` exposes a responsive competency route with factual
  `unmapped`, `learning_only`, and `assessed` states plus live, manual, and
  missing-evidence drill-down. It never serializes assessment expected answers
  or presents coverage as an automatic quality verdict.
- `python -m pytest -q` passed 88 tests on 2026-07-14. Frontend lint/build,
  repo-wide pre-commit, desktop/mobile and delayed-loading browser checks, and
  general/product-UX targeted rechecks passed with no remaining P0/P1 findings.
- Program designers and administrators can create a real program, assemble and
  reorder its canonical course tape, add competencies, and save live or manual
  evidence-backed course contributions in one contextual workbench. A
  methodologist keeps the read-only map without authoring controls.
- Authoring course summaries and evidence choices are bounded and organization
  scoped; expected answers and model metadata remain private. Course-order
  writes cannot omit an existing course, exact no-ops preserve the version, and
  all related writes use optimistic concurrency with content-safe events.
- Conflict recovery preserves dirty course and contribution drafts. Partial
  success is distinguished from failed writes and locks further writes until a
  refresh; the selected live source exposes type, review state, confidence, and
  a plain-text excerpt before saving.
- `python -m pytest -q` passed 90 tests on 2026-07-14. Focused program tests,
  frontend lint/build, repo-wide pre-commit, desktop/mobile and recovery browser
  checks, and general/product-UX targeted rechecks passed with no remaining
  P0/P1 findings.
- Methodologists, program designers, and administrators can run a deterministic
  read-only audit of the selected program map. It reports explicit missing
  coverage, assessment, or evidence plus one cautious assessed-before-learning
  sequence signal; instructors, students, and cross-organization users receive
  non-disclosing denials.
- Findings expose stable keys, rule-confidence language, review state, bounded
  plain-text evidence, and explicit analysis/output truncation. Evidence is
  resolved in batches, expected answers and model metadata stay private, and
  incomplete data cannot create absence-based sequence findings.
- The “Контрольная рейка” UI passed populated, loading, empty, error/retry,
  truncated, low-confidence, permission, keyboard/focus, desktop/mobile, clean
  console, and delayed-request program-switch checks. The general and product/UX
  targeted rechecks reported no remaining P0/P1 findings.
- `python -m pytest -q` passed 91 tests on 2026-07-17. Focused program tests,
  frontend lint/build, repo-wide pre-commit, and `git diff --check` passed.
- The administrator-only program portfolio overview is complete: active maps
  are listed alphabetically with exact bounded course, competency, mapping, and
  declared-assessment counts. The ledger contains no quality score, ranking,
  teacher/student data, model call, or write side effect.
- Overview actions pin the exact organization and program. Routes with
  competencies open the existing evidence-backed audit in one action; stale or
  cross-organization links fail closed without falling back to another map.
- `python -m pytest -q` passed 92 tests on 2026-07-17. Frontend lint/build,
  repo-wide pre-commit, desktop/mobile and edge-state browser checks, and
  general/product-UX targeted rechecks passed with no remaining P0/P1 findings.
- The previous administration overview was re-audited for multi-organization
  use. Workspace and overview links now pin the exact administrator organization;
  foreign, stale, and malformed organization/program targets fail closed without
  selecting another program or starting its audit.
- Program audit preview now emits one medium-confidence `duplication_check` when
  the same explicitly saved `introduced` or `developed` stage appears in at
  least two canonical courses. Normal progression and repeated assessment alone
  do not trigger it, and incomplete analysis suppresses the conclusion.
- Each candidate exposes canonically ordered, ownership-validated evidence,
  explicit per-finding truncation, neutral review status, and an intentional-
  spiral boundary. It uses no model, embedding, prompt, learner activity, score,
  write, or Canvas mutation.
- `python -m pytest -q` passed 92 tests on 2026-07-17. Focused program tests,
  frontend lint/build, repo-wide pre-commit, `git diff --check`, desktop/mobile
  browser checks, and general/product-UX/RAG reviews passed with no P0/P1.
- Explicit same-program prerequisite relations are now persisted with
  self-link, cycle, scope, bounded-output, and optimistic-version protection.
  Exact no-ops preserve version; create/update/delete events contain IDs but not
  rationale text.
- Program maps expose the author rationale, earliest saved prerequisite
  assessment, earliest saved target start, source review state, and one cautious
  structural state: missing evidence, order to review, or structure matching the
  declared order. No relation is inferred and no state proves learner readiness.
- The “Линии предпосылок” UI supports explicit create/update/delete, cycle draft
  retention, truthful partial-refresh recovery with write locking, read-only
  methodologist access, neutral missing-evidence styling, and all three states.
- `python -m pytest -q` passed 93 tests on 2026-07-17. Frontend lint/build,
  repo-wide pre-commit, `git diff --check`, desktop/mobile, keyboard, overflow,
  clean-console, update, cycle, and mocked partial-refresh checks passed.
  General, product-UX, and RAG targeted rechecks reported no remaining P0/P1.
- A local LTI 1.3 test issuer now exercises the browser-mediated OIDC login,
  signed resource-link launch, JWKS verification, and one-use state/nonce flow
  without a real Canvas instance. Development endpoints disappear outside safe
  development authentication.
- Registrations, platform subjects, and platform course contexts require exact
  active bindings. Canvas learner, instructor, designer, and administrator roles
  can only intersect existing internal permissions; launch claims never create
  users, memberships, courses, or elevated roles.
- Success and refusal screens are no-store, iframe-ready, non-disclosing, and
  explicit that Canvas was neither read nor changed. The real local issuer flow
  passed desktop/mobile, keyboard, 390 px overflow, safe-return, expected replay
  refusal, and clean successful-console checks.
- `python -m pytest -q` passed 116 tests on 2026-07-17. Frontend lint/build,
  repo-wide pre-commit, `git diff --check`, and general/product-UX targeted
  rechecks passed with no remaining P0/P1 findings.
- Verified learner and instructor launches now issue a 60-minute, host-only
  HttpOnly product session and route to the exact bound tutor or teacher page.
  Designer and administrator confirmations do not receive this unsupported
  product handoff, and a prior browser session is cleared.
- Only a SHA-256 session digest is persisted. Active-session issuance is
  serialized on the LTI registration and protected by a partial unique index;
  active registration, organization, user, exact course, membership, and role
  are rechecked on every request.
- Cookie-authenticated writes require a same-session HMAC CSRF header. CORS
  credentials are enabled only for validated exact HTTP(S) origins; wildcard
  members and hostile preflights fail closed. Organization actions and other
  courses remain inaccessible.
- Learner and teacher pages use credentialed requests without putting identity
  or session credentials in URLs or localStorage. Loading, denied, transient
  failure, expired/revoked, logout, desktop/mobile, 390 px overflow, and keyboard
  states were checked in the real local signed-launch flow.
- `python -m pytest -q` passed 127 tests on 2026-07-17. Frontend lint/build,
  repo-wide pre-commit, `git diff --check`, general/security and product-UX
  targeted rechecks passed with no remaining P0/P1 findings; RAG review was not
  applicable and confirmed preserved course isolation.
- Public Canvas configuration now exposes one anonymous course-navigation
  placement, no service scopes, server-derived login/launch URLs, and a bounded
  public-only RSA JWKS with deterministic ETag and weak/strong conditional 304.
- Organization administrators can inspect truthful readiness, copy the Canvas
  package, create/edit inactive production registration drafts, and explicitly
  activate/deactivate them. Active fields cannot change silently; mutations
  serialize on the registration row and content-minimal audit events record
  field names only.
- Draft saving performs no DNS lookup or fetch. Activation requires an exact
  platform host allow-list, rejects malformed endpoints and unsafe resolved
  addresses, and preserves the draft on failure. Unexpected URL, state, or
  private-key-shaped request fields fail validation.
- The installation-route UI passed empty/draft/active/error/success, copy,
  desktop/mobile, 390 px overflow, keyboard confirmation/error focus, and clean-
  console checks. It keeps activation distinct from a verified first launch.
- `python -m pytest -q` passed 153 tests on 2026-07-17. Frontend lint/build,
  repo-wide pre-commit, `git diff --check`, general/security and product-UX
  targeted rechecks passed with no remaining P0/P1 findings.
- UX01 expressive workspace foundation is complete. `/workspace` and the Canvas
  registration route now share a distinctive educational-atlas system with a
  functional Course Thread/orbit, richer asymmetric hierarchy, role-aware
  navigation, and responsive Canvas connection route without adding external
  fonts, images, libraries, API changes, or permissions.
- Course selection now exposes selected state and its controlled action panel;
  narrow screens move to the panel with reduced-motion support. Disabled mobile
  destinations keep an explicit `скоро` status, raw configuration has visible
  focus, copy confirmation remains announced, and practical controls meet the
  44 px target baseline.
- Frontend lint/build, `git diff --check`, 1440 x 900 and 390 x 844 screenshots,
  zero mobile horizontal overflow, clean browser console, keyboard focus, and
  general/product-UX targeted rechecks passed with no remaining P0/P1 findings.
- UX02 design comparison is complete at
  `/design-lab/workspace-hero-variants`: five concepts render the same workspace
  hero content through distinct Orbit, Workshop, Layers, Portal, and Folded Map
  compositions. The route uses static content only and does not change the
  production workspace.
- Exactly one concept can be selected with native radio semantics, unique
  accessible names, visible focus, live and sticky text confirmation, and
  reduced-motion handling. Frontend lint/build, 1440 x 900 and 390 x 844
  screenshots, zero mobile overflow, clean console, and general/product-UX
  reviews passed with no remaining P0/P1 findings.
- UX03 full-page Workshop workspace prototype is complete at
  `/design-lab/workshop-workspace`. It extends the selected UX02 direction into
  a responsive administrator shell with a route sidebar, organization context,
  full hero, selectable synthetic courses, and a live current-course panel.
- The prototype is static and does not request APIs, persist data, alter Canvas,
  or change the production `/workspace`. Inactive destinations use native
  disabled controls with a visible prototype explanation.
- Frontend lint/build, 1440 x 900 and 390 x 844 screenshots, zero horizontal
  overflow, clean console, keyboard focus, course selection, and general plus
  product/UX targeted rechecks passed with no remaining P0/P1 findings.
- UX04 Workshop product migration is complete. Workshop Route is now the
  canonical production and future-UI contract in the design system and agent
  guide; external font requests were removed in favor of the local Cyrillic
  system stack.
- The root laboratory, role-aware workspace, teacher and student course views,
  Canvas installation, program map, and program portfolio share the same grid
  paper, workshop ink, route cobalt, evidence mint, note yellow, apricot marker,
  typography, action hierarchy, focus treatment, and state surfaces. The
  production workspace now uses the approved linear Course Route instead of the
  earlier orbit metaphor.
- The legacy root footer now speaks in user outcomes under the Kontur identity;
  developer links are collapsed under an explicit developer section. Workspace
  transport failures are localized and state what was preserved and how to
  retry. Mobile retains compact workspace and settings controls.
- Frontend lint/build, desktop and 390 px route screenshots, zero final
  horizontal overflow, permission-state review, and general/product-UX targeted
  rechecks passed with no remaining P0/P1 findings.
- Verified LTI launches now quarantine only missing opaque subject/context
  identifiers after signature and mandatory-claim validation. Invalid launches
  create no candidates, raw identifiers are never returned to the UI, and no
  launch claim auto-creates a user, course, role, or membership.
- Organization administrators can inspect masked first/last-seen evidence,
  choose an existing in-scope target, confirm one explicit binding, dismiss a
  request, and see the required Canvas relaunch instruction. Cross-organization,
  expired, dismissed, and repeated resolution fails closed.
- Candidate plaintext is cleared on resolution and by an independent bounded
  hourly Celery expiry task. The local issuer proves that a rejected unbound
  launch succeeds only after the explicit binding and a new signed launch.
- The M05 rehearsal applies all 36 migrations to an empty disposable PostgreSQL
  database and skips all 36 on the checksum-backed second pass. It verifies
  migrations `0033`–`0036`, 11 critical constraints, and 3 critical indexes.
- Simultaneous first capture now converges on one pending candidate with
  `seen_count = 2`; simultaneous resolution produces one binding/event, one
  safe `candidate_unavailable` loser, and clears candidate plaintext.
- Rehearsal wrappers fail closed on migration, runner, or cleanup errors. The
  database guard requires an explicit disposable flag and a segmented
  `rehearsal`/`test` database marker; no port, persistent volume, container, or
  network remains after the run.
- `python -m pytest -q` passed 169 tests on 2026-07-18. Repo-wide pre-commit and
  the general quality recheck passed with no remaining P0/P1 findings.
- The production LTI preflight validates production/external-auth mode, exact
  HTTPS CORS/frontend/browser-API/tool origins, public-only RSA JWKS, exact
  platform host scope, iframe cookie policy, and the CSRF secret without DNS,
  HTTP, database, Canvas, or deployment access.
- Preflight output is versioned, contains codes/statuses only, and exits `2` on
  local blockers. Real Canvas version, Developer Key, TLS, iframe behavior,
  role accounts, pilot course, signing-key ownership, rollback, and retention
  stay explicitly external rather than being reported as passed.
- Host validation rejects wildcard/malformed/loopback origins, ambiguous
  browser-normalized IPv4 forms, and IPv4-mapped IPv6 loopback. The focused
  preflight suite passed 66 tests after the general quality recheck.
- `python -m pytest -q` passed 235 tests on 2026-07-18; repo-wide pre-commit
  passed.
- Organization administrators now see a fixed seven-day production LTI launch
  route with accepted/rejected counts, bounded failure families, unresolved
  subject/context backlog, and explicit manual pause triggers. The aggregate
  excludes local development registrations and never exposes raw reason codes,
  users, courses, roles, registration IDs, or platform identifiers.
- The Workshop Route panel covers not-started, stable, pending-binding,
  failure/stop, inactive-registration, loading, error, stale-data, and retry
  states. Registration lifecycle and binding resolution refresh the aggregate;
  no state disables a registration or changes Canvas automatically.
- `python -m pytest -q` passed 239 tests before review. The post-review focused
  LTI suite passed 72 tests; frontend lint/build, targeted pre-commit, desktop
  and 390 px browser checks, zero-overflow, clean-console, focus, and
  activation/deactivation recovery checks passed. General and product/UX
  targeted rechecks reported no remaining P0/P1 findings.
- A Canvas-launched instructor can now inspect a content-minimal read-only
  preview for the exact current course. Exact LTI course/registration/context
  binding, instructor membership, a server-derived HTTPS Canvas source, and four
  explicit Course/Modules/Pages/Assignments read scopes are required; local
  identities, students, other registrations, malformed sources, and cross-target
  fake reads fail closed.
- Credential custody is isolated behind a registration/user-scoped connection
  provider: routers and response schemas never receive a token. The production
  default has no connection and returns `oauth_required`; deterministic fake
  transport tests cover ready counts, missing scopes, provider/vault failure,
  retry recovery, and exact origin/course enforcement without a Canvas host.
- The Workshop Route teacher panel shows Canvas -> current course -> preview,
  aggregate course/module/page/assignment counts, explicit exclusions, and
  loading, OAuth-required, scope-mismatch, unverified-source, failure, retry, and
  ready states. It never imports content or changes Canvas.
- `python -m pytest -q` passed 246 tests before review. After the fix pass, 9
  focused tests, targeted pre-commit, frontend lint/build, and `git diff --check`
  passed. Desktop and 390 px browser checks covered ready, missing-scope,
  expected failure, retry recovery, keyboard flow, clean ready console, and zero
  overflow. Loading/ready panel heights were 876/878 px at 390 px; general and
  product/UX targeted rechecks found no remaining P0/P1.
- Organization administrators can now save only the exact HTTPS Canvas API
  origin and separate non-secret OAuth Client ID for an existing registration.
  Fixed Course/Modules/Pages/Assignments read scopes, a server-derived callback,
  ten-minute one-use state, active-admin revalidation, and registration/config
  locking protect the fake authorization-code lifecycle.
- Connection ownership is registration/user scoped. Raw state, code, credential
  material, client secret, Canvas content, rosters, submissions, grades, and
  activity never enter API/event payloads. Production secret storage, exchange,
  and Canvas transport remain unavailable by default.
- The Workshop Route panel exposes the actual trust route `Canvas API -> OAuth
  -> current course`, non-secret configuration, human-readable scope evidence,
  exclusions, stale-vault recovery, and an explicit disconnect confirmation.
- `python -m pytest -q` passed 260 tests after all review fixes. The focused
  Canvas/LTI suite passed 101 tests; frontend lint/build, pre-commit, migration
  `0037` PostgreSQL rehearsal, `git diff --check`, desktop/mobile browser QA,
  clean console, zero overflow, and keyboard-focus recovery passed. General and
  product/UX rechecks reported no remaining P0/P1 findings.
- A Canvas-launched instructor can now inspect, start, complete, retry, and
  disconnect the fake OAuth handoff only for the exact active product session,
  registration, user, course, context binding, source origin, and external
  Canvas course. Allow, denial, bounded exchange/storage failure, and callback
  replay return only to that teacher course; student, stale, replaced, changed,
  or cross-target contexts fail closed.
- Migration `0038` persists explicit admin/instructor attempt context. The fake
  provider checks expiry, revocation, process-local custody, exact origin/course,
  and exact equality with the four read scopes; it never reads credential
  material or calls Canvas. Fake preview counts are deterministic and visibly
  marked `Canvas не вызывался` and `Синтетический тест`.
- The Workshop Route exposes state-specific teacher guidance and a visible
  `Подключить тестовое чтение` action, with bounded configuration, reconnect,
  production-disabled, denial, failure, busy, confirmation, and focus states.
- `python -m pytest -q` passed 274 tests on 2026-07-19. Frontend lint/build,
  repo-wide pre-commit, `git diff --check`, desktop/mobile signed-LTI browser QA,
  zero overflow, and clean console passed. Disposable PostgreSQL applied all 38
  migrations twice and passed callback-versus-relaunch concurrency. General,
  product/UX, and RAG/isolation rechecks found no remaining P0/P1.
- The exact Canvas-launched instructor preview now returns a schema-version 2,
  non-persisted manifest with embedded `synthetic_development` or `test_fixture`
  provenance. Modules, pages, and assignments are canonical, bounded, carry
  stable source references and publication state, and distinguish collection
  totals from at most five representative items.
- Adapter output fails closed on ambiguous provenance, malformed shapes,
  duplicate or unsafe references, oversized text/counts, inconsistent
  truncation, naive timestamps, and invalid scope metadata. The deterministic
  development provider remains network-free and production remains unavailable.
- The Workshop Route teacher view now presents one tactile intake ledger with
  honest synthetic provenance, explicit read limits, no-import language,
  wrapped evidence references, and a concise refresh announcement. Desktop and
  390 px signed-LTI checks passed with clean console and zero mobile overflow.
- `python -m pytest -q` passed 296 tests on 2026-07-19; the focused manifest and
  handoff suite passed 45 tests. Frontend lint/build, repo-wide pre-commit, and
  `git diff --check` passed. General, product/UX, and RAG/isolation reviews found
  no remaining P0/P1. No migration was required.
- Read-only observation of the authenticated Canvas Letovo learner interface on
  2026-07-19 verified two materially different course shapes: an ordered
  module route with external links/pages/assignment/attachment, and a
  syllabus-first unit with goals, assessment tables, criteria files, and
  calendar context. No grade, submission, message, or other-user data was read
  and no Canvas state was changed.
- The local synthetic Canvas simulator UI slice is complete behind two
  server-only enablement flags. It provides a familiar dashboard, module-route
  and syllabus-first demo courses, assignments, source return links, a bounded
  course assistant preview, honest abstention, and deterministic fail-closed
  loading/access/error/content states without connecting to school Canvas.
- Frontend lint/build, targeted pre-commit, `git diff --check`, server-gate 404,
  desktop/mobile browser checks, clean console, 390 px overflow, mobile-menu
  keyboard recovery, and the final 14 px Course Route check passed on
  2026-08-01. General and product/UX review findings for this frontend slice
  were remediated; the broader M05 integration remains active.
- The learner entry now uses a versioned read-only `/course-map` derived only
  from the exact signed product session; no course ID is selected in its URL.
  It exposes only bounded published/available topology, rejects conflicting or
  malformed visibility, stale removed modules, unsafe or credential-shaped
  URLs, and marks unknown item types unsupported.
- Signed learner launches now land on `/canvas-companion`. Its Workshop Route
  screen keeps at most three Canvas-familiar actions, distinguishes external
  destinations, and passes the selected exact module through the protected
  tutor boundary so retrieval is limited to that module. The simulator can
  embed one server-configured development LTI registration per synthetic course
  and remains unavailable in production.
- `python -m pytest -q` passed 300 tests before the final fail-closed URL and
  publication recheck; the final focused course-map/Canvas/LTI/tutor suite
  passed 51 tests. Frontend lint/build, repo-wide pre-commit, `git diff --check`,
  1440 x 900 and 390 x 844 protected-companion browser checks, exact module
  handoff, clean console, and zero overflow passed. General, product/UX, and
  RAG/isolation targeted rechecks found no remaining P0/P1.
- The local M05 simulator gate is complete. A development-only idempotent
  bootstrap now seeds both synthetic course shapes, exact learner and instructor
  bindings, and stable LTI registrations; an origin-validated actor resolver
  connects the Canvas shell to the exact role-specific signed product route
  without static IDs or a live Canvas host.
- A production Playwright suite now covers dashboard -> exact course -> signed
  learner launch -> companion -> selected-module tutor and instructor launch ->
  exact teacher workspace for both fixtures at 1440 x 900 and 390 x 844. It
  also checks all eight bounded states, keyboard recovery, resolver denial,
  role isolation, warning/error-free console, zero horizontal overflow, visible
  item types, and module-scoped citations. The final matrix passed 12 tests
  without retries on 2026-08-02.
- `python -m pytest -q` passed 313 tests after the simulator role hardening.
  Frontend
  lint/build, repo-wide pre-commit, and `git diff --check` passed. Final general,
  product/UX, and LTI-isolation rechecks found no remaining P0/P1.
- B02 ModelGateway is complete: one server-owned structured task supports mocked
  DeepSeek/Gemma-shaped OpenAI envelopes with exact-origin validation, no
  redirects, bounded streaming response reads, finite timeouts, retry/circuit/
  concurrency limits, strict schema validation, deterministic fallback, and
  secret-safe content-free organization metadata in migration `0039`.
- Only authenticated organization administrators can read the no-store AI
  readiness projection; compatibility bypass, every other role, and cross-org
  requests fail non-disclosingly. Rendering never probes the provider.
- The Canvas operations workspace now shows product-language AI readiness with
  distinct disabled/configured/ready/degraded/error/stale states, four aggregate
  metrics, explicit recovery guidance, and no provider details or transcripts.
  Final evidence: 341 full backend tests, 28 focused gateway tests, frontend
  lint/build, 20/20 desktop/mobile Playwright scenarios, all-files pre-commit,
  `git diff --check`, and quality/safety/RAG/UX rechecks with no remaining P0/P1.
- B03 role policy and routing are complete. `POST /agent/v1/messages` derives
  user, organization, course, role, registration, and session only from the
  authenticated boundary; CSRF, HMAC-scoped idempotency, owner isolation, exact
  execution-time rechecks, and stable no-store errors fail closed.
- The immutable `agent-tools.v1` registry contains 20 exact existing, adapter,
  or planned boundaries with closed field sets, versions, role allow-lists,
  time/output limits, evidence contracts, failure maps, and content-safe audit
  descriptors. Multi-intent requests clarify; assessment and injected control
  text cannot elevate a learner.
- AgentRun persistence contains no raw message, response, prompt, retrieved
  excerpt, or transcript. Event replay expires at 24 hours; student deletion
  removes linked metadata; the 30-day global purge includes inactive
  organizations. No tool, provider, Canvas call, or mutation occurs in B03.
- Final B03 evidence: 367 backend tests, 97 focused agent/LTI/model regressions,
  repo-wide pre-commit, `git diff --check`, and quality, agent-safety, and RAG
  targeted rechecks passed with no remaining P0/P1 findings. No UI changed, so
  no B03 screenshots were required.
- B07A program route brief is complete. Signed organization/user/role/program/
  version references drive a deterministic, read-only assistant route with SQL
  aggregate counts, at most three authoritative audit priorities, evidence and
  review state, confidence language, visible truncation, and a direct audit
  handoff. Changed maps or evidence abstain instead of serving a stale result.
- The Workshop Route UI covers loading, result, empty, error/retry, stale-map
  refresh, program switching, focus, reduced motion, and mobile overflow. Final
  evidence: 409 backend tests, frontend lint/build, 34/34 desktop/mobile Canvas
  simulator scenarios, repo-wide pre-commit, `git diff --check`, and the batch
  review gate with no remaining P0/P1 findings.
- B07B administrator operations route is complete. An active administrator can
  request one signed organization-scoped route that reduces existing LTI
  registration, seven-day launch, 30-minute school-model, and retention-policy
  projections to exactly four evidence-windowed stations and at most three
  ordered actions. It stores only a digest and makes no Canvas, model, policy,
  or infrastructure write.
- One failed database projection now yields a truthful partial route with an
  unavailable station instead of discarding the other current evidence.
  Changed source state makes a completed route abstain, and every non-admin or
  changed membership fails closed without exposing organization details.
- The Workshop Route administrator UI passed its 8 desktop/mobile normal,
  stale, error/retry, partial, focus, handoff, console, and overflow scenarios.
  Final B07B evidence: 418 backend tests, frontend lint/build, repo-wide
  pre-commit, `git diff --check`, agent-safety review, and targeted quality/UX
  rechecks with no remaining P0/P1. One pre-existing full-suite focus scenario
  was transiently flaky and passed its isolated unchanged recheck.
- B07C administrator analytics tape is complete. It compares two equal 28-day
  adoption windows at an indivisible five-non-admin-user threshold and two equal
  24-hour content-free model-runtime windows. It exposes no person, course,
  workflow, prompt, transcript, provider, or model breakdown and never treats
  increased use as proof of learning quality.
- Cost appears only when both server-owned token rates are valid. Exact
  normalized rates are part of the hidden stale-result digest but never the API
  response or tool events; even a rate change that preserves the rounded public
  price invalidates the completed tape. One failed SQL source preserves a
  truthful partial result, and at most one handoff opens an existing control.
- The continuous Workshop Route control tape passed no-activity, privacy-
  suppressed, runtime-attention, unconfigured-cost, partial, stale, retry,
  focus, keyboard, console, and overflow states on desktop and mobile. Final
  B07C evidence: 426 backend tests, frontend lint/build, 54/54 Canvas simulator
  tests, repo-wide pre-commit, `git diff --check`, and targeted quality/UX/
  agent-safety rechecks with no remaining P0/P1.
- B07D program evidence routes are complete. Methodologists, program designers,
  and administrators can choose one saved program and ask for the first bounded
  gap candidate or the first explicitly declared prerequisite line that needs
  evidence/order review. Each route returns at most one candidate, four evidence
  anchors, visible uncertainty/review/truncation, and one exact handoff to the
  existing audit or prerequisite surface; it makes no model, Canvas, or write
  call and never infers learner readiness.
- Completed evidence routes use a canonical source fingerprint over the full
  bounded audit/relation projection, raw source IDs/content/status, and public
  route. Program version changes, a changed nonselected relation, or a hidden
  evidence-text change abstain instead of serving a stale result. Revoked access
  moves to the existing non-disclosing terminal permission screen.
- The Workshop Route fork passed candidate, clear, empty, partial, stale,
  permission, retry, program-switch, focus, keyboard, reduced-motion, clean-
  console, and overflow states on desktop and mobile. Final B07D evidence: 443
  backend tests, frontend lint/build, 72/72 Canvas simulator tests, repo-wide
  pre-commit, `git diff --check`, and quality/UX/agent-safety rechecks with no
  remaining P0/P1.
- B07E administrator data custody is complete. An active administrator can run
  one signed, deterministic `admin.policy_status.v1` workflow that shows the
  effective tutor-data retention period, the separate 30-day agent metadata
  boundary, two policy-version rows, and at most one latest content-free
  organization cleanup receipt. It invokes no model, Canvas call, policy write,
  deletion, or purge.
- Receipt projection is limited to organization-wide automatic/admin cleanup
  events with no course or subject association. Absence is described honestly:
  an empty cleanup may run without creating a receipt. Policy and receipt SQL
  sources fail independently into a partial result without exception details.
- The result fingerprint includes effective policy source state and the exact
  latest safe receipt identifier/content, so a policy change or a new otherwise-
  identical receipt abstains instead of projecting stale evidence.
- The Workshop Route retention ruler and receipt ledger passed default-policy,
  current/previous receipt, no-receipt, partial, stale, retry, disclosure-focus,
  keyboard, reduced-motion, clean-console, and overflow checks on desktop and
  mobile. Final B07E evidence: 452 backend tests, frontend lint/build, 82/82
  Canvas simulator tests, repo-wide pre-commit, `git diff --check`, and quality/
  UX/agent-safety rechecks with no remaining P0/P1.
- B10B completed the administrator agent-policy control plane: organization
  role routes and deterministic-only/model-host mode are versioned, previewed,
  confirmed, audited, and rechecked at admission and execution without exposing
  a public write key or weakening immutable safety boundaries.
- B10C completed the offline model-host handoff: DeepSeek and Gemma profiles use
  the production structured-output parser on committed synthetic envelopes;
  report, JSON export, and CLI share one deterministic, content-free projection.
  Origin and runtime diagnostics are independent, malformed dormant URLs remain
  bounded, and profile validation follows exact administrator authorization.
  The Workshop Route passport passed coherent refresh failure, keyboard focus,
  safe download, desktop/mobile, overflow, and clean-console checks. Final B10C
  evidence: 461 backend tests, frontend lint/build, 104/104 Canvas simulator
  scenarios, repo-wide pre-commit, and quality/UX/agent-safety rechecks with no
  remaining P0/P1.
- B07F program review notes are complete. Program designers and administrators
  can ask the deterministic program agent for one current gap candidate, inspect
  bounded evidence/confidence/review state, edit the proposed note, choose
  `act`, `observe`, or `dismiss`, and explicitly confirm a versioned save.
- Signed draft references bind organization, user, role, program version,
  finding, and the complete evidence-source digest. A saved decision is exposed
  as current only for the exact same evidence state; changed sources abstain or
  conflict, literal replay is stable, and content-free events exclude note text.
- The Workshop Route review desk preserves dirty edits across cancelled or
  failed program switches, moves focus to confirmation/conflict/receipt, and
  keeps Canvas and the program map unchanged. Final B07F evidence: 464 backend
  tests, frontend lint/build, 112/112 Canvas simulator scenarios, repo-wide
  pre-commit, `git diff --check`, and quality/UX/agent-safety rechecks with no
  remaining P0/P1.

## Known gaps

- The tutor benchmark is a small synthetic regression gate, not an independent
  teacher-validated acceptance sample. Labeled lexical citation support does not
  prove semantic entailment, and offline p95 excludes database, provider, model,
  network, concurrency, and cost.
- Canvas prerequisite/progress visibility remains deliberately fail-closed until
  real learner-specific Canvas semantics can be tested.
- Historical tutor feedback without actor user IDs is conservatively excluded
  from the new student-helpfulness aggregate.
- Tutor-quality thresholds are product defaults and are not yet empirically
  calibrated; quote integrity does not prove answer entailment.
- Real Canvas iframe cookie behavior, institutional TLS/DNS, registration policy,
  and browser storage restrictions remain untested. The read-only preview and
  OAuth custody contracts exist, but the real code exchange, approved encrypted
  secret store, refresh lifecycle, and Canvas read adapter are still absent.
- Local/private Canvas addresses remain blocked unless both the exact platform
  and exact private-host allow-lists deliberately permit the institutional host.
- Frontend is concentrated in a small number of large files.
- The browser E2E suite is included in the AURUS source checkpoint; it was not
  rerun during transfer preparation. Its historical evidence remains dated.
- The synthetic matrix cannot prove real Canvas iframe cookie/session behavior.
  A clean self-hosted Canvas must still verify registration, storage policy,
  institutional TLS/DNS, and learner/teacher role behavior before M05 can be
  completed or used as evidence for the school instance.
- `npm audit --omit=dev` still reports the transitive `sharp <0.35.0` libvips
  advisory through Next.js. Its offered automatic fix is a breaking Next.js
  downgrade, so dependency remediation needs a deliberate upgrade path rather
  than `npm audit fix --force`.
- The accumulated implementation is included in the AURUS source checkpoint;
  source publication does not establish production or research readiness.
- Local Claude settings contain a value that resembles a provider credential;
  it must be removed and rotated before the baseline is considered safe.
- Policy concurrency still needs a real PostgreSQL test; SQLite does not exercise
  `SELECT FOR UPDATE` semantics.
- Scheduled retention cleanup currently commits all organizations in one task;
  per-organization transaction isolation and retry/backoff remain to be added.
- Tutor styles still need provider-level groundedness, latency, and token-cost
  benchmarks before a production pilot.
- The B10C synthetic envelopes prove only local parser and configuration
  contracts. They do not prove real DeepSeek/Gemma availability, quality, TLS,
  latency, or school-network compatibility. Browser export validation remains a
  secondary shallow guard over the server-owned closed schema.
- A dedicated browser/API regression should cover opening existing history while
  the tutor is paused and a question already in flight during a concurrent pause.
- M04 still lacks semantic similarity across differently named competencies.
  The current sequence, duplication, and explicit-prerequisite signals remain
  narrow structural review prompts, not inferred curriculum verdicts.
- Program optimistic locking and migrations `0031`/`0032`/`0049` still need a
  real PostgreSQL concurrency/rehearsal check; SQLite tests do not exercise
  `SELECT FOR UPDATE`.
- The development demo currently reserves a conventional program code rather
  than storing explicit demo provenance.
- Expired/revoked product-session rows do not yet have a bounded cleanup job.
  Multi-tab relaunch can leave an older tab with a stale cached CSRF value until
  it reloads, while the backend continues to reject its writes.
- Product-session locking and migration `0034` still need a real PostgreSQL
  concurrency/rehearsal check; SQLite tests do not exercise `SELECT FOR UPDATE`.
- Registration mutation locking and migration `0035` still need a real
  PostgreSQL concurrency/migration rehearsal; SQLite does not exercise
  `SELECT FOR UPDATE`.
- DNS validation and the later TLS connection are not IP-pinned, so exact
  operator-controlled host allow-lists reduce but cannot eliminate DNS
  rebinding/TOCTOU risk.
- The organization-level registration UI still needs approved production SSO;
  course-scoped LTI product sessions correctly cannot enter this admin flow.
- The Canvas Developer Key must still be created manually. Signing-key
  ownership/rotation, TLS, iframe behavior, role accounts, rollback ownership,
  and retention approval have an explicit runbook gate but still need real-host
  evidence.
- Pilot health currently applies the seven-day lower bound but does not exclude
  future-dated audit events caused by clock skew. Registration-health lifecycle
  recovery has browser QA but no committed E2E regression yet.
- The development OAuth vault is intentionally process-local, so a server
  restart produces `reconnect_required`. Expired authorization attempts do not
  yet have a bounded cleanup task, and the fake consent action should move away
  from state-changing GET semantics before broader automated browser use.
- OAuth error responses still need one uniform no-store/referrer header policy,
  and an invalid frontend return-origin configuration can strand the browser
  after an otherwise completed exchange.
- Agent migrations `0040`-`0044`, real PostgreSQL lock/statement-timeout
  behavior, and concurrent final-execute recovery still need a rehearsal in an
  approved PostgreSQL environment; Docker Desktop was not running during B04.
- The administrator operations route still needs PostgreSQL timeout/load
  rehearsal, explicit tampered-reference and mid-run authorization-revocation
  regressions, and a real-host check of server-global versus organization-scoped
  readiness signals. Its mobile route is intentionally complete but dense.
- The administrator analytics tape still needs PostgreSQL aggregate/p95 load
  evidence, explicit cross-organization and mid-run revocation regressions, and
  content-safe unavailable-source tool-event classification. Its technical
  runtime vocabulary should be simplified before a broad nontechnical pilot.
- The prerequisite agent route still builds the full program map before its
  bounded response. A dedicated relation/evidence projection should apply the
  deadline before ORM hydration; legacy/imported relation sets above the limit
  should return partial before claiming a globally first candidate.
- `AgentRun.course_id ON DELETE SET NULL` and inactive-organization purge
  receipts remain production-hardening work.
## Current batch

B09 is complete under
`development/specs/done/B09-research-protocol-freeze.md`. The repository now
contains a closed machine-readable preregistration, deterministic JSON/Markdown
exports, blinded course-level RU/EN split tooling, fixed Canvas-search and RAG
comparisons, teacher calibration rules, grounding/safety gates, privacy guards,
and explicit external blockers. The frozen protocol SHA-256 is
`0772898f365df58300f15f45912f61e83633534b629269694f33f0688f99dddd`.
This is research infrastructure, not classroom-effectiveness or real-Canvas
evidence. Final verification: 21 focused tests, 485 full backend tests,
pre-commit, frontend lint/build, `git diff --check`, and research-methodology,
RAG, agent-safety, and batch-quality reviews passed with no open P0/P1.

## Next batch

Start the queued clean self-hosted Canvas track when an approved isolated
environment is available. First verify B01 platform/version compatibility,
PostgreSQL migrations and concurrency, real role accounts, trusted approval and
dataset/split manifests, and the organization agent-host operations gate. Only
then prepare the approved B10 pilot and any teacher-confirmed Canvas write-back.
There is no metadata-only path from the offline repository to collection,
analysis readiness, production access, or a school-effectiveness claim.

## External blockers

- No server, REST API, Developer Key, or approved OAuth credential access to the
  school Canvas instance. Learner-browser access is product evidence only.
- No ability to deploy the project to the organization agent host yet.
- Canvas version, Developer Key policy, internal DNS, and TLS details are
  unknown.
- No teacher or Canvas administrator test account is currently available for
  role-specific interface validation.
