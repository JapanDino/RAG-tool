# Roadmap Next Steps

## Purpose

This roadmap captures the next practical steps for turning the current RAG Bloom tool from a strong internal MVP into a more polished, trustworthy, and production-ready product.

The project is already useful:
- local launch is stable
- the main workflow is clearer
- the UI has a unified light/dark design
- explainability and confidence cues are now visible

At the same time, several areas still need work:
- residual UI text inconsistencies and encoding leftovers
- confidence is heuristic rather than calibrated
- classification quality still depends on a relatively simple extraction/classification stack
- test coverage is still defensive, not exhaustive
- production hardening is incomplete

---

## Priority Order

1. UX and text polish
2. Review workflow for low-confidence nodes
3. Model quality and confidence calibration
4. Explainability v2
5. QA and regression coverage
6. Security and production hardening

---

## Phase 1. UX and Text Polish

### Goal

Finish the interface polish so the product feels complete, consistent, and trustworthy.

### Tasks

- Remove remaining mixed-language UI strings such as `Annotator`, `Create`, `online`, `offline`, and other untranslated fragments.
- Eliminate remaining mojibake and broken Cyrillic in older UI sections.
- Normalize all tab descriptions, button labels, helper text, onboarding text, and settings labels into one tone of voice.
- Review all empty states and make them action-oriented.
- Ensure the right sidebar uses the same language and interaction model as the main workspace.
- Standardize labels in the graph, labeling, and dashboard views.

### Done When

- No visible broken encoding remains in the main user flows.
- No mixed Russian/English UI remains unless technically necessary.
- All primary screens feel like one product rather than stitched sections.

---

## Phase 2. Review Workflow for Low-Confidence Nodes

### Goal

Make manual verification faster and more intentional by prioritizing ambiguous nodes.

### Tasks

- Add a filter: `show only low-confidence nodes`.
- Add sorting by ambiguity: smallest gap between the top 2 Bloom levels first.
- Add a dedicated queue entry point: `Nodes requiring review`.
- Surface low-confidence counts not only in Analysis, but also in Dashboard and Labeling.
- Add quick actions:
  - send low-confidence node to labeling
  - open neighboring context
  - compare top-1 vs top-2 Bloom levels
- Highlight why a node is considered risky for auto-label acceptance.

### Done When

- A reviewer can move from ambiguous node to ambiguous node without manual searching.
- The labeling queue can be focused on the most uncertain results first.

---

## Phase 3. Model Quality and Confidence Calibration

### Goal

Improve actual classification quality, not only the interface around it.

### Tasks

- Evaluate the current extractor and classifier on a representative labeled set.
- Compare:
  - heuristic extractor
  - current multilabel classifier
  - stronger semantic extraction options
  - stronger model-backed classification options
- Replace purely heuristic confidence thresholds with calibrated bands based on observed validation behavior.
- Track model version, extractor version, and confidence version explicitly in stored metadata.
- Add a side-by-side evaluation mode for comparing old vs new classifier behavior.

### Done When

- Confidence labels reflect measured behavior rather than UI heuristics only.
- There is a documented quality baseline and at least one improved classification path.

---

## Phase 4. Explainability v2

### Goal

Move from "confidence display" to "decision transparency".

### Tasks

- Show which features influenced the classification:
  - rationale text
  - important phrases or cues
  - top competing levels
- Distinguish explanation source:
  - heuristic
  - keyword baseline
  - model rationale
- Add a compact explanation mode in cards and an expanded one in the detail modal.
- Add a "why not this other level?" explanation for close alternatives.
- If feasible, expose explanation metadata from backend explicitly instead of inferring only from `prob_vector`.

### Done When

- A user can answer:
  - why the node got this level
  - how strong the choice is
  - why the alternative level was not selected

---

## Phase 5. QA and Regression Coverage

### Goal

Raise confidence in changes and reduce UI/backend regressions.

### Tasks

- Add end-to-end scenario coverage for:
  - create dataset
  - upload/import document
  - analyze text
  - inspect nodes
  - open graph
  - send node to manual review
  - export JSON/CSV/JSONL
- Add smoke tests for light/dark themes and critical UI load paths.
- Add regression coverage for:
  - encoding regressions
  - explainability rendering
  - low-confidence queue logic
  - graph filtering behavior
- Make local and CI test execution more reproducible.

### Done When

- The core user journey is covered by automated verification.
- UI and API regressions are caught before they reach users.

---

## Phase 6. Security and Production Hardening

### Goal

Prepare the tool for broader use beyond a local/internal workflow.

### Tasks

- Add authentication and user roles.
- Restrict open access to upload and API endpoints.
- Add audit trail for manual labeling and node edits.
- Review CORS and deployment defaults.
- Add better operational logging and error boundaries.
- Define production environment configuration separately from local development.

### Done When

- The product can be deployed for real users without relying on a trusted local environment.

---

## Recommended Execution Plan

### Sprint A

- Phase 1: UX and text polish
- Phase 2: low-confidence review workflow

### Sprint B

- Phase 3: model quality and confidence calibration
- Phase 4: explainability v2

### Sprint C

- Phase 5: QA and regression coverage
- Phase 6: security and production hardening

---

## Recommended Next Immediate Task

If we continue right away, the best next step is:

`Implement a low-confidence review workflow`

Why this first:
- the confidence layer already exists
- the data is already available in the frontend
- it gives immediate product value
- it improves trust without requiring a backend redesign

---

## Notes

- The current product should be treated as a strong internal MVP, not yet as a fully production-grade classification platform.
- UI maturity is now ahead of model maturity, so the next big gains should come from review workflow and model-quality work.
