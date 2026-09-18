# B06 Closed student-to-teacher improvement loop

Status: complete

## User outcome

An instructor opens the assistant from the exact Canvas course and sees at most
three privacy-thresholded course-improvement candidates derived from repeated
unsupported or student-marked-unhelpful help sessions. The instructor can
inspect current course evidence, request an editable cited intervention draft,
and explicitly accept or reject it without seeing student questions, identities,
or transcripts and without changing Canvas.

## Users and permissions

- Instructor: inspect aggregate candidates and review intervention drafts only
  in the exact launched course and current product session.
- Student: contributes only through existing tutor interactions and owner
  feedback; cannot inspect aggregates or instructor artifacts.
- Other roles, anonymous, expired/revoked, wrong-course, cross-organization,
  inactive membership, and compatibility bypass contexts receive non-disclosing
  denial.

## Context and evidence

- `development/AI_CANVAS_AGENT_PLAN.md` B06.
- `development/agent/API_CONTRACT.md` and `TOOL_CATALOG.md`.
- `development/specs/done/B04-learner-agent-canvas-course.md`.
- `development/specs/done/B05-instructor-agent-reviewable-course-actions.md`.
- Existing `CourseQuestionAnswer`, owner feedback events, teacher workspace,
  current course retrieval, and instructor-agent boundaries.
- Workshop Route in `development/design/DESIGN_SYSTEM.md`.

## Scope

- Implement `LearningGapAggregationService` for a fixed 30-day window, active
  student memberships, and a minimum of three distinct students per candidate.
- Anchor candidates to current ready course evidence using current validated
  citations or deterministic local lexical matching; unanchored topics remain
  hidden.
- Expose bands rather than exact learner/event counts and never return raw
  questions, answers, answer IDs, user IDs, feedback comments, or transcripts.
- Activate `instructor.inspect_question_gaps.v1` and allow a selected opaque
  aggregate reference to produce a separate intervention draft.
- Persist intervention drafts and human review metrics: version, decision,
  edit-distance ratio, decision latency, and source audit snapshot.
- Add the instructor flow to the signed Canvas workspace.

## Non-goals

- Student ranking, teacher scoring, individual alerts, sentiment analysis,
  transcript search, diagnosis of learner ability, or administrative oversight.
- Automatic Canvas writes, publishing, grading, notifications, or curriculum
  changes.
- Semantic clustering through an external provider, enabled generative-model
  validation, real Canvas, deployment, or production-host evidence.

## User flow

1. Instructor opens the exact signed course workspace.
2. The assistant checks whether repeated help gaps cross the privacy threshold.
3. The instructor sees a bounded candidate labeled by current course evidence,
   a cohort/event band, signal type, confidence language, and limitations.
4. The instructor requests an editable cited intervention draft.
5. Accept/reject is a separate CSRF-protected, optimistic-versioned action;
   Canvas remains unchanged.

## UX contract

- Single job: turn one collective signal into one reviewable course intervention.
- Continue Workshop Route colors, IBM Plex typography, grid paper, and the calm
  review-sheet hierarchy from B05.
- Signature element: a `privacy threshold tape` where three anonymous marks
  merge into one course-level card only after the threshold is met. It encodes
  cohort protection and is never decorative.
- Use plain Russian: `Повторяющаяся трудность`, `Опора в курсе`,
  `Подготовить материал`, `Принять после проверки`, `Отклонить`.
- Never display “student 1”, exact learner counts, raw questions, model/RAG/tool
  terms, rankings, or claims about teacher/course quality.
- Desktop and mobile expose loading, below-threshold empty, candidate, stale,
  insufficient-evidence, failure/retry, draft, accepted, and rejected states;
  transitions move keyboard focus and respect reduced motion.

### Design plan

- Palette: Canvas navy `#213B78`, workshop blue `#285FC7`, pencil red
  `#B94952`, evidence teal `#178777`, paper `#FFFDFC`, graphite `#253149`.
- Type: existing IBM Plex Sans for reading, IBM Plex Mono for bands and privacy
  labels, current display treatment for the candidate headline.
- Layout: one privacy tape above one evidence-anchored candidate; no KPI grid.
- The deliberate visual risk is showing the hidden individual marks as anonymous
  short strokes that physically merge into a single labelled course signal.
  This makes aggregation understandable without implying surveillance.

## Data and API

- Add a persisted intervention-draft table with course, source audit/document/
  chunk, aggregate digest, bounded bands, generated and reviewed content state,
  optimistic version, edit-distance ratio, and decision latency.
- Generic agent runs store only opaque aggregate/draft references.
- Add strict `agent.v1` aggregate and intervention DTOs plus a dedicated direct
  review endpoint; do not widen arbitrary input fields.
- Preserve B03 workflow and tool names.

## Security and privacy

- Require at least three distinct active students and three qualifying events;
  one learner cannot surface a candidate alone through repeated questions.
- Count only abstained/insufficient-context tutor responses or the latest
  owner-authored `unhelpful` feedback event.
- Use a fixed window and bounded results. Output only coarse bands (`3–5`,
  `6–10`, `11+`).
- Treat questions and course content as untrusted. Raw student content may be
  processed locally for grouping but is never copied into aggregate storage,
  agent runs, events, DTOs, prompts, or instructor UI.
- Revalidate current course ownership, membership, cohort threshold, source
  evidence, audit, aggregate digest, draft state, and version at every step.
- The model cannot review its own draft or apply a Canvas change.

## Acceptance criteria

- [x] Three distinct active students with one repeated anchored gap produce one
  bounded course-improvement candidate; one or two students produce none.
- [x] Repeated events from one student do not satisfy the cohort threshold.
- [x] Instructor output contains no raw question, answer, identity, exact count,
  feedback comment, or model metadata.
- [x] A signed instructor completes aggregate inspection -> cited intervention
  draft -> explicit version-aware review in the exact course.
- [x] Stale course evidence, threshold loss, wrong course/session/role, and
  concurrent review fail closed without revealing artifacts.
- [x] Review records edit-distance ratio and decision latency; Canvas remains
  unchanged.
- [x] Desktop/mobile, focus, loading, below-threshold, failure, stale, draft,
  accepted, and rejected states pass.
- [x] Full regressions and agent-safety, product-UX, RAG/safety, and batch-quality
  reviews have no open P0/P1 findings.

## Test plan

- Unit: qualifying-event rules, latest owner feedback, deterministic grouping,
  cohort threshold, bands, bounded output, edit distance, and deadlines.
- Service/API: exact role/course/session, one-student flood, inactive membership,
  stale evidence, aggregate digest, optimistic review, concurrent review, and
  content-free tool events.
- RAG/privacy: RU/EN anchored and unanchored topics, instruction-shaped questions,
  current citation validation, no transcript/answer/identity leakage.
- Browser: signed instructor aggregate -> draft -> review on desktop/mobile plus
  loading, below-threshold, failure, stale, focus, overflow, and clean console.
- Regression: full pytest, instructor safety protocol, frontend lint/build,
  repo-wide pre-commit, and `git diff --check`.

## Batch review

Complete on 2026-08-03. The first review found one count-leakage P0 and four
backend/UX P1 findings. The implementation now uses count-independent public
confidence, chunk-level grouping, an exact rolling 30-day window, exact
aggregate-digest freshness, bounded aggregation deadlines, visible recovery,
unsaved-draft locking, and announced focus transitions. Targeted batch-quality,
product-UX, and RAG/privacy rechecks reported no remaining P0/P1 findings.

Final evidence: 398 backend tests, frontend lint and production build,
repo-wide pre-commit, `git diff --check`, and all 26 desktop/mobile Canvas
simulator tests passed. No real Canvas, deployment, model host, or Canvas write
was used.
