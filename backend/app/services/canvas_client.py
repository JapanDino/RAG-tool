"""
Canvas LMS REST API client.
Reads CANVAS_URL and CANVAS_TOKEN from environment at call time
(no module-level caching — safe for test environments that swap env vars).
"""
import os
import re
import time
from typing import Any
from urllib.parse import urlencode

import requests


def _headers() -> dict:
    token = os.getenv("CANVAS_TOKEN", "")
    if not token:
        raise RuntimeError("CANVAS_TOKEN environment variable not set")
    return {"Authorization": f"Bearer {token}"}


def _base_url() -> str:
    url = os.getenv("CANVAS_URL", "").rstrip("/")
    if not url:
        raise RuntimeError("CANVAS_URL environment variable not set")
    return url


def _parse_next_link(link_header: str) -> str | None:
    """Extract rel='next' URL from Canvas Link header."""
    for part in link_header.split(","):
        match = re.match(r'\s*<([^>]+)>;\s*rel="next"', part.strip())
        if match:
            return match.group(1)
    return None


def _check_canvas_errors(data: Any, url: str) -> None:
    """Raise a descriptive error if Canvas returned an error envelope."""
    if isinstance(data, dict) and "errors" in data:
        msgs = "; ".join(
            e.get("message") or e.get("type") or str(e)
            for e in (data["errors"] if isinstance(data["errors"], list) else [data["errors"]])
        )
        raise requests.HTTPError(
            f"Canvas API error for {url}: {msgs}",
            response=None,
        )


def get_all(path: str, params: dict | None = None) -> list[dict[str, Any]]:
    """Paginate through all pages of a Canvas list endpoint."""
    url = f"{_base_url()}/api/v1{path}"
    if params:
        url += "?" + urlencode(params)
    results: list[dict] = []
    while url:
        resp = requests.get(url, headers=_headers(), timeout=30)
        if resp.status_code == 429:
            time.sleep(5)
            continue
        resp.raise_for_status()

        # Respect Canvas leaky-bucket rate limit.
        # Formula: sleep proportional to how close we are to exhaustion.
        # Divide by 100 (not 1000) so the sleep is meaningful before hitting 429.
        remaining = float(resp.headers.get("X-Rate-Limit-Remaining", 600))
        cost = float(resp.headers.get("X-Request-Cost", 1))
        if remaining < 300:
            time.sleep(max(0.5 * cost * (300 - remaining) / 100, 0.05))

        data = resp.json()
        _check_canvas_errors(data, url)

        if isinstance(data, list):
            results.extend(data)
        else:
            return [data]
        url = _parse_next_link(resp.headers.get("Link", ""))
    return results


def get_one(path: str, params: dict | None = None) -> dict[str, Any]:
    """Fetch a single Canvas resource."""
    url = f"{_base_url()}/api/v1{path}"
    resp = requests.get(url, headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    _check_canvas_errors(data, url)
    return data


# ── Convenience wrappers ────────────────────────────────────────────────────

def list_courses(enrollment_state: str = "active") -> list[dict]:
    return get_all("/courses", {
        "enrollment_state": enrollment_state,
        "include[]": "syllabus_body",
        "per_page": 50,
    })


def list_pages(course_id: int) -> list[dict]:
    return get_all(f"/courses/{course_id}/pages", {"per_page": 50})


def get_page(course_id: int, page_url: str) -> dict:
    return get_one(f"/courses/{course_id}/pages/{page_url}")


def list_assignments(course_id: int) -> list[dict]:
    return get_all(f"/courses/{course_id}/assignments", {"per_page": 50})


def list_quizzes(course_id: int) -> list[dict]:
    return get_all(f"/courses/{course_id}/quizzes", {"per_page": 50})


def list_quiz_questions(course_id: int, quiz_id: int) -> list[dict]:
    return get_all(f"/courses/{course_id}/quizzes/{quiz_id}/questions", {"per_page": 50})


def list_discussions(course_id: int) -> list[dict]:
    return get_all(f"/courses/{course_id}/discussion_topics", {"per_page": 50})


def list_files(course_id: int) -> list[dict]:
    return get_all(f"/courses/{course_id}/files", {"per_page": 50})


def list_modules(course_id: int) -> list[dict]:
    return get_all(f"/courses/{course_id}/modules", {
        "include[]": "items",
        "per_page": 50,
    })
