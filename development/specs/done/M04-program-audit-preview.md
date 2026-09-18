# M04 — Evidence-backed program audit preview

Status: complete

## User outcome

A methodologist or program designer can check one current program route, see a
bounded list of factual coverage/evidence gaps and one cautious sequence signal,
and inspect the declared course evidence behind every observation.

## Users and permissions

- Methodologist: run and inspect the read-only audit preview for an organization
  program.
- Program designer and administrator: the same preview access while authoring
  the route.
- Instructor and student: no cross-course program or audit access.
- This slice records no review decision and changes no program, course, Canvas,
  student, or teacher data.

## Context and evidence

- `development/STATUS.md` names an evidence-backed program audit as the next M04
  batch.
- `development/ROADMAP.md` requires program-level audit, prerequisite and
  duplication visibility, and evidence drill-down.
- `development/PRODUCT.md` requires inspectable evidence and forbids opaque
  scores or personnel judgements.
- `development/ARCHITECTURE.md` keeps program intelligence in the application
  service and now distinguishes the current computed preview from a future
  persisted `ProgramAudit` entity.
- `development/design/EXPERIENCE.md` makes curriculum relationships primary and
  requires confidence as actionable language.
- The completed program-map and visual-authoring specs define canonical course
  order, contribution stages, evidence safety, and the current page shell.

## Scope

- Add a read-role program audit-preview endpoint derived only from the current
  canonical program map.
- Return four deterministic observation kinds:
  `coverage_gap`, `assessment_gap`, `evidence_gap`, and `sequence_check`.
- Define `sequence_check` narrowly: an assessed contribution appears earlier in
  canonical course order than the first introduced/developed contribution for
  the same competency. It is a review prompt, not a declared prerequisite error.
- Bound analyzed competencies, contributions, findings, and evidence excerpts;
  expose explicit truncation.
- Add an in-page audit panel to `/workspace/programs` with a finding rail and one
  evidence sheet. Reuse the existing map below it as context.
- Load the preview only when a permitted user chooses “Проверить маршрут”.

## Non-goals

- Persisted `ProgramAudit`, review decisions, assignments, comments, exports, or
  notifications.
- A program/teacher score, ranking, pass/fail badge, or claim that silence proves
  quality.
- Inferred prerequisite relations, semantic duplication, cognitive progression,
  or model-generated findings.
- Student progress, grades, submissions, conversations, or learner-level Canvas
  prerequisite state.
- Editing the route from the audit panel, Canvas writes, LTI/OAuth, or deployment.

## User flow

1. A permitted user selects a program on “Карта программы”.
2. They choose “Проверить маршрут”; the existing page remains visible while the
   preview loads.
3. The panel opens with counts by observation kind and an explicit statement
   that it is a structural check, not a quality score.
4. The user selects an observation from the inspection rail.
5. The evidence sheet shows competency, affected course stops, declared stages,
   rationale, source state, confidence language, and review state.
6. With no observations, the panel says that no formal break was found in the
   analyzed portion and names what the preview does not prove.

## UX contract

Subject: a methodologist inspecting a curriculum route on a light table. The
single job is to locate one structural break and understand exactly why it was
raised.

- Reuse Ink `#172033`, Slate `#536078`, Canvas `#F6F8FC`, Paper `#FFFFFF`,
  Learning blue `#356AE6`, Evidence teal `#178C7E`, Review amber `#C77B16`, and
  Risk red `#C34E57`.
- Signature: “Контрольная рейка” — observations appear as compact inspection
  tags aligned to the program route, with kind and review state encoded by text
  and shape as well as color.
- Spend the saturated risk color only on a factual broken/missing link. Sequence
  checks stay amber because the declared mapping may be incomplete or intentional.
- Desktop: inspection rail at left and evidence sheet at right. Mobile: tags and
  sheet stack vertically without horizontal scrolling.
- Primary action: “Проверить маршрут”. Refresh action: “Проверить заново”.
  Finding action: “Открыть основание”. Error retry: “Повторить проверку”.
- Loading preserves the panel frame. Empty, error, permission, truncated,
  missing-evidence, low-confidence, and no-finding states explain the next valid
  interpretation or action.
- Finding controls are keyboard buttons with `aria-pressed`; selection moves
  focus to the evidence heading. Status uses `aria-live`, loading uses
  `aria-busy`, focus is visible, and reduced motion is respected.
- Imported rationale and excerpts render only as plain text. Each observation
  exposes evidence, rule-confidence language, and finding review status.

## Data and API

- No migration. Reuse `Program`, `ProgramCourse`, `Competency`,
  `CourseContribution`, `LearningObjective`, and `AssessmentItem`.
- `GET /programs/{program_id}/audit-preview` is available to methodologists,
  program designers, and administrators and repeats role/scope checks in the
  service layer.
- Analyze at most 500 competencies and 5,000 contributions. Return at most 500
  findings and at most 8 evidence items per finding, with explicit
  `analysis_truncated` and `findings_truncated` flags.
- Every finding returns a stable key, kind, attention level, competency identity,
  title/detail, rule-confidence label, `review_status=not_reviewed`, and bounded
  content-safe evidence items.
- Response counts describe returned structural observations only. There is no
  aggregate quality score.
- Existing program map/authoring, course, tutor, audit, and Canvas APIs remain
  backward compatible.

## Security and privacy

- Route and service authorization both require a current organization read role;
  other roles and cross-organization programs receive non-disclosing denial.
- The preview exposes no students, memberships, submissions, grades,
  conversations, expected answers, provider metadata, prompts, or credentials.
- Course content, rationale, and evidence are untrusted data and are never used
  as instructions or rendered as HTML.
- Evidence resolution verifies the evidence still belongs to the declared course.
- The read-only preview writes no event and retains no generated content.
- Labels explicitly prevent use as an automatic teacher/program quality verdict.

## Acceptance criteria

- [x] Read roles receive a bounded deterministic preview; instructor/student and
  cross-organization access are non-disclosing.
- [x] Coverage, assessment, missing-evidence, and sequence observations are
  derived from canonical order and explicit contributions with stable keys.
- [x] Every observation exposes evidence, confidence language, and review state;
  expected answers and sensitive/model metadata never serialize.
- [x] The UI opens from the current program page, supports selection and refresh,
  and never presents counts as a quality score.
- [x] Loading, no-finding, populated, truncated, error, permission,
  missing-evidence, low-confidence, desktop/mobile, and keyboard states pass.
- [x] Existing map/authoring, identity/course authorization, tutor, and course
  workflows regressions pass.
- [x] Focused/full tests, frontend lint/build, pre-commit, browser checks, and
  general/product-UX batch reviews pass.

## Test plan

- Service/API: role matrix, cross-organization denial, each finding kind,
  canonical sequence, stable order/keys, bounds/truncation, missing evidence,
  content-safe excerpts, and no expected-answer leakage.
- Frontend/browser: initial action, loading frame, populated selection, refresh,
  no findings, error retry, truncated copy, keyboard/focus, 1440 × 900,
  390 × 844, no horizontal overflow, and clean console.
- Regression: full backend suite, frontend lint/build, and repo-wide pre-commit.

## Batch review

- General review found one P1 race: invalidating an in-flight audit while
  switching or reloading a program could leave `auditLoading` stuck. The
  invalidation paths now clear loading, and a delayed-request browser recheck
  returned the new program with `busy=0` and the audit launcher available.
- Course-window truncation now counts all declared contributions before deciding
  whether absence-based findings are safe. A targeted regression confirms that
  an omitted learning contribution cannot produce a false sequence finding.
- Product/UX review passed after narrowing the launcher copy to the actual
  sequence rule, making the review status methodologist-facing, and visually
  distinguishing missing evidence from confirmed evidence.
- Final general and product/UX targeted rechecks reported no remaining P0/P1.
- Verified with 91 backend tests, frontend lint/build, repo-wide pre-commit, and
  real-browser desktop/mobile, loading, empty, populated, truncated, error/retry,
  permission, low-confidence, keyboard/focus, clean-console, and race checks.
