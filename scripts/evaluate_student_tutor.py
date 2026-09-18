from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.app.services.tutor_evaluation import (  # noqa: E402
    evaluate_tutor_benchmark,
    tutor_benchmark_markdown,
    tutor_benchmark_path,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the deterministic student-tutor readiness benchmark"
    )
    parser.add_argument("--data", type=Path, default=tutor_benchmark_path())
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero when any required benchmark threshold fails",
    )
    args = parser.parse_args()

    raw = args.data.read_bytes()
    report = evaluate_tutor_benchmark(raw, dataset_name=args.data.name)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    print(rendered, end="")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered, encoding="utf-8")
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(
            tutor_benchmark_markdown(report),
            encoding="utf-8",
        )
    if args.strict and not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
