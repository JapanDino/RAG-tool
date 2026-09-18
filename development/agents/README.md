# Reviewer agents

These are canonical, tool-agnostic reviewer contracts. The main implementation
agent reads them directly when delegating a batch review.

Thin tool-specific wrappers may exist in `.claude/agents/`. Do not duplicate the
full prompt there.

## Routing

| Agent | When |
| --- | --- |
| `batch-quality-reviewer` | Every completed vertical slice |
| `product-ux-reviewer` | Material UI, navigation, copy, or interaction change |
| `rag-evaluator` | Retrieval, prompt, citation, confidence, or model change |
| `canvas-integration-reviewer` | LTI, OAuth, iframe, Canvas API, or write-back change |
| `agent-safety-reviewer` | Agent workflow, tool, memory, model routing, or approval change |
| `research-methodology-reviewer` | Benchmark, experiment, pilot, or research claim |

All reviewers are read-only. They report evidence-backed findings to the
main implementation agent. They do not commit, push, update status, or expand
the feature scope.

## Batch rule

Run reviews after acceptance criteria are implemented and focused tests pass.
Run them in parallel when their scopes are independent. After the main agent
fixes P0/P1 findings, perform one targeted recheck.
