from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.app.services.course_retrieval import _bm25_scores
from backend.app.services.embedding import embed_texts


def evaluate_cases(path: Path, min_score: float = 0.12) -> dict:
    cases = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    hits = reciprocal_rank = abstention_correct = abstention_total = 0
    details = []
    for case in cases:
        documents = case["documents"]
        texts = [item["text"] for item in documents]
        lexical = _bm25_scores(case["query"], texts)
        try:
            vectors = embed_texts([case["query"], *texts])
            semantic = [
                max(0.0, min(1.0, sum(a * b for a, b in zip(vectors[0], vector))))
                for vector in vectors[1:]
            ]
        except Exception:
            semantic = [0.0] * len(texts)
        ranked = sorted(
            [
                (documents[index]["id"], lexical[index] * 0.6 + semantic[index] * 0.4)
                for index in range(len(documents))
            ],
            key=lambda item: (-item[1], item[0]),
        )
        ranked = [item for item in ranked if item[1] >= min_score]
        predicted = [item[0] for item in ranked[: int(case.get("top_k", 5))]]
        expected = set(case.get("expected_document_ids", []))
        if expected:
            match_rank = next(
                (
                    index
                    for index, item in enumerate(predicted, start=1)
                    if item in expected
                ),
                None,
            )
            if match_rank:
                hits += 1
                reciprocal_rank += 1.0 / match_rank
        else:
            abstention_total += 1
            abstention_correct += int(not predicted)
        details.append(
            {"id": case["id"], "expected": sorted(expected), "predicted": predicted}
        )
    retrieval_cases = len(cases) - abstention_total
    return {
        "cases": len(cases),
        "retrieval_cases": retrieval_cases,
        "recall_at_k": round(hits / retrieval_cases, 4) if retrieval_cases else 0.0,
        "mrr": round(reciprocal_rank / retrieval_cases, 4) if retrieval_cases else 0.0,
        "abstention_accuracy": (
            round(abstention_correct / abstention_total, 4)
            if abstention_total
            else None
        ),
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate the offline Course Copilot retriever"
    )
    parser.add_argument(
        "--data", type=Path, default=Path("data/course_copilot_eval.jsonl")
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument("--min-score", type=float, default=0.12)
    args = parser.parse_args()
    report = evaluate_cases(args.data, args.min_score)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
