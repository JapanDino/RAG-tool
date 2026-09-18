# M03 — Teacher-facing tutor quality

Status: done

## User outcome

An instructor can tell whether the course tutor is helping students, refusing
honestly, and staying inside the assessment policy without reading a surveillance
feed of individual student conversations.

## Product decision

The teacher workspace receives a compact service-quality panel for the last 30
days. It describes the tutor, not the students. The panel must not expose names,
user identifiers, raw questions, answer text, citations, feedback comments,
student rankings, or risk labels.

## Scope

- Count tutor interactions from active student course memberships only.
- Separate supported answers, study guidance, and honest abstentions.
- Count normal answers that need quality review because they have weak confidence
  or no valid citation.
- Show how many answers received student feedback.
- Show helpfulness only after at least three ratings; before that, explain that
  the sample is too small.
- Embed the panel in the existing teacher course workspace.
- Preserve the current non-disclosing course authorization boundary.

## Non-goals

- A list or search view of student questions.
- Identifying, ranking, or scoring students.
- Inferring confusion, cheating, engagement, attainment, or wellbeing.
- Automated teacher alerts or Canvas changes.
- Topic clustering or semantic analysis of question text.
- Historical cohort comparison before retention rules are agreed.

## Metric contract

- `questions_total`: student-owned tutor interactions in the last 30 days.
- `answer_responses`: all normal explanatory answers; together with guidance and
  abstentions this forms the response-mode distribution.
- `supported_answers`: normal answers with a citation whose document and chunk
  still belong to the course and whose quote matches that chunk; this is a
  subset of `answer_responses`.
- `guidance_answers`: assessment-safe study guidance.
- `abstained_answers`: honest insufficient-context responses.
- `answers_needing_review`: normal answers with confidence below 0.5 or no
  citation. This is a service-quality queue count, not a student-risk count.
- `rated_answers`: the latest helpful or unhelpful event submitted by the
  student who owns each answer. Later staff quality reviews neither count as nor
  erase student feedback.
- `helpful_rate` and `helpful_answers`: returned only when
  `rated_answers >= 3`; the numerator is also suppressed below the threshold.
- Counts are mutually understandable, but `answers_needing_review` is a subset
  of normal answers and therefore is not part of the response-mode distribution.

## Primary signal

The API returns one deterministic `signal` so every client uses the same
transparent priority:

- `empty`: no student interactions;
- `early`: fewer than five interactions, before any quality conclusion;
- `coverage`: at least 35% abstentions and this rate is not smaller than the
  weak-normal-answer rate;
- `review`: at least one normal answer needs review after the coverage check;
- `limited`: five or more interactions but fewer than three normal answers;
- `steady`: enough normal answers and no current review/coverage signal.

## UX contract

- Lead with one plain-language verdict derived from transparent thresholds.
- Use a three-part horizontal response mix for answer, guidance, and abstention.
- Keep exact counts next to percentages and never imply learning outcomes.
- Explain the 30-day window, the minimum feedback sample, and the privacy boundary.
- Empty state says to wait for real student questions; it does not manufacture a
  score from staff testing.
- Mobile order: verdict, response mix, action signal, feedback, privacy note.

## Acceptance criteria

- [x] Instructor, methodologist, and administrator can see aggregate tutor quality.
- [x] Student and program designer receive a non-disclosing denial.
- [x] Staff tutor tests and inactive/former students are excluded.
- [x] Response-mode and review-needed counts follow the metric contract.
- [x] Helpfulness is suppressed below three ratings.
- [x] API payload contains no question, answer, identity, citation, or comment data.
- [x] Teacher UI has useful populated and empty states on desktop and mobile.
- [x] Tests, lint, build, browser console, and batch reviews pass.

## Test plan

- Service/API tests with student, instructor, inactive member, and second course.
- Boundary assertions against forbidden transcript and identity fields.
- Minimum-sample tests for helpfulness.
- Existing authorization and full regression suite.
- Frontend lint/build and browser checks at 1440 × 900 and 390 × 844.

## Verification

- `python -m pytest -q`: 72 passed.
- Python formatting, import order, frontend lint/build, and `git diff --check`:
  passed for the changed code.
- Populated desktop, populated mobile, and empty states checked in production
  browser build; console errors and warnings: 0.
- Batch quality, product UX, and RAG/metrics repeat reviews: pass, no P0/P1.
- Residual P2 work: semantic entailment benchmark, threshold calibration,
  historical actor backfill policy, small-class aggregation policy, and SQL-side
  aggregation at school scale.
