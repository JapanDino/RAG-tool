# M04 — Inspectable program competency map

Status: done

## User outcome

A methodologist or program designer can open one curriculum map, see where each
competency is introduced, developed, and assessed across courses, and inspect the
course evidence behind every declared contribution.

## Users and permissions

- Program designer: list organization programs, create a program, add
  competencies, record course contributions, and inspect evidence.
- Methodologist: read the program map and inspect evidence; authoring is deferred.
- Administrator: the same program authoring access as a program designer for
  operational setup, without student-level data.
- Instructor and student: no cross-course program-map access in this slice.
- Development-only demo seed: program designer or administrator only and disabled
  in production.

## Context and evidence

- `development/ROADMAP.md` defines program entities, competencies, course
  contribution mapping, evidence drill-down, and aggregate views as M04 gates.
- `development/PRODUCT.md` requires inspectable evidence instead of opaque scores
  and forbids a single ranking of teachers or students.
- `development/ARCHITECTURE.md` identifies program intelligence as an application
  service and keeps the current Next.js Pages Router.
- `development/design/EXPERIENCE.md` makes relationships the primary structure for
  methodologists and program designers.
- Existing `LearningObjective` and `AssessmentItem` rows provide live course
  evidence; their content remains untrusted data.

## Scope

- Add organization-scoped `Program`, explicitly ordered `ProgramCourse`,
  `Competency`, `CourseContribution`, and content-safe change-event entities in
  one migration.
- Add optimistic program-map versioning and service-level organization/evidence
  validation.
- Add list, create, competency-create, contribution-upsert, map-read, and
  development demo endpoints.
- Add `/workspace/programs` as a curriculum workspace linked from the role-aware
  home for program designers, methodologists, and administrators.
- Show a responsive competency-by-course route and an evidence detail panel.
- Derive factual coverage states only: no course, learning without assessment,
  or assessed. Do not present these states as an automatic quality verdict.

## Non-goals

- Full visual authoring, course reordering, deletion, bulk import, prerequisite
  relations, or change impact simulation.
- Automated program audit, duplication finding, Bloom progression judgement, or
  a single program/teacher score.
- Reading submissions, student conversations, grades, or learner-level progress.
- Canvas/LTI synchronization or deployment to the organization host.
- Generating competency mappings with a model.

## User flow

1. A permitted organization role opens “Карта программы” from `/workspace`.
2. The curriculum workspace selects the first available program or explains that
   no program has been configured.
3. The user selects a competency row and sees its route across program courses.
4. Selecting a mapped course opens level, rationale, source kind, review state,
   and a plain-text evidence excerpt.
5. Missing or deleted evidence remains visible as “Источник требует повторной
   привязки”; the contribution is not silently treated as supported.

## UX contract

Subject: an architect of a school program tracing a learning trajectory. The
screen's single job is to make cross-course competency coverage inspectable.

- Reuse Ink `#172033`, Slate `#536078`, Canvas `#F6F8FC`, Paper `#FFFFFF`,
  Learning blue `#356AE6`, Evidence teal `#178C7E`, Review amber `#C77B16`, and
  Risk red `#C34E57`.
- Reuse the Cyrillic-capable display/body/utility system fallbacks already in the
  product; body copy stays at least 16 px and dense map labels at least 14 px.
- Layout: quiet program header, program selector, competency route workspace, and
  one evidence panel. Avoid KPI-card rows and decorative charts.
- Signature: “Маршрут программы” — a competency row travels through ordered
  course stops; stage is always encoded by word and shape as well as color.
- Desktop: competency list and course route occupy the main plane; evidence stays
  in a stable right panel. Mobile: each competency becomes a vertical sequence,
  and evidence follows the selected route without horizontal page scrolling.
- Primary mapped-cell action: “Открыть доказательство”. Empty development action:
  “Создать учебный пример”. Retry: “Повторить загрузку”.
- Loading preserves the page frame. Empty distinguishes no programs from a
  program with no competencies. Error states say the map was preserved and offer
  retry. Permission denial is non-disclosing and links back to the workspace.
- Missing evidence and learning-without-assessment are explicit low-evidence
  states, not silent empty cells.
- Route cells are keyboard buttons with visible focus; selection uses
  `aria-pressed`; evidence focus moves to its heading after selection. Reduced
  motion is respected.

## Data and API

- Migration `0031_program_competency_map.sql` adds the five entities, foreign
  keys, uniqueness, allowed-stage/source checks, and indexes.
- A program begins at version 1. Competency and contribution writes require
  `expected_version`, lock the program row, increment once, and append a
  content-safe event.
- `GET/POST /organizations/{organization_id}/programs` lists or creates programs.
- `GET /programs/{program_id}/map` returns ordered courses, competencies,
  contribution stages, factual coverage state, and resolved evidence.
- `POST /programs/{program_id}/competencies` adds one competency.
- `PUT /programs/{program_id}/contributions` creates or replaces one
  competency-course contribution. Its required `course_position` establishes
  the course's canonical position on first use; later mismatches or occupied
  positions return a conflict instead of silently changing the route.
- `POST /organizations/{organization_id}/programs/demo` creates an idempotent
  development-only two-course example.
- Evidence types are `learning_objective`, `assessment_item`, or `manual_note`.
  Live evidence IDs must belong to the declared course; manual notes have no ID.
- Existing course, tutor, audit, and Canvas APIs remain backward compatible.

## Security and privacy

- Organization authorization and all program/course/evidence scope checks are
  enforced in routes and repeated inside the service layer.
- Cross-organization program, competency, course, and evidence combinations
  receive non-disclosing denials.
- Objective and assessment excerpts are returned only after a contribution has
  been explicitly mapped by a permitted author and never include expected
  answers.
- Imported evidence and rationale are rendered as plain text, never HTML or
  prompt instructions.
- Change events store entity/version/count metadata, not full evidence excerpts.
- Program views expose no student identity, conversation, submission, grade, or
  personnel ranking.

## Acceptance criteria

- [x] Program, ordered program-course, competency, contribution, and change-event
  schema validates organization scope, uniqueness, stages, and evidence types.
- [x] Program designer/admin can author with optimistic concurrency;
  methodologist can read; instructor/student receive non-disclosing denial.
- [x] Cross-organization course, competency, or evidence references are rejected
  at the service boundary without partial writes.
- [x] Map returns ordered courses and competencies with factual `unmapped`,
  `learning_only`, and `assessed` states.
- [x] Every mapped cell exposes rationale and live/manual/missing evidence state;
  assessment expected answers are never serialized.
- [x] Development demo creation is idempotent and unavailable in production.
- [x] Workspace entry and curriculum page cover loading, no-program, no-
  competency, populated, missing-evidence, error, permission, desktop/mobile,
  and keyboard states.
- [x] Existing identity/course authorization and course workflows regressions
  pass.
- [x] Focused/full tests, frontend lint/build, targeted pre-commit, browser checks,
  and batch/UX reviews pass.

## Test plan

- Service/API: role matrix, version conflicts, idempotent demo, ordered map,
  cross-organization denial, evidence ownership, missing evidence, and no expected
  answer leakage.
- Regression: identity context, course access, teacher workspace, student tutor,
  and M03 lifecycle tests.
- Browser: 1440 × 900 and 390 × 844; populated, evidence selection, empty/error,
  keyboard focus, and console inspection.

## Batch review

Completed on 2026-07-14.

- The initial general review found two P1 issues: course order was inferred from
  `Course.id`, and whitespace-only authoring fields could be stored empty.
  `ProgramCourse` now persists canonical order, contribution writes reject
  position conflicts atomically, and input strings are stripped before length
  validation. Focused API tests cover both fixes.
- The initial product/UX review found two P1 issues: a slow program switch could
  pair the new selector value with the old map, and critical route/evidence text
  was below the 14/16 px design contract. Switching now masks stale content with
  an explicit busy state, and critical labels/body copy meet the contract.
- One targeted general recheck and one targeted product/UX recheck both passed
  with no remaining or newly introduced P0/P1 findings.
- Verification: 4 focused and 88 full backend tests passed; frontend lint and
  production build passed; repo-wide pre-commit passed. Browser checks covered
  desktop, mobile, a delayed program switch, keyboard/evidence focus, error,
  permission, empty, missing-evidence, and console states. Mobile page width was
  382/382 with no horizontal overflow.
- Deferred P2 work: show missing-evidence markers directly on route cells; make
  secondary navigation identical for all permitted roles; exercise optimistic
  locks and migration `0031` against real PostgreSQL; distinguish demo provenance
  from a user-owned program code; add visual course reordering and authoring.
