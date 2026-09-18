from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

from backend.app.services.research_protocol import (  # noqa: E402
    load_research_protocol,
    research_protocol_markdown,
    research_protocol_report,
)

DEFAULT_PROTOCOL = (
    REPO_ROOT / "research" / "protocols" / "teacher_calibrated_multilingual_rag_v1.json"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate and export the frozen B09 research protocol"
    )
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    parser.add_argument(
        "--require-analysis-ready",
        action="store_true",
        help="exit non-zero while approvals, real data, or run version pins are missing",
    )
    args = parser.parse_args()

    protocol = load_research_protocol(args.protocol)
    report = research_protocol_report(protocol, repo_root=args.repo_root)
    rendered_json = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    rendered_markdown = research_protocol_markdown(report)
    print(rendered_json, end="")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_bytes(rendered_json.encode("utf-8"))
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_bytes(rendered_markdown.encode("utf-8"))
    if args.require_analysis_ready and not report["analysis_ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
