# Development control center

This directory is the canonical technical workspace for product development.
It keeps stable decisions, the active slice, design contracts, quality gates,
integration plans, and reviewer instructions in one place.

## Directory map

| Path | Purpose | Update cadence |
| --- | --- | --- |
| `PRODUCT.md` | Users, outcomes, scope, value metrics | Rarely |
| `ARCHITECTURE.md` | Current and target system boundaries | On architectural change |
| `ROADMAP.md` | Ordered milestones and gates | At milestone review |
| `AI_CANVAS_AGENT_PLAN.md` | Detailed Canvas-agent delivery and research plan | At phase review |
| `STATUS.md` | Current verified state and next batch | Once per batch |
| `specs/active/` | One executable vertical-slice contract | During its batch |
| `specs/queued/` | Approved future slices awaiting their dependency gate | At phase planning |
| `design/` | Experience, design system, flows, screen states | At UX decisions |
| `quality/` | Test strategy and batch review gate | When the gate changes |
| `integrations/` | LMS-specific contracts | Per integration |
| `security/` | Non-negotiable security baseline | At threat-model change |
| `decisions/` | Significant architectural decisions | Append-only ADRs |
| `agents/` | Canonical reviewer prompts | Rarely |
| `agent/` | Versioned Canvas-agent API and tool contracts | At agent contract review |

## Context discipline

The main agent normally needs only:

1. root `AGENTS.md`;
2. `STATUS.md`;
3. the active spec;
4. one relevant design, security, or integration document.

Do not copy the same progress list into several files. Existing `PROGRESS.md`,
`docs/PRODUCT_PLAN.md`, `docs/ROADMAP_NEXT_STEPS.md`, and related documents are
legacy evidence until their useful content is deliberately consolidated here.

## Review cadence

A batch is one end-to-end user outcome, normally two to five working days.
Formatting and focused tests run during implementation. Full code, UX, and RAG
reviews run once when the slice meets its acceptance criteria.
