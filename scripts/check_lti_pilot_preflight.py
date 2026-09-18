"""Content-minimal production configuration preflight for the Canvas pilot."""

from __future__ import annotations

import json

from backend.app.services.lti_preflight import assess_lti_pilot_preflight


def main() -> int:
    report = assess_lti_pilot_preflight()
    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if report["status"] == "ready_for_external_rehearsal" else 2


if __name__ == "__main__":
    raise SystemExit(main())
