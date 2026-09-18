# M05 Canvas Letovo embedded course companion

Status: done

## User outcome

A learner launched from a Canvas Letovo course immediately recognizes the exact
course and its familiar ordered structure, knows where to continue, and can ask
for cited help without seeing integration setup or leaving the Canvas interface.

## Users and permissions

- Learner: inspect only published synthetic course structure, choose a source,
  and enter the existing protected tutor flow for the exact launched course.
- Instructor: the existing exact-course teacher route and intake controls remain
  available but are not redesigned in this slice.
- Methodologist, designer, and administrator: no new embedded actions.
- No role receives grades, submissions, messages, other-user data, or Canvas
  write capability.

## Context and evidence

- `development/PRODUCT.md`
- `development/ROADMAP.md`
- `development/ARCHITECTURE.md`
- `development/integrations/CANVAS.md`
- `development/security/SECURITY_BASELINE.md`
- `development/design/DESIGN_SYSTEM.md`
- `development/design/USER_FLOWS.md`
- `development/specs/done/M05-course-manifest-provenance.md`

Verified browser evidence from 2026-07-19 shows both module-route and
syllabus-first Canvas Letovo courses. It does not prove REST API, teacher/admin,
or server behavior. The completed local signed LTI boundary already routes a
learner to the exact bound course.

## Scope

- Add a lightweight local Canvas shell for deterministic browser testing. It
  owns no real Canvas code or data and renders synthetic dashboard, course
  navigation, and embedded LTI launch states only.
- Add two synthetic course fixtures:
  - an ordered module route with page, assignment, file, external URL, and
    section-label items;
  - a syllabus-first unit with goals, assessment summaries, criteria/demo files,
    and calendar context.
- Define a normalized, bounded course-map projection separate from the
  instructor intake manifest. Preserve module and item order, item type,
  published/available state, source reference, and external-source provenance.
- Render the learner entry surface inside simulated Canvas chrome with the exact
  course name, ordered map, and no more than three primary actions:
  `Продолжить по курсу`, `Спросить по материалам`, and `Открыть источник`.
- Route questions into the existing exact-course tutor boundary. Sources remain
  visible and link back to the authoritative simulated Canvas object.
- Keep the local signed-launch provider deterministic and production disabled.

## Non-goals

- Copying the school Canvas database, files, HTML, branding assets, users,
  credentials, cookies, or private course content.
- Running or modifying the official Canvas LMS code inside this repository.
- A real school Canvas API call, Developer Key, production OAuth exchange, or
  private-host/TLS exception.
- Cross-course dashboard, global/user navigation placement, teacher/admin UX
  redesign, file-body ingestion, external-site crawling, grades, submissions,
  messages, or writes.

## User flow

1. Launch a synthetic learner from the exact simulated Canvas course.
2. Keep Canvas chrome visible and open `Помощник курса` in the content frame.
3. Confirm the exact course and see its familiar ordered map.
4. Select a material and either continue, open the source, or ask for help.
5. Receive the existing cited answer/abstention behavior for that course only.

## UX contract

- Subject: a Canvas Letovo learner who wants to understand where they are and
  what to do next, not configure an integration.
- Preserve the Workshop Route visual language inside the tool frame, but let
  Canvas provide the surrounding navigation chrome. Do not imitate or duplicate
  the Canvas sidebar inside the tool.
- The exact course name and current location precede product branding.
- Learner copy must not contain OAuth, scope, import, synchronization, manifest,
  provenance, embedding, RAG, model, or token terminology.
- Item rows use Canvas-recognizable labels: `Страница`, `Задание`, `Файл`,
  `Внешний источник`, and `Раздел`.
- External links are visibly marked before navigation. Empty, unavailable,
  loading, error, expired-session, wrong-course, and no-supported-content states
  explain the next safe action.
- At 1440 x 900 and 390 x 844 the embedded surface has no page-level horizontal
  scroll, body text is at least 16 px, dense evidence is at least 14 px, actions
  are at least 44 px, and keyboard focus remains visible.
- Reduced motion is respected. Untrusted titles and syllabus excerpts render as
  text only.

## Data and API

- No migration or persistence in this slice.
- Add a versioned read-only `course-map` response for the exact product session;
  it is not the instructor `canvas-sync-preview` contract.
- The response contains bounded course identity, optional syllabus summary,
  ordered modules/items, item type, availability, source reference, and explicit
  `canvas` or `external` destination provenance.
- Unknown item types fail to a visible unsupported-item state rather than being
  silently dropped or treated as a page.
- Fixtures and simulator routes are unavailable outside safe development mode.

## Security and privacy

- Reuse exact signed LTI session, user, organization, membership, registration,
  context binding, and course checks before returning a course map.
- The learner projection contains published/available material only and never
  exposes hidden teacher content, expected answers, grades, submissions,
  messages, roster data, tokens, cookies, or credential references.
- Treat titles, excerpts, filenames, URLs, and model output as untrusted.
- External destinations are displayed but never fetched by the backend in this
  slice. Reject unsafe schemes and render links with explicit external-source
  treatment.
- Simulator data is synthetic and must be visibly identified in development.

## Acceptance criteria

- [x] A signed synthetic learner opens the tool from the simulated current
  course and sees the exact course name without selecting an ID.
- [x] Both module-route and syllabus-first fixtures retain familiar order and
  expose page, assignment, file, external-source, and section-label states.
- [x] The learner can continue, ask, or open a source without encountering
  integration terminology.
- [x] Hidden/unavailable items, wrong course/user/role, expired session, and
  malformed topology fail closed without leaking data.
- [x] Existing instructor intake, tutor guards, citations, abstention, OAuth,
  LTI, and manual import behavior remain green.
- [x] Desktop/mobile iframe checks cover both fixtures, keyboard use, clean
  console, no horizontal overflow, and all bounded failure states.

## Test plan

- Unit: normalized ordering, item-type handling, bounds, unsafe URL rejection,
  and published-only projection.
- Service/API: exact learner and every permission/session/course failure.
- Frontend: lint, production build, loading/empty/error/unsupported states.
- Browser: simulator dashboard -> course -> signed LTI -> embedded companion at
  1440 x 900 and 390 x 844 for both fixtures.
- Regression: focused Canvas/LTI/tutor tests, full pytest, pre-commit, and
  `git diff --check`.
- Batch review: general, product/UX, and RAG/isolation reviewers.

## Batch review

The local frontend simulator sub-batch was reviewed on 2026-07-19 and rechecked
on 2026-08-01. It now has an explicit server-only synthetic-data gate, working
source-return links, deterministic supported answers plus abstention, bounded
loading/access/error/content states, accessible contrast and target sizes, and
desktop/mobile Canvas-like flows for both fixtures.

Frontend lint/build, targeted pre-commit, `git diff --check`, a disabled-gate
404 check, clean-console Playwright flows, 390 px overflow, mobile menu Escape
recovery, and the 14 px mobile Course Route label check passed. The active spec
remained open after that simulator-only review.

The protected integration sub-batch completed on 2026-08-01. `/course-map` now
uses only the exact learner product session, returns bounded ordered topology,
fails closed on conflicting publication/visibility, removed modules, locks,
dates, prerequisites, unsafe/credential-shaped/malformed URLs, and preserves an
explicit unsupported state. Signed learner launch now targets the Canvas-native
companion; selected modules are revalidated there and constrain tutor retrieval.

The companion passed frontend lint/build, desktop/mobile protected-session
browser checks, exact module handoff, clean console, and zero overflow. The
backend reached 300 full-suite tests before the final narrow hardening pass; 51
focused course-map/Canvas/LTI/tutor tests passed after it. Repo-wide pre-commit,
`git diff --check`, and general/product-UX/RAG-isolation targeted rechecks found
no remaining P0/P1. The spec stays active because the server-configured signed
launch still needs the full two-fixture simulator browser matrix and then a
separate clean self-hosted Canvas iframe verification.

The complete local simulator gate passed on 2026-08-02. A development-only,
idempotent bootstrap now creates both synthetic courses, their exact learner
bindings, stable LTI registrations, and an origin-validated resolver without
requiring a live Canvas instance. The local Playwright scenario starts at
the simulator dashboard, opens the exact course, performs the signed launch,
selects a module, asks a module-scoped question, validates supported citations,
and exercises all eight bounded failure states at 1440 x 900 and 390 x 844.

The production browser matrix later expanded to 12 tests across both roles and
both viewports without retries. The final backend suite passed 313 tests;
frontend lint/build, repo-wide pre-commit, and `git diff --check` also passed.
General, product/UX, and isolation rechecks found no remaining P0/P1. All local
acceptance criteria are complete. Clean self-hosted Canvas iframe, cookie,
registration, and role verification is intentionally separated into its own
queued integration spec because it requires a different environment and
evidence level.
