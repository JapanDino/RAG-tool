# Baseline quality report

## Dataset

- Source: `data/bloom_dataset.jsonl`
- Samples: 100
- Labeling style: curated educational examples for Bloom multi-label regression coverage
- Subjects covered: history, math, natural sciences, literature, language, social studies
- Bloom levels covered: remember, understand, apply, analyze, evaluate, create
- Multi-label examples: included

## Evaluation command

```powershell
python scripts\evaluate_multilabel.py --data data\bloom_dataset.jsonl --out docs\BASELINE_QUALITY_REPORT.json
```

## Aggregate metrics

| Metric | Value |
| --- | ---: |
| Hamming Loss | 0.0100 |
| F1 micro | 0.9720 |
| F1 macro | 0.9717 |
| Samples | 100 |
| Min probability | 0.20 |
| Max levels | 2 |

## Per-level metrics

| Level | Precision | Recall | F1 | TP | FP | FN |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| remember | 0.8889 | 1.0000 | 0.9412 | 16 | 2 | 0 |
| understand | 0.8947 | 1.0000 | 0.9444 | 17 | 2 | 0 |
| apply | 1.0000 | 1.0000 | 1.0000 | 16 | 0 | 0 |
| analyze | 0.9444 | 0.9444 | 0.9444 | 17 | 1 | 1 |
| evaluate | 1.0000 | 1.0000 | 1.0000 | 20 | 0 | 0 |
| create | 1.0000 | 1.0000 | 1.0000 | 18 | 0 | 0 |

## Interpretation

This report is a baseline for the current keyword/semantic MVP path, not a final proof of production model quality. The dataset is intentionally broad enough to catch regressions across subjects and Bloom levels, but it should still be reviewed and expanded with teacher-validated examples before being treated as an acceptance benchmark.

The weakest baseline areas are `remember`, `understand`, and `analyze`, where false positives or one missed label remain. Future classifier work should focus on reducing overlap between generic comparison/explanation cues and deeper analysis/evaluation cues.
