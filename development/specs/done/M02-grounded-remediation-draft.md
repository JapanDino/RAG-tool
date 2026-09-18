# M02 — Grounded remediation draft

Status: done

## User outcome

After confirming a course issue, a teacher can generate an evidence-backed draft,
edit it, and accept or reject it without leaving the product or changing Canvas.

## Users and permissions

- Instructor: generate, edit, accept, and reject a draft for an assigned course.
- Methodologist: generate and review a methodological draft for an assigned course.
- Administrator: available only with explicit organization course access.
- Student and program designer: no access.

## Context

- Attention queue: `../done/M02-teacher-attention-queue.md`.
- Existing grounded Copilot service and suggestion persistence.
- Canvas change package remains read-only: `../../integrations/CANVAS.md`.

## Scope

- Generate a draft only after the finding is confirmed.
- Show draft, rationale, confidence, provider mode, and citations.
- Make the text editable before acceptance.
- Attribute acceptance/rejection to the authenticated reviewer.
- Preserve accepted drafts for the existing Canvas change-set preview.
- Show insufficient-context and provider-fallback states.

## Non-goals

- Automatic publication or Canvas mutation.
- Rich-text WYSIWYG editing.
- Collaborative simultaneous editing.
- Version merging across multiple accepted suggestions.
- Student-facing generation.

## User flow

1. Confirm a finding in the attention queue.
2. Select “Prepare draft”.
3. Inspect citations and why the draft addresses the finding.
4. Edit the draft text if needed.
5. Accept or reject the draft.
6. See a clear statement that Canvas was not changed.

## UX contract

- Generation is secondary to evidence review, not the first action.
- A draft without grounded context cannot be accepted.
- Citations remain visible while editing.
- “Accept draft” never implies “Publish”.
- The saved confirmation repeats that Canvas was not changed.

## Data and API

- Reuse `CourseCopilotSuggestion` and existing generation endpoints.
- Permit an edited draft in the review request and persist it atomically with the
  decision.
- Derive `reviewed_by` from the authenticated principal.

## Security and privacy

- Apply course role guards to generation and review.
- Treat retrieved content and generated draft as untrusted text.
- Keep API/provider credentials server-side.
- Never send hidden course content outside the configured model boundary.

## Acceptance criteria

- [x] Confirmed finding can produce a cited draft from the attention queue.
- [x] Unconfirmed finding cannot generate from the product flow.
- [x] Teacher can edit and accept/reject the draft.
- [x] Accepted edit and authenticated reviewer are persisted atomically.
- [x] Insufficient-context draft cannot be accepted.
- [x] UI explicitly states that Canvas was not changed.
- [x] Student/direct unauthorized requests remain non-disclosing.
- [x] Tests, build, desktop/mobile, and console checks pass.

## Verification

- `python -m pytest -q`: 61 passed.
- `npm run lint`: passed.
- `npm run build`: passed.
- Browser flow verified at 1440 x 900 and 390 x 844.
- Edited draft persisted with `instructor@local.test`; Canvas remained unchanged.
- Browser console: 0 errors, 0 warnings.

## Test plan

- Authenticated generation and reviewer-attribution API tests.
- Edited draft persistence and insufficient-context rejection tests.
- Existing Copilot and full regression suite.
- Frontend lint/build and rendered teacher/mobile states.
