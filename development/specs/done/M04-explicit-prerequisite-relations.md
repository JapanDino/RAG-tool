# M04 — Explicit prerequisite relations

Status: complete

## User outcome

A program designer can explicitly declare that one program competency should
precede another, while a methodologist can inspect the declared rationale and
the saved course evidence that supports or contradicts the current order.

## Users and permissions

- Program designer and administrator: create, update, and remove explicit
  prerequisite relations inside one organization program.
- Methodologist: inspect relations, rationale, evidence, and structural status
  without write controls.
- Instructor and student: no program prerequisite access.

## Context and evidence

- `development/STATUS.md` names explicit prerequisite relations as the next M04
  batch.
- `development/ROADMAP.md` requires prerequisite visibility across courses.
- `development/ARCHITECTURE.md` lists `PrerequisiteRelation` as planned and
  forbids invented prerequisite relations in the computed audit.
- Existing program foundations provide canonical course order, explicit
  competency contributions, evidence resolution, optimistic program versions,
  content-safe events, and protected authoring roles.
- `development/design/EXPERIENCE.md` requires curriculum relationships to be the
  primary structure and every aggregate signal to open inspectable evidence.

## Scope

- Persist directed prerequisite competency → target competency relations within
  one active program.
- Require a bounded author rationale and reject self-links, duplicates across
  programs, inactive scope, and graph cycles.
- Use optimistic program versioning for create/update/delete and write
  content-safe change events containing IDs but not rationale text.
- Add relations to the existing program-map response in deterministic order.
- Derive one cautious structural state from current canonical contributions:
  `needs_evidence`, `order_check`, or `declared_order`.
- Show a dedicated “Линии предпосылок” panel on the program page. Readers see
  relation/evidence cards; writers also see a compact composer and remove action.

## Non-goals

- Model-inferred prerequisites, semantic similarity, embeddings, prompts, or
  retrieval.
- Learner completion, Canvas module requirements, grades, submissions, mastery,
  adaptive release, or progress gating.
- A pass/fail program score, automatic curriculum change, teacher judgement, or
  claim that canonical order proves learning readiness.
- Cross-program prerequisites, bulk import/export, notifications, review
  decisions, Canvas writes, LTI/OAuth, or deployment.

## User flow

1. A writer opens a program and chooses prerequisite and target competencies.
2. They enter why the dependency is intended and choose “Сохранить линию”.
3. The service rejects self-links and cycles before writing; successful writes
   refresh the same program map.
4. A reader sees prerequisite → target, rationale, the earliest saved assessment
   of the prerequisite, and the earliest saved start of the target.
5. The panel explains whether evidence is missing, order needs review, or the
   declared prerequisite assessment currently precedes the target start.
6. A writer can remove a relation after explicit confirmation.

## UX contract

- Subject: a curriculum architect drawing dependency lines between competency
  cards on a light table. The single job is to inspect one declared dependency.
- Reuse the current Ink/Slate/Canvas/Paper/Learning blue/Evidence teal/Review
  amber/Risk red palette and IBM Plex typography.
- Signature: one directional “prerequisite line” with a square source node, an
  arrow, and a round target node. Shape and text carry meaning without color.
- `needs_evidence` is neutral dashed, `order_check` is amber, and
  `declared_order` is teal but explicitly says “structure matches”, not “ready”.
- Primary action: “Сохранить линию”. Remove action: “Удалить линию”. Retry keeps
  the entered rationale and selected competencies where safe.
- Empty, busy, success, conflict/cycle, partial-refresh, read-only, and bounded
  states explain the next valid action.
- Desktop cards align relation, state, and two evidence stops; mobile stacks
  without horizontal scrolling. Controls use labels, visible focus, `aria-live`,
  `aria-busy`, and plain-text rendering of all untrusted content.

## Data and API

- Add migration `0032_program_prerequisite_relations.sql` and model
  `ProgramPrerequisiteRelation`.
- Columns: program, prerequisite competency, target competency, rationale,
  created/updated actor, and timestamps. Unique directed pair and self-link check
  are database constraints; same-program ownership and cycle prevention remain
  service invariants.
- Add `PrerequisiteRelationUpsertIn`, `PrerequisiteRelationDeleteIn`, relation
  evidence/status outputs, and `prerequisites` to `ProgramMapOut`.
- `PUT /programs/{program_id}/prerequisites` creates or updates one directed
  pair. Exact no-op preserves version.
- `DELETE /programs/{program_id}/prerequisites/{relation_id}` removes one relation.
- At most 500 relations are serialized; `prerequisites_truncated` is explicit.
- Structural state uses the earliest canonical `assessed` contribution of the
  prerequisite and earliest canonical contribution of the target. Missing either
  yields `needs_evidence`; prerequisite position greater than or equal to target
  yields `order_check`; strictly earlier yields `declared_order`.
- Evidence exposes current source state and bounded excerpt but never expected
  answers or provider/model metadata.

## Security and privacy

- Route and service layers independently repeat organization role and active
  program scope checks.
- Both competencies and every resolved course/evidence item are revalidated
  against the same program and organization.
- Rationale and imported evidence are untrusted plain text, never prompts or HTML.
- Events contain relation/competency IDs and action type only; rationale is not
  logged. No student, teacher, membership, conversation, grade, submission,
  expected-answer, token, prompt, or model data is exposed.
- Reads do not write events. Failed validation rolls back without version change.

## Acceptance criteria

- [x] Writers can create/update/delete an explicit same-program relation with
  optimistic versioning; readers see it and other roles receive non-disclosing
  denial.
- [x] Self-links, cross-program competencies, stale versions, and direct or
  transitive cycles are rejected without a write or leaked resource detail.
- [x] Exact no-op preserves version; successful writes emit content-safe events.
- [x] Map output is bounded/deterministic and exposes exact rationale, evidence,
  confidence boundary, and one of the three structural states.
- [x] Canonical-order changes recompute state without mutating the relation.
- [x] UI supports writer/read-only, empty, busy, success, conflict/cycle,
  partial-refresh, evidence-missing, order-check, declared-order, desktop/mobile,
  keyboard, overflow, and clean-console states.
- [x] Full regressions, frontend lint/build, repo-wide pre-commit, and general/
  product-UX/RAG reviews pass without remaining P0/P1.

## Test plan

- Model/migration: constraints, indexes, cascade behavior, and migration ordering.
- Service/API: role matrix, cross-org, self, direct/transitive cycle, no-op,
  stale version, create/update/delete events, deterministic order, 500 bound,
  missing evidence, equal/later/earlier course position, reorder recomputation,
  missing source safety, and expected-answer exclusion.
- Browser: create, retained form on cycle error, read-only methodologist, remove
  confirmation, three structural states, responsive screenshots, keyboard focus,
  no overflow, and console.
- Regression: focused/full pytest, frontend lint/build, repo-wide pre-commit,
  and `git diff --check`.

## Batch review

- Full gate: 93 backend tests, frontend lint/build, repo-wide pre-commit, and
  `git diff --check` passed.
- Browser: writer create/update/delete, cycle draft retention, mocked
  partial-refresh recovery, methodologist read-only mode, three structural
  states, keyboard navigation, 1440 × 900 and 390 × 844 screenshots, exact
  mobile width, and clean final console passed.
- Initial general, product-UX, and RAG reviews found four UI P1 findings:
  over-strong `declared_order` language, risk styling for missing evidence,
  contradictory partial-refresh feedback, and no visible update mode.
- One grouped fix pass made structural language cautious, missing evidence
  neutral, partial writes truthful and locked until reload, and existing pairs
  explicitly editable. It also exposed source review status and `aria-busy`.
- Targeted general, product-UX, and RAG rechecks reported no remaining P0/P1.
- Residual P2: real PostgreSQL migration/concurrency rehearsal, committed browser
  E2E coverage, and human-labeled usefulness measurement remain future work.
