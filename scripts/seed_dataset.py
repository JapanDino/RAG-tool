#!/usr/bin/env python3
"""
Seed bloom_dataset.jsonl into the API as labeled knowledge nodes.

Usage:
    python scripts/seed_dataset.py --dataset-id 1
    python scripts/seed_dataset.py --dataset-id 1 --api http://localhost:8000
    python scripts/seed_dataset.py --dataset-id 1 --annotator teacher1 --dry-run

Each JSONL line must be: {"text": "...", "labels": ["remember", ...]}

The script:
  1. Calls POST /analyze/content for each example to extract+classify nodes.
  2. For each returned node, calls PUT /nodes/{id}/labels with the gold labels.
"""

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("requests not installed — run: pip install requests")

DATASET_FILE = Path(__file__).parent.parent / "data" / "bloom_dataset.jsonl"


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset-id", type=int, required=True, help="Target dataset ID in the DB")
    p.add_argument("--api", default="http://localhost:8000", help="API base URL (default: http://localhost:8000)")
    p.add_argument("--annotator", default="seed", help="Annotator name for labels (default: seed)")
    p.add_argument("--file", type=Path, default=DATASET_FILE, help="Path to JSONL file")
    p.add_argument("--dry-run", action="store_true", help="Parse and validate without calling API")
    p.add_argument("--delay", type=float, default=0.1, help="Seconds to wait between requests (default: 0.1)")
    return p.parse_args()


def load_examples(path: Path) -> list[dict]:
    examples = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                sys.exit(f"Line {i}: invalid JSON — {e}")
            if "text" not in obj or "labels" not in obj:
                sys.exit(f"Line {i}: missing 'text' or 'labels' field")
            examples.append(obj)
    return examples


def main():
    args = parse_args()
    examples = load_examples(args.file)
    print(f"Loaded {len(examples)} examples from {args.file}")

    if args.dry_run:
        print("[dry-run] Validation OK — no API calls made.")
        return

    session = requests.Session()
    session.headers["Content-Type"] = "application/json"

    ok = fail = labeled = 0

    for i, ex in enumerate(examples, 1):
        text: str = ex["text"]
        gold_labels: list[str] = ex["labels"]

        # 1. Analyze content → extract+classify nodes
        try:
            r = session.post(
                f"{args.api}/analyze/content",
                json={"text": text, "dataset_id": args.dataset_id},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"  [{i}/{len(examples)}] FAIL analyze: {e}")
            fail += 1
            continue

        nodes = data.get("nodes", [])
        if not nodes:
            print(f"  [{i}/{len(examples)}] SKIP (no nodes extracted): {text[:60]}")
            fail += 1
            continue

        # 2. Label every extracted node with the gold labels from the dataset
        for node in nodes:
            node_id = node["id"]
            try:
                r2 = session.put(
                    f"{args.api}/nodes/{node_id}/labels",
                    json={"labels": gold_labels, "annotator": args.annotator},
                    timeout=10,
                )
                r2.raise_for_status()
                labeled += 1
            except Exception as e:
                print(f"    node {node_id}: FAIL label: {e}")

        ok += 1
        print(f"  [{i}/{len(examples)}] OK — {len(nodes)} node(s) labeled {gold_labels}: {text[:60]}")

        if args.delay:
            time.sleep(args.delay)

    print(f"\nDone. analyzed={ok}, failed={fail}, nodes_labeled={labeled}")
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
