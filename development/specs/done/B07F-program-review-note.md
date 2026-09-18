# B07F Program review note

Status: complete

## User outcome

A program designer or organization administrator asks the bounded program
assistant to prepare one evidence-linked note for the first current gap
candidate, edits it, and explicitly records a human decision without changing
the program map or Canvas. A later run reveals the current saved decision for
the same evidence state.

## Users and permissions

- Program designer and administrator: prepare, edit, and save the note.
- Methodologist: keeps the existing read-only evidence routes; note authoring is
  not added implicitly.
- Instructor, student, anonymous, bypass, inactive, wrong-organization,
  wrong-user, stale-program, and wrong-role contexts receive a non-disclosing
  denial.

## Context and evidence

- `development/AI_CANVAS_AGENT_PLAN.md` B07.
- `development/agent/TOOL_CATALOG.md` `draft_program_review_note`.
- `development/specs/done/B07D-program-evidence-routes.md`.
- Existing bounded deterministic program audit and signed `program_ref`.
- Workshop Route rules in `development/design/`.

## Scope

- Bind `program.draft_review_note.v1` to a strict deterministic
  `ProgramReviewDraftService`; no provider call is required.
- Draft only from the first current allowed gap candidate and at most four
  evidence anchors returned by the authoritative B07D route.
- Issue one signed draft reference bound to organization, user, role, program
  version, finding key, and complete evidence-source digest.
- Persist one current versioned human note per program/finding with decision
  `act`, `observe`, or `dismiss` through a separate confirmed application API.
- Recheck role, organization, active program, current finding, exact evidence
  digest, expected note version, and confirmation immediately before save.
- Expose the current saved decision when the same current draft is prepared
  again; record content-free change events.
- Add a Workshop Route review margin beside the existing program evidence tools.

## Non-goals

- No autonomous acceptance, model/provider request, unrestricted instruction,
  new curriculum inference, score, grading, learner data, transcript, or person
  ranking.
- No program-map, audit-source, course, Canvas, or LTI mutation.
- No methodologist write permission, multi-review discussion thread, assignment,
  notification, or real school deployment.

## User flow

1. Program designer or administrator selects a saved program.
2. They choose `Подготовить заметку решения`.
3. The agent rechecks the signed program and current bounded gap evidence and
   returns one editable draft or an honest clear/partial state.
4. The user edits the note, selects one explicit decision, and chooses
   `Сохранить решение`.
5. A confirmation sheet repeats the decision, evidence fingerprint, and the
   boundary that neither the map nor Canvas will change.
6. The confirmed save returns a content-safe receipt and current note version.

## UX contract

- Role: program designer or administrator; single job: record a defensible next
  decision for one current finding.
- Signature element: an evidence sheet with a ruled reviewer margin and a
  removable decision stamp; it continues Workshop Route rather than adding a
  generic chat or modal form.
- The evidence subject, confidence, source state, draft/human status, and exact
  current-note version remain visible while editing.
- Idle, loading, no-candidate, partial, draft, existing-decision, dirty,
  confirmation, saving, success, conflict/stale, permission, retry, program
  switch, long Russian copy, desktop, and mobile states are explicit.
- Focus moves to draft, confirmation, conflict, or receipt. Keyboard controls,
  visible focus, `aria-live`, and reduced motion apply.

## Data and API

- Migration `0049_program_review_notes.sql` creates one current versioned note
  per program/finding plus content-free program change events.
- Extend `AgentRunOut` with closed `program_review_draft` output.
- Execute and project `program.draft_review_note.v1` through the current agent
  state machine and result/source digest boundary.
- PUT `/programs/{program_id}/review-note` accepts signed `draft_ref`, decision,
  bounded edited content, expected note version, and exact confirmation.
- Note save never increments program-map version. Optimistic note version starts
  at 1 and increments only on a materially changed human decision.

## Security and privacy

- Imported rationale and evidence excerpts remain untrusted display data and
  cannot select tools, decisions, targets, or instructions.
- Draft text is deterministic from closed fields and is never treated as a
  decision until the separate human save.
- Signed draft references and current-source recomputation prevent switching
  program, finding, actor, role, or stale evidence.
- Audit events store decision/status/version/digests only, never note content or
  evidence excerpts. Stored content is bounded and organization scoped.
- Unknown input fields, invalid decisions, missing confirmation, stale versions,
  and changed evidence fail closed. Canvas remains read-only.

## Acceptance criteria

- [x] Program designers and administrators can prepare one bounded draft; all
  other roles and contexts fail closed.
- [x] Draft and saved note expose evidence, uncertainty, draft/human status,
  limitations, and no learner/person/provider data.
- [x] Saving requires an exact current signed reference, explicit decision,
  edited content, expected note version, and confirmation.
- [x] Evidence/program changes abstain or conflict without overwriting the note;
  exact replay is stable and conflicting concurrent edits are rejected.
- [x] No program version, map object, Canvas object, model invocation, or
  content-bearing audit event changes.
- [x] Desktop/mobile idle, draft, confirmation, saved, no-candidate, stale,
  error/retry, keyboard/focus, overflow, and console checks pass.
- [x] Batch-quality, product-UX, and agent-safety reviews have no open P0/P1.

## Test plan

- Unit/service: deterministic draft, candidate bounds, signed ref, source
  change, create/update/no-op/conflict, content/event bounds, no map mutation.
- API/agent: two allowed roles; methodologist/instructor/student/cross-org/
  bypass denials; malformed/stale/tampered refs; idempotent run and direct save.
- Browser: prepare, edit, decision, confirm/save, existing decision, no candidate,
  load/save failure, conflict recovery, program switch, focus, desktop/mobile,
  overflow, and clean console.
- Regression: full pytest, frontend lint/build, full Canvas simulator,
  repo-wide pre-commit, and `git diff --check`.

## Batch review

Passed general quality, product UX, and agent-safety targeted rechecks with no
remaining P0/P1 findings. Final evidence: 464 backend tests, frontend lint and
production build, 112/112 Canvas simulator scenarios, repo-wide pre-commit,
`git diff --check`, and desktop/mobile review-note screenshots. The work remains
offline: no real Canvas, model host, program map, or Canvas object was mutated.
