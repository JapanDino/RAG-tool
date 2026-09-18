# M03 — Teacher-configurable tutor policy

Status: done

## User outcome

An instructor can pause the course tutor or choose how it helps students without
writing a system prompt and without weakening content visibility, assessment, or
grounding protections.

## Product decision

Configuration is deliberately structured. The first slice exposes only:

- tutor enabled / paused;
- answer style: `balanced`, `guided`, or `concise`.

The following rules are immutable and always shown next to the controls:

- only ready, student-visible course content can be retrieved;
- assessment requests receive guidance, not a ready answer;
- insufficient evidence produces an abstention;
- supported factual answers retain visible citations.

## Style contract

- `balanced`: a short sourced explanation with enough context to understand it.
- `guided`: sourced stepping stones and a check question that make the student
  do part of the reasoning.
- `concise`: the smallest useful sourced explanation, without extra expansion.

The style may shape presentation but cannot alter retrieval eligibility,
assessment classification, citation validation, or abstention behaviour.

## Permissions

- Student: read the effective policy for an assigned course; never edit it.
- Instructor and administrator: read and update policy.
- Methodologist: read policy in the teacher workspace; never edit it.
- Program designer and outsiders: no tutor-policy access.

## Data and audit contract

- One optional policy row per course; absence means enabled + balanced, version 0.
- Updates use `expected_version` optimistic concurrency.
- Every accepted update records authenticated actor user ID, previous state, new
  state, and timestamp in an append-only event.
- Every answer snapshots the effective policy version and style so later quality
  work is not ambiguous.
- Request bodies never accept actor identity or free-form prompt text.

## UX contract

- Controls live beside the aggregate tutor-quality panel in the teacher course
  workspace.
- Each style explains the student experience in plain language.
- Pausing is explicit and reversible; it does not delete history.
- Student UI shows the current style and a clear paused state.
- Save success states that safety boundaries stayed active.

## Non-goals

- Choosing model/provider, temperature, system prompt, or hidden retrieval score.
- Disabling assessment protection, citations, visibility filtering, or abstention.
- Per-student settings, adaptive profiling, or automatic style selection.
- Topic-level source inclusion controls before real Canvas metadata is available.
- Canvas write-back or Canvas-side configuration.

## Acceptance criteria

- [x] Default policy is enabled + balanced without requiring a database row.
- [x] Instructor/admin can update with version checking and authenticated audit.
- [x] Student/methodologist can read but cannot update; designer receives 404.
- [x] Paused policy blocks new tutor questions without deleting history.
- [x] All three styles produce distinguishable grounded fallback presentation.
- [x] Assessment guidance and abstention remain unchanged by style.
- [x] Stored answers snapshot policy version and style.
- [x] Teacher and student UI expose policy and immutable safety boundaries.
- [x] Tests, lint/build, desktop/mobile, console, and batch reviews pass.

## Test plan

- API authorization, default, update, audit, and stale-version tests.
- Disabled ask test and answer snapshot test.
- Style-specific grounded fallback tests plus assessment/abstention regression.
- Full backend suite and frontend lint/build.
- Teacher/student desktop and mobile browser checks.

## Verification

- `python -m pytest -q`: 74 passed on 2026-07-13.
- Frontend lint and production build passed.
- Teacher policy and student active/paused states were checked at desktop and
  mobile widths with no browser console errors.
- Batch implementation, UX/accessibility, and RAG/safety reviews found no
  P0/P1 issues.
- Follow-up P2 work is recorded in `development/STATUS.md`; no next-phase work
  was started as part of this slice.
