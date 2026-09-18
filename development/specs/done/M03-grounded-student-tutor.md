# M03 — Grounded student tutor

Status: done

## User outcome

A student can ask a question inside an assigned course and receive useful study
help grounded in that course's materials, with visible sources and an honest
refusal when the evidence is weak or the request asks for a ready assessment
answer.

## Users and permissions

- Student: ask questions and see only their own tutor history in an assigned course.
- Instructor and administrator: can exercise the tutor and review course answers.
- Methodologist: can review tutor quality for an assigned course.
- Program designer: no access to individual student questions.

## Scope

- Expose the existing course-grounded Q&A capability to assigned students.
- Persist the authenticated asker without exposing identity in answer payloads.
- Scope student history and feedback to the owner of an answer.
- Distinguish a normal answer, study guidance, and insufficient-context abstention.
- Detect explicit requests for ready quiz, test, homework, or exam answers and
  return learning guidance instead of a final answer.
- Keep assessment documents out of cited evidence for guarded responses.
- Show citations, uncertainty, privacy expectations, and feedback controls.

## Non-goals

- Proctoring, cheating detection, discipline decisions, or student risk scoring.
- Reading submission attempts, grades, deadlines, or live Canvas activity.
- Guaranteeing detection of every assessment-related question.
- Teacher access to a surveillance-style transcript dashboard.
- Automatic changes to Canvas.
- Global rate limiting and production SSO; these require deployment context.

## Student flow

1. Open an assigned course and see what the tutor can and cannot do.
2. Ask a question in their own words.
3. Receive either a cited answer, a learning-oriented hint, or a clear abstention.
4. Open source excerpts beside the answer.
5. Mark the answer helpful or unhelpful.
6. Revisit only their own recent questions.

## Safety contract

- Course text and student questions are untrusted inputs and cannot override policy.
- A supported factual answer has at least one valid course citation.
- An insufficient-context answer has no citations and says that evidence is missing.
- A guarded assessment response does not provide a final answer or cite assessment text.
- The heuristic is described as a safety boundary, not as cheating detection.
- No raw student transcript is exposed to program designers or other students.

## Data and API

- Extend `CourseQuestionAnswer` with asker ownership and response-policy metadata.
- Let `ask_course` and the owner's history routes accept the student role.
- Derive asker/reviewer identity from the authenticated principal.
- Preserve compatibility mode for the existing test and local API surface.

## Acceptance criteria

- [x] Assigned student can ask a grounded course question.
- [x] Answer includes valid course citations or explicitly abstains.
- [x] Ready-answer request receives study guidance, not a final answer.
- [x] Guarded response excludes assessment/quiz documents from citations.
- [x] Student history contains only their own answers.
- [x] Student can review only their own answer; reviewer identity is authenticated.
- [x] Other students and program designers receive non-disclosing denials.
- [x] Student UI explains sources, uncertainty, privacy, and assessment boundaries.
- [x] Tests, build, desktop/mobile, and browser console checks pass.

## Test plan

- Unit tests for assessment intent classification and guarded response construction.
- Authenticated API tests for student ask/history/feedback ownership.
- Cross-student and program-designer authorization tests.
- Existing Q&A tests and full regression suite.
- Frontend lint/build plus normal, guarded, and abstention browser states.

## Verification

- `python -m pytest -q`: 66 passed.
- `npm run lint` and `npm run build`: passed.
- Python formatting and `git diff --check`: passed for the changed code.
- Normal answer, study-guidance, and abstention states checked in the browser at
  1440 × 900 and 390 × 844; console errors and warnings: 0.
- Batch quality, product UX, and RAG evaluation reviews: no P0/P1 findings.
- Remaining P2 work is tracked outside this slice: retrieval benchmarks,
  latency measurement, retention rules, and real Canvas progress semantics.
