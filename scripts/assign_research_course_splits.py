from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

from backend.app.services.research_protocol import (  # noqa: E402
    ResearchCourseRegistry,
    assign_blinded_course_splits,
    load_research_protocol,
)

DEFAULT_PROTOCOL = (
    REPO_ROOT / "research" / "protocols" / "teacher_calibrated_multilingual_rag_v1.json"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a blinded course-level RU/EN research split manifest"
    )
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    protocol = load_research_protocol(args.protocol)
    registry = ResearchCourseRegistry.model_validate_json(
        args.registry.read_text(encoding="utf-8")
    )
    manifest = assign_blinded_course_splits(protocol, registry)
    rendered = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    print(rendered, end="")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
