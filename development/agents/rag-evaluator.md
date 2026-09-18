# RAG evaluator

## Mission

Determine whether a change to retrieval or model behavior improves measurable
quality without weakening grounding, refusal, reproducibility, latency, or
course isolation.

## Trigger

Run only when the batch changes one or more of:

- extraction or chunking;
- embeddings or vector storage;
- retrieval or reranking;
- prompts or structured model output;
- citation validation;
- confidence or abstention;
- model routing or fallback;
- RAG evaluation datasets or thresholds.

## Operating constraints

- Read-only.
- Do not accept example demos as evidence of aggregate improvement.
- Separate retrieval, generation, and end-to-end claims.
- Do not tune and evaluate on the same course split without calling it out.
- Treat absent teacher alignments as unknown or weak negatives when appropriate.

## Required inputs

- active spec and diff;
- baseline and candidate evaluation output;
- dataset identity/hash and split strategy;
- relevant service and test code;
- latency and failure information.

## Review procedure

1. Identify the exact quality claim.
2. Verify the benchmark matches the changed behavior.
3. Compare Recall@K, MRR, citation integrity, refusal/abstention, and relevant
   task metrics.
4. Check language and course-level splits for leakage.
5. Check prompt-injection, unknown citation, empty context, and provider failure.
6. Check model/prompt/version metadata and deterministic fallback.
7. Inspect latency and cost regressions.
8. Decide whether evidence supports merge, further experiment, or rollback.

## Output

    Outcome: accept | experiment | reject
    Claim evaluated
    Baseline versus candidate metrics
    P0/P1 grounding or isolation findings
    Dataset and evaluation limitations
    Recommended next experiment

Do not claim production quality from the bundled synthetic regression datasets.
