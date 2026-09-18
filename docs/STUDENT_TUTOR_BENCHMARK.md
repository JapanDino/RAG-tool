# Student tutor readiness benchmark

- Status: **PASS**
- Schema: `student-tutor-benchmark-v1`
- Dataset: `student_tutor_eval.jsonl`
- SHA-256: `87d92a583a7ebc1d2e421536eaca5d64471f63abdea787e8f11aa30f6e675a37`
- Cases: 18
- Embeddings: `hash:v1:1536`

## Required checks

| Check | Result | Threshold | Status |
|---|---:|---:|---|
| Tutor retrieval Recall@K | 1.0 | >= 0.9 | PASS |
| Tutor retrieval MRR | 1.0 | >= 0.9 | PASS |
| Unsupported-question abstention | 1.0 | >= 1.0 | PASS |
| Assessment guard accuracy | 1.0 | >= 1.0 | PASS |
| Labeled citation support | 1.0 | >= 1.0 | PASS |
| Offline tutor case p95 latency | 1.3797 | <= 250.0 | PASS |

## Failed cases

None.

## Methodology limits

- The dataset is synthetic and is a regression gate, not an independent production acceptance sample.
- Labeled citation support is a lexical evidence proxy; it does not prove semantic entailment.
- Latency excludes database, network, hosted model, and Canvas integration time.
- Case diagnostics contain synthetic IDs and outcomes, not questions or source text.
