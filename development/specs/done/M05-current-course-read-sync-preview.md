# M05 Current-course Canvas read synchronization preview

Status: complete

## User outcome

An instructor who opens an exactly bound course from Canvas can see whether the
tool is ready to read that course, which content groups are in the read-only
snapshot, and why synchronization cannot start when configuration is incomplete.
Refreshing the preview never stores course content and never changes Canvas.

## Users and permissions

- A Canvas-launched instructor may inspect and refresh the preview for the exact
  course in the current LTI product session.
- A student, a local development identity, another course, another registration,
  and an unbound session receive no preview and no resource disclosure.
- An organization administrator configures the later OAuth connection outside
  this slice. The instructor UI gives a truthful handoff instead of accepting a
  pasted token.

## Context and evidence

- `development/ARCHITECTURE.md`
- `development/SECURITY.md`
- `development/integrations/CANVAS.md`
- `development/design/DESIGN_SYSTEM.md`
- `development/design/EXPERIENCE.md`
- `development/design/SCREEN_STATES.md`
- Canvas OAuth2 and Developer Key documentation:
  <https://developerdocs.instructure.com/services/canvas/oauth2/file.oauth>
  and
  <https://developerdocs.instructure.com/services/canvas/oauth2/file.developer_keys>
- Canvas endpoint documentation for Courses, Modules, Pages, and Assignments.

Verified current behavior: LTI product sessions already carry an exact internal
course and registration; context bindings are unique per registration and
course; imported Canvas courses preserve a Canvas course ID and source URL. The
existing manual importer accepts a user-provided token, but the product does not
yet have OAuth token custody or an automatic sync endpoint.

## Scope

- Add an explicit connection-provider boundary whose concrete connection owns
  credential use. Routers and response models never receive access or refresh
  tokens.
- Add a deterministic fake read connection for tests, with an exact expected
  Canvas origin and course ID.
- Require these four scopes for the preview:
  - `url:GET|/api/v1/courses/:id`;
  - `url:GET|/api/v1/courses/:course_id/modules`;
  - `url:GET|/api/v1/courses/:course_id/pages`;
  - `url:GET|/api/v1/courses/:course_id/assignments`.
- Add `GET /courses/{course_id}/canvas-sync-preview` for a Canvas-launched
  instructor and the exact current course.
- Resolve the Canvas origin and numeric course ID only from the already-bound
  internal course source. Never accept them from the request.
- Return content-minimal counts, source identity, required/missing scopes,
  snapshot time, and one of: `oauth_required`, `scope_mismatch`, `ready`,
  `course_source_unverified`, or `source_unavailable`.
- Add the read route to the teacher course workspace with refresh and all
  relevant states.

## Non-goals

- OAuth authorization, callback, refresh, revocation, encryption, or database
  persistence of credentials.
- Real Canvas HTTP calls, deployment-host exceptions, or environment-driven fake
  credentials.
- Reading rosters, users, enrollments, submissions, grades, analytics, quiz
  answers, unpublished bodies, or student activity.
- Importing or persisting content, scheduling background sync, diffing snapshots,
  running an audit, or writing to Canvas.
- Student, methodologist, program, or administrator synchronization screens.

## User flow

1. An instructor opens the tool from the Canvas Course Navigation placement.
2. The teacher workspace requests a preview for the course already fixed by the
   LTI product session; the user does not select a host or course ID.
3. The panel shows the route `Canvas -> current course -> local snapshot`, the
   read-only boundary, and either exact snapshot counts or one configuration
   blocker.
4. In a ready or recoverable connection-error state, the instructor can choose
   `Обновить снимок`; the response confirms that Canvas was only read and that
   nothing was imported or changed.

## UX contract

- Information hierarchy: source status and title first; route boundary second;
  snapshot counts or one blocker third; exclusions and refresh action last.
- Place the panel immediately after the course hero because Canvas content is the
  source for downstream course analysis.
- Extend Workshop Route with one functional read route. Use grid paper, workshop
  ink, route cobalt, evidence mint, and an apricot current-position marker; no new
  font, external asset, or generic integration dashboard.
- Desktop uses a source/status column beside a horizontal three-stop route and
  snapshot ledger. At 390 px the sections stack and the route becomes vertical
  without horizontal page scrolling.
- Loading keeps the panel footprint stable and says what is being checked.
- `oauth_required` says that the administrator must connect read-only Canvas
  access; it does not show a non-functional connect button.
- `scope_mismatch` names only missing required reads and says existing access was
  not broadened.
- `course_source_unverified` says that this internal course has no confirmed
  Canvas source and does not reveal another resource.
- `source_unavailable` says no content was imported or changed and offers
  `Повторить проверку`.
- `ready` shows course, module, page, and assignment counts plus a localized
  timestamp, and offers `Обновить снимок`.
- Permission failures remain the existing non-disclosing workspace failure.
- Every state has text in addition to color; controls have hover, disabled, busy,
  and visible keyboard focus states; status changes use an `aria-live` region;
  reduced motion is respected.

## Data and API

- No schema or migration changes.
- Extend the in-process principal with optional `registration_id`, populated only
  from a verified product session.
- The connection provider is an injectable process boundary. Its unavailable
  default makes production fail closed until a real encrypted OAuth adapter is
  implemented and approved.
- The fake transport returns deterministic aggregate counts only and rejects any
  origin/course request outside its configured expectation.
- Response schema version is `1`. No secret, token handle, full granted-scope
  list, content body, user identifier, roster, grade, or submission is returned
  or logged.
- The endpoint is cache-disabled because readiness and short-lived authorization
  can change between requests.

## Security and privacy

- Authorization requires an instructor membership, `auth_mode=lti_session`, an
  exact product-session course, an exact registration, and an exact context
  binding for that registration/course.
- Canvas origin and course ID are server-derived from the bound course. HTTPS,
  credential-free origin syntax, a positive numeric external ID, and a matching
  `/courses/{id}` source path are required before a connection is requested.
- The provider is keyed by registration and user. A future implementation must
  keep refresh tokens encrypted in an approved secret store and expose only a
  read connection, never plaintext credentials.
- Missing scopes are evaluated before any read. Only required missing scopes are
  returned; unrelated granted permissions are not disclosed.
- Imported HTML and model output are not involved in this preview. Fake payload
  titles are untrusted text and are rendered by React without raw HTML.
- Failures expose stable state codes and user guidance, not provider bodies,
  tokens, exception text, or internal connection identifiers.

## Acceptance criteria

- [x] A bound Canvas-launched instructor receives a ready preview from the fake
  adapter for the exact current course and sees four aggregate content counts.
- [x] The provider observes only the registration, user, server-derived origin,
  server-derived Canvas course ID, and the four declared read scopes.
- [x] A wrong course, student, local identity, absent/mismatched context binding,
  malformed source, or cross-origin/course fake request fails closed without a
  snapshot.
- [x] Missing connection and missing-scope responses make zero read calls and
  expose no credentials or unrelated scopes.
- [x] Provider failure becomes `source_unavailable`; retry can recover to
  `ready`; no content or Canvas write occurs in either case.
- [x] The teacher UI presents loading, ready, OAuth-required, scope-mismatch,
  unverified-source, error, and retry states at desktop and mobile widths.
- [x] Existing manual import, LTI launch, teacher workspace, and authorization
  tests remain green.

## Test plan

- Unit: source-boundary parsing, required-scope comparison, fake exact-target
  enforcement, provider failure mapping, and response minimization.
- Service/API: instructor ready path; absent connection; missing scopes; wrong
  course/registration binding; local identity and student denial; no-store
  header; provider call ledger.
- Frontend: lint and production build.
- Browser: LTI teacher route at 1440 x 900 and 390 x 844; ready, loading,
  OAuth-required, scope-mismatch, error, and recovered retry; keyboard focus,
  clean console, and zero horizontal overflow.
- Regression: focused Canvas/LTI/teacher suites, then the full backend gate and
  repository pre-commit gate at batch close.

## Batch review

- General review P1 fixed: `CanvasReadUnavailable` is mapped to the stable
  `source_unavailable` state during provider lookup, scope inspection, and
  snapshot reading. Lookup failure, recovery, and scope-metadata regressions are
  covered directly.
- Product UX P1 fixed: loading now preserves the same header, three-stop route,
  ledger, and footer structure as ready. At 390 px the measured panel heights
  are 876 px and 878 px respectively, with zero horizontal overflow.
- Direct student and different-registration isolation tests were added during
  the fix pass. Both targeted reviewer rechecks reported no remaining P0/P1.
- Deferred P2: an IPv6-literal course source would be reconstructed without URL
  brackets. The unavailable production provider prevents a real call in this
  slice; the future real adapter must reject or correctly normalize this target.
- Real OAuth custody, approved host/DNS/TLS validation, Canvas failure
  translation, pagination, and real-host behavior remain explicitly deferred.
