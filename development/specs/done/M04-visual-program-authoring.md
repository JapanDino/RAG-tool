# M04 — Visual program authoring

Status: complete

## User outcome

A program designer can create a real program and assemble its first inspectable,
evidence-backed competency route without calling the API manually.

## Users and permissions

- Program designer: create a program, add organization courses, reorder the
  declared course route, add competencies, and create or update one
  competency-course contribution.
- Administrator: the same authoring access for operational setup.
- Methodologist: keeps read-only access to the completed map and never sees
  authoring controls.
- Instructor and student: no cross-course map or authoring access.

## Context and evidence

- `development/STATUS.md` names visual authoring as the next M04 batch.
- `development/specs/done/M04-program-competency-map.md` defines the existing
  program entities, explicit course order, evidence boundary, permissions, and
  inspectable map.
- `development/PRODUCT.md` requires role-specific workflows and evidence before
  recommendations.
- `development/design/EXPERIENCE.md` makes relationships the primary structure
  for program designers and requires visible evidence, confidence, and review.
- Existing course objectives and assessment items are untrusted imported data;
  assessment expected answers remain private.

## Scope

- Add write-role-only authoring endpoints that list organization courses and,
  on demand, bounded content-safe objective/assessment choices for one course.
- Add an optimistic course-route endpoint that can add organization courses and
  reorder the current route without silently removing courses or contributions.
- Replace the writer empty state with a real program-creation form while keeping
  the development demo as a secondary action.
- Add one contextual authoring workbench to `/workspace/programs` for course
  order, competency creation, and evidence-backed contribution upsert.
- Refresh the inspectable map after each successful write and preserve the
  existing read-only methodologist experience.

## Non-goals

- Deleting programs, courses, competencies, contributions, or evidence links.
- Creating/importing a course, editing competency text, or bulk authoring.
- Drag-and-drop ordering; accessible move controls are sufficient for this slice.
- Prerequisite graphs, duplication analysis, program audit, aggregate
  administration, AI-generated mappings, or Canvas writes.
- LTI/OAuth setup or deployment to the organization host.

## User flow

1. A program designer opens “Карта программы”. If no program exists, they enter
   code, title, and description and choose “Создать программу”.
2. They choose “Редактировать маршрут”; the current map remains visible below an
   authoring workbench.
3. In “Лента курсов”, they add an existing organization course and move course
   stops earlier or later. Each successful change immediately refreshes the map.
4. In “Новая компетенция”, they enter code, title, and description and save it.
5. In “Связь и доказательство”, they select a competency and course, choose its
   stage and a live course source or explicit author note, explain the mapping,
   and choose “Сохранить связь”.
6. The workbench confirms the change; the refreshed route and evidence panel
   expose exactly what was saved.

## UX contract

Subject: an education architect assembling a route on a drafting table. The
single job is to turn an empty or incomplete map into one reviewable route.

- Continue the existing Ink `#172033`, Slate `#536078`, Canvas `#F6F8FC`, Paper
  `#FFFFFF`, Learning blue `#356AE6`, Evidence teal `#178C7E`, Review amber
  `#C77B16`, and Risk red `#C34E57` system.
- Body copy remains at least 16 px and dense labels at least 14 px.
- Signature: “Лента курсов” — the canonical sequence is shown as numbered course
  stops joined by a line. Move controls change a real program relationship, not
  a decorative list.
- The workbench opens inside the page, not as a generic settings dashboard or a
  stack of floating modals. It is visually distinct but leaves the inspectable
  map in context.
- Desktop: course strip first, then competency and contribution composers side
  by side. Mobile: one vertical workbench; move buttons remain reachable without
  horizontal page scrolling.
- Primary actions are “Создать программу”, “Добавить курс”, “Сохранить порядок”,
  “Добавить компетенцию”, and “Сохранить связь”. “Создать учебный пример” remains
  secondary and development-only.
- Loading preserves the workbench frame. Empty states explain whether no courses,
  no competencies, or no evidence sources are available. Errors preserve entered
  values and tell the user whether to reload after a version conflict.
- Every field has a visible label and helper/error copy. Native controls, visible
  focus, keyboard-operable move buttons, `aria-busy`, `aria-live`, and reduced
  motion are required.
- Course content and evidence excerpts render as plain text only. A source choice
  shows source type and review status; it never implies automatic quality.

## Data and API

- No migration. Reuse `Program`, `ProgramCourse`, `Competency`,
  `CourseContribution`, and `ProgramChangeEvent`.
- `GET /programs/{program_id}/authoring-context` is available only to program
  designers and administrators. It returns at most 500 organization course
  summaries with current positions and an explicit truncation flag.
- `GET /programs/{program_id}/courses/{course_id}/evidence-options` applies the
  same permission and scope boundary and returns at most 100 objectives plus 100
  assessments for the selected course as content-safe options. Expected answers
  and model metadata are absent.
- `PUT /programs/{program_id}/courses` accepts `expected_version` and a unique,
  ordered `course_ids` list. It rejects cross-organization IDs and omission of
  any current program course, locks the program, applies canonical positions,
  increments once when changed, and appends a content-free event.
- Repeating the exact current order is a no-op and does not increment the program
  version.
- Existing create-program, create-competency, contribution-upsert, map-read, and
  demo endpoints remain backward compatible.

## Security and privacy

- Route authorization and service-layer authorization both require a current
  organization write role.
- Program, course, competency, and evidence scope checks remain non-disclosing.
- Authoring context exposes only organization course content needed to choose an
  evidence source; it exposes no students, conversations, submissions, grades,
  expected answers, hidden model prompts, or model metadata.
- Imported text is treated as data and rendered only through React text nodes.
- Route-change events store IDs, counts, and positions only; form text and
  evidence excerpts are excluded.
- Omitting a current course cannot cascade-delete contributions through the UI.

## Acceptance criteria

- [x] Writer roles can create a real program from the empty state; methodologists
  retain a read-only empty state.
- [x] Writer roles can load bounded organization course/evidence choices; other
  roles receive non-disclosing denial and expected answers never serialize.
- [x] Adding/reordering courses preserves every existing course and contribution,
  uses optimistic concurrency, and updates the visible canonical route.
- [x] A writer can add a competency and save a live or manual contribution from
  the workbench without manual API calls.
- [x] Version conflicts and validation failures preserve entered form state and
  do not partially write or silently remove data.
- [x] Loading, no-course, no-competency, no-evidence, success, error, permission,
  desktop/mobile, and keyboard states are covered.
- [x] Existing read-only map, evidence boundary, identity/course authorization,
  and tutor/course workflows regressions pass.
- [x] Focused/full tests, frontend lint/build, pre-commit, browser checks, and
  general/product-UX batch reviews pass.

## Test plan

- Service/API: writer/read role matrix, bounded content-safe context, explicit
  order, add, reorder, no-op, omission denial, cross-organization denial, stale
  version rollback, content-free event, and no expected-answer leakage.
- Frontend: program creation, workbench open/close, course add/reorder,
  competency creation, live/manual contribution, preserved values on error, and
  read-only methodologist behavior.
- Regression: full backend suite, frontend lint/build, and pre-commit.
- Browser: 1440 × 900 and 390 × 844, keyboard move/save flow, busy/success/error
  states, no horizontal overflow, and clean console.

## Batch review

- General and product-UX reviews initially found version-recovery draft loss,
  production demo visibility, absent pre-save evidence state, ambiguous partial
  success, and an ineffective editor-context retry.
- One fix pass added explicit dirty drafts, conflict/partial/general recovery,
  write locking until refresh, scoped retry, evidence preview, and a build-time
  demo capability. It also aligned the program-course limit at 500 and bounded
  course descriptions to 500-character authoring excerpts.
- Targeted general and product-UX rechecks closed every P1 and reported no new
  P0/P1 findings.
- `python -m pytest -q` passed 90 tests; focused program tests passed 6; frontend
  lint/build and repo-wide pre-commit passed. Desktop/mobile, permission,
  conflict preservation, partial-success recovery, context retry, keyboard,
  clean-console, and production demo-hidden browser checks passed.
- Deferred non-blockers: a committed browser E2E suite, direct post-save jump to
  the refreshed evidence, and real PostgreSQL concurrency rehearsal.
