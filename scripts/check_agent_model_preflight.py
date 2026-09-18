"""Emit a credential-free, network-free model-host preflight bundle."""

from __future__ import annotations

import argparse
import sys

from backend.app.services.model_preflight import (
    PROFILE_ID_BY_CLI_NAME,
    build_model_host_preflight,
    serialize_model_host_preflight,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=tuple(PROFILE_ID_BY_CLI_NAME),
        required=True,
    )
    parser.add_argument(
        "--organization-route-state",
        choices=("allowed", "deterministic_only", "not_assessed"),
        default="not_assessed",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = build_model_host_preflight(
        profile_id=PROFILE_ID_BY_CLI_NAME[args.profile],
        organization_model_route=args.organization_route_state,
    )
    sys.stdout.buffer.write(serialize_model_host_preflight(report))
    return 0 if report.status == "ready_for_credentialed_probe" else 2


if __name__ == "__main__":
    raise SystemExit(main())
