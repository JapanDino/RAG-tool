from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.parse import urlparse

import requests


def _origin(value: str) -> str:
    try:
        parsed = urlparse(value)
        parsed.port
    except ValueError as exc:
        raise argparse.ArgumentTypeError("enter an exact HTTP origin") from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise argparse.ArgumentTypeError("enter an exact loopback HTTP origin")
    return value.rstrip("/")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed the two synthetic Canvas simulator LTI flows."
    )
    parser.add_argument("--api-base", type=_origin, default="http://localhost:8000")
    parser.add_argument("--canvas-base", type=_origin, default="http://localhost:3000")
    args = parser.parse_args()
    headers = {"Accept": "application/json"}
    write_key = os.getenv("API_WRITE_KEY", "").strip()
    if write_key:
        headers["X-API-Key"] = write_key
    try:
        response = requests.post(
            f"{args.api_base}/integrations/lti/development/simulator/bootstrap",
            json={
                "lti_base_url": args.api_base,
                "canvas_base_url": args.canvas_base,
            },
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"Canvas simulator bootstrap failed: {exc}", file=sys.stderr)
        return 1
    payload = response.json()
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
