# Canvas LMS Integration Guide

**Target:** Developer who built the RAG + Bloom's Taxonomy tool and wants to pull Canvas course content into the analysis pipeline.

---

## Table of Contents

1. [Authentication](#1-authentication)
2. [Key API Endpoints](#2-key-api-endpoints)
3. [Pagination](#3-pagination)
4. [Content Extraction — Stripping HTML](#4-content-extraction--stripping-html)
5. [Proposed Integration Architecture](#5-proposed-integration-architecture)
6. [Step-by-Step Setup Guide](#6-step-by-step-setup-guide)
7. [Full Code Listings](#7-full-code-listings)

---

## 1. Authentication

### 1.1 Personal Access Token (use this first)

Canvas lets any user generate a personal API token from their account settings. This is the fastest path — no OAuth app registration needed.

**Required header for every request:**

```
Authorization: Bearer <your_token_here>
```

**Test it immediately:**

```bash
curl -H "Authorization: Bearer $CANVAS_TOKEN" \
  "https://YOUR_INSTITUTION.instructure.com/api/v1/users/self"
```

A `200` response with your user JSON confirms the token works.

### 1.2 How to Generate a Token in Canvas

1. Log into your Canvas instance (e.g., `https://canvas.institution.edu`).
2. Click your **Account** avatar (top-left sidebar) → **Settings**.
3. Scroll down to **Approved Integrations**.
4. Click **+ New Access Token**.
5. Fill in **Purpose** (e.g., "RAG Bloom Tool") and optionally set an **Expiry Date**.
6. Click **Generate Token**.
7. **Copy the token immediately** — Canvas will never show it again.

### 1.3 OAuth2 vs Token Auth

| Method | When to use |
|---|---|
| **Personal token** | Your own account, development, single-tenant scripts |
| **OAuth2 Authorization Code** | Multi-user app, you need tokens per-student/teacher |
| **OAuth2 Client Credentials** | Server-to-server, needs admin approval via Developer Keys |

For this integration — a single developer ingesting their own courses — the **personal token is the right choice**. No Developer Key registration required.

### 1.4 Token Security Rules

- Store in environment variable `CANVAS_TOKEN`, never in source code.
- Tokens are password-equivalent. Rotate them if exposed.
- Tokens issued from Developer Keys (post-Oct 2015) expire after **1 hour** and need a refresh token flow. Personal tokens from Settings do not expire unless you set a date.
- For production multi-tenant use, implement OAuth2 with refresh tokens (see [Canvas OAuth2 docs](https://canvas.instructure.com/doc/api/file.oauth.html)).

---

## 2. Key API Endpoints

Base URL pattern: `https://<canvas_domain>/api/v1/`

All responses are JSON. All list endpoints are paginated (see Section 3).

### 2.1 List Courses

```
GET /api/v1/courses
```

**Useful query params:**
- `enrollment_type=teacher` or `enrollment_type=student` — filter by your role
- `enrollment_state=active` — only active enrollments
- `per_page=50` — request larger pages (max 100)
- `include[]=syllabus_body` — embed the syllabus HTML in each course object
- `include[]=total_students` — optional counts

**Example:**
```bash
curl -H "Authorization: Bearer $CANVAS_TOKEN" \
  "https://canvas.institution.edu/api/v1/courses?enrollment_state=active&include[]=syllabus_body&per_page=50"
```

**Response fields of interest:**
```json
{
  "id": 12345,
  "name": "Introduction to Python",
  "course_code": "CS101",
  "syllabus_body": "<p>Course syllabus HTML here...</p>",
  "start_at": "2025-08-25T00:00:00Z"
}
```

---

### 2.2 Course Modules

```
GET /api/v1/courses/:course_id/modules
```

**List module items within a module:**
```
GET /api/v1/courses/:course_id/modules/:module_id/items
```

Or fetch all module items for the whole course at once (more efficient):
```
GET /api/v1/courses/:course_id/modules?include[]=items&per_page=50
```

**Module item types:** `Page`, `Assignment`, `Quiz`, `File`, `Discussion`, `ExternalUrl`, `ExternalTool`, `SubHeader`

**Response (module item):**
```json
{
  "id": 789,
  "title": "Week 1: Variables",
  "type": "Page",
  "page_url": "week-1-variables",
  "url": "https://canvas.institution.edu/api/v1/courses/12345/pages/week-1-variables"
}
```

Use the `url` field to fetch the actual content of each linked item.

---

### 2.3 Pages (Wiki Pages)

```
GET /api/v1/courses/:course_id/pages
GET /api/v1/courses/:course_id/pages/:url_or_page_id
```

**List all pages:**
```bash
curl -H "Authorization: Bearer $CANVAS_TOKEN" \
  "https://canvas.institution.edu/api/v1/courses/12345/pages?per_page=50"
```

**Response fields:**
```json
{
  "page_id": 1001,
  "url": "week-1-variables",
  "title": "Week 1: Variables",
  "body": "<h2>Variables in Python</h2><p>A variable stores a value...</p>",
  "updated_at": "2025-09-01T10:00:00Z",
  "published": true
}
```

The `body` field is HTML. Strip it before analysis (see Section 4).

---

### 2.4 Assignments

```
GET /api/v1/courses/:course_id/assignments
```

**Useful params:**
- `per_page=50`
- `include[]=description` — include the full HTML description

**Response fields:**
```json
{
  "id": 2001,
  "name": "Homework 1: Loops",
  "description": "<p>Write a Python program that...</p>",
  "due_at": "2025-09-15T23:59:00Z",
  "points_possible": 100
}
```

The `description` field is HTML. Strip it before analysis.

---

### 2.5 Quizzes and Quiz Questions

**List quizzes:**
```
GET /api/v1/courses/:course_id/quizzes
```

**List questions in a quiz:**
```
GET /api/v1/courses/:course_id/quizzes/:quiz_id/questions
```

**Response (quiz question):**
```json
{
  "id": 3001,
  "quiz_id": 400,
  "question_name": "Q1",
  "question_type": "multiple_choice_question",
  "question_text": "<p>What does a for loop do?</p>",
  "answers": [
    {"text": "Repeats code", "weight": 100},
    {"text": "Defines a function", "weight": 0}
  ]
}
```

`question_text` and answer `text` fields are HTML — strip both.

> **Note on New Quizzes:** If your institution uses Canvas's newer "New Quizzes" engine (Quiz Engine v2), questions live under a separate endpoint (`/api/v1/courses/:id/new_quizzes`). The classic Quizzes API above covers the majority of deployments.

---

### 2.6 Files

```
GET /api/v1/courses/:course_id/files
```

**Response fields:**
```json
{
  "id": 5001,
  "display_name": "lecture_01.pdf",
  "filename": "lecture_01.pdf",
  "content-type": "application/pdf",
  "url": "https://canvas.institution.edu/files/5001/download?download_frd=1",
  "size": 204800
}
```

To ingest file content: download via `url` and pass the bytes to the existing `/datasets/{id}/documents` upload endpoint. The backend already handles PDF, image OCR, and plain text extraction.

---

### 2.7 Discussion Topics (and Announcements)

**Discussion topics:**
```
GET /api/v1/courses/:course_id/discussion_topics
```

**Announcements** (scoped to one or more courses):
```
GET /api/v1/announcements?context_codes[]=course_12345&context_codes[]=course_67890
```

**Response (discussion topic):**
```json
{
  "id": 6001,
  "title": "Week 1 Discussion: Your Coding Experience",
  "message": "<p>Tell the class about your prior experience...</p>",
  "posted_at": "2025-08-26T08:00:00Z"
}
```

`message` is HTML.

---

### 2.8 Syllabus Body

The syllabus is embedded in the course object itself. Fetch it with:

```
GET /api/v1/courses/:course_id?include[]=syllabus_body
```

```json
{
  "id": 12345,
  "name": "Introduction to Python",
  "syllabus_body": "<h2>Course Objectives</h2><ul><li>Understand variables</li>..."
}
```

`syllabus_body` is HTML. This is often the most content-rich single document in a course for Bloom analysis.

---

## 3. Pagination

### How It Works

Canvas uses **HTTP `Link` header pagination** — not a JSON envelope. Every list endpoint returns a `Link` header:

```
Link: <https://canvas.edu/api/v1/courses?page=1&per_page=10>; rel="current",
      <https://canvas.edu/api/v1/courses?page=2&per_page=10>; rel="next",
      <https://canvas.edu/api/v1/courses?page=1&per_page=10>; rel="first",
      <https://canvas.edu/api/v1/courses?page=5&per_page=10>; rel="last"
```

- `rel="next"` exists when there are more pages. When absent, you're on the last page.
- `rel="first"` / `rel="last"` always present.
- `rel="prev"` present on all pages except the first.
- Header name is case-insensitive — parse robustly.

### Python Helper

```python
import re
import requests

def get_all_pages(url: str, headers: dict) -> list:
    """Traverse all pages of a Canvas paginated endpoint."""
    results = []
    next_url = url
    while next_url:
        resp = requests.get(next_url, headers=headers)
        resp.raise_for_status()
        results.extend(resp.json())
        # Parse Link header for next page
        next_url = _parse_next_link(resp.headers.get("Link", ""))
    return results

def _parse_next_link(link_header: str) -> str | None:
    """Extract rel="next" URL from Canvas Link header."""
    for part in link_header.split(","):
        part = part.strip()
        match = re.match(r'<([^>]+)>;\s*rel="next"', part)
        if match:
            return match.group(1)
    return None
```

### Recommended `per_page`

- Use `per_page=50` as default. Canvas allows up to `per_page=100`.
- Do not exceed 100 — requests above this are silently capped.

---

## 4. Content Extraction — Stripping HTML

Canvas page bodies, assignment descriptions, and quiz questions are all **HTML**. You need plain text before passing to the Bloom classifier.

### Simple Approach (BeautifulSoup)

```python
from bs4 import BeautifulSoup

def html_to_text(html: str) -> str:
    """Strip HTML tags, preserve readable whitespace."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    # Remove script/style blocks
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # Collapse blank lines
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)
```

Add `beautifulsoup4` to `backend/requirements.txt`:
```
beautifulsoup4>=4.12,<5.0
lxml>=5.0,<6.0  # faster HTML parser for BeautifulSoup
```

### What to Feed Into analyze_content

For each Canvas content item, assemble a text block and call `POST /analyze/content`:

```python
# Example: one Canvas page → one call to the analyze pipeline
text = html_to_text(page["body"])
payload = {
    "text": text,
    "dataset_id": dataset_id,
    "max_nodes": 30,
    "min_prob": 0.2
}
# POST to /analyze/content
```

---

## 5. Proposed Integration Architecture

### 5.1 New Files to Create

```
backend/app/routers/canvas.py        # Two new endpoints
backend/app/services/canvas_client.py # Canvas API client (token + pagination)
```

### 5.2 Environment Variables

Add to `backend/.env`:

```env
CANVAS_URL=https://your-institution.instructure.com
CANVAS_TOKEN=your_personal_access_token_here
```

### 5.3 New Endpoints

#### `GET /canvas/courses`
Lists the authenticated user's active courses from Canvas.

#### `POST /canvas/ingest`
Pulls all text content from a course and runs it through the existing `analyze_content` pipeline, storing results in the specified dataset.

**Request body:**
```json
{
  "course_id": 12345,
  "dataset_id": 1,
  "content_types": ["syllabus", "pages", "assignments", "quizzes", "discussions"],
  "max_nodes_per_doc": 30
}
```

**Response:**
```json
{
  "course_id": 12345,
  "documents_ingested": 14,
  "nodes_created": 87,
  "skipped": []
}
```

### 5.4 Canvas Client Service

```python
# backend/app/services/canvas_client.py
import os
import re
import requests
from typing import Any

CANVAS_URL = os.getenv("CANVAS_URL", "").rstrip("/")
CANVAS_TOKEN = os.getenv("CANVAS_TOKEN", "")

def _headers() -> dict:
    return {"Authorization": f"Bearer {CANVAS_TOKEN}"}

def _parse_next_link(link_header: str) -> str | None:
    for part in link_header.split(","):
        match = re.match(r'\s*<([^>]+)>;\s*rel="next"', part.strip())
        if match:
            return match.group(1)
    return None

def get_all(path: str, params: dict | None = None) -> list[dict]:
    """Paginate through all pages of a Canvas list endpoint."""
    url = f"{CANVAS_URL}/api/v1{path}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    results = []
    while url:
        resp = requests.get(url, headers=_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            return [data]
        url = _parse_next_link(resp.headers.get("Link", ""))
    return results

def get_one(path: str, params: dict | None = None) -> dict:
    """Fetch a single Canvas resource."""
    url = f"{CANVAS_URL}/api/v1{path}"
    resp = requests.get(url, headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()

def list_courses(enrollment_state: str = "active") -> list[dict]:
    return get_all("/courses", {
        "enrollment_state": enrollment_state,
        "include[]": "syllabus_body",
        "per_page": "50"
    })

def list_pages(course_id: int) -> list[dict]:
    return get_all(f"/courses/{course_id}/pages", {"per_page": "50"})

def get_page(course_id: int, page_url: str) -> dict:
    return get_one(f"/courses/{course_id}/pages/{page_url}")

def list_assignments(course_id: int) -> list[dict]:
    return get_all(f"/courses/{course_id}/assignments", {"per_page": "50"})

def list_quizzes(course_id: int) -> list[dict]:
    return get_all(f"/courses/{course_id}/quizzes", {"per_page": "50"})

def list_quiz_questions(course_id: int, quiz_id: int) -> list[dict]:
    return get_all(f"/courses/{course_id}/quizzes/{quiz_id}/questions", {"per_page": "50"})

def list_discussions(course_id: int) -> list[dict]:
    return get_all(f"/courses/{course_id}/discussion_topics", {"per_page": "50"})
```

### 5.5 Canvas Router

```python
# backend/app/routers/canvas.py
import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from bs4 import BeautifulSoup
from typing import Optional

from ..db.session import get_db
from ..models.models import Dataset
from ..services import canvas_client as cc
from ..services.node_extractor import get_node_extractor
from ..services.bloom_multilabel import classify_bloom_multilabel
from ..services.embedding import embed_texts
from ..models.models import KnowledgeNode
from ..utils.vector import vector_literal

router = APIRouter(prefix="/canvas", tags=["canvas"])


def html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    lines = [line.strip() for line in soup.get_text(separator="\n").splitlines()]
    return "\n".join(line for line in lines if line)


class IngestRequest(BaseModel):
    course_id: int
    dataset_id: int
    content_types: list[str] = ["syllabus", "pages", "assignments", "quizzes", "discussions"]
    max_nodes_per_doc: int = 30


class IngestResponse(BaseModel):
    course_id: int
    documents_ingested: int
    nodes_created: int
    skipped: list[str]


@router.get("/courses")
def list_courses():
    """List active Canvas courses for the configured token holder."""
    if not os.getenv("CANVAS_TOKEN"):
        raise HTTPException(400, "CANVAS_TOKEN not configured")
    try:
        courses = cc.list_courses()
    except Exception as e:
        raise HTTPException(502, f"Canvas API error: {e}")
    return [{"id": c["id"], "name": c["name"], "course_code": c.get("course_code")} for c in courses]


@router.post("/ingest", response_model=IngestResponse)
def ingest_course(payload: IngestRequest, db: Session = Depends(get_db)):
    """
    Pull text content from a Canvas course and run it through
    the existing node extraction + Bloom classification pipeline.
    """
    if not os.getenv("CANVAS_TOKEN"):
        raise HTTPException(400, "CANVAS_TOKEN not configured")

    ds = db.get(Dataset, payload.dataset_id)
    if not ds:
        raise HTTPException(404, "Dataset not found")

    extractor = get_node_extractor()
    documents_ingested = 0
    nodes_created = 0
    skipped = []

    def process_text(text: str, source_label: str):
        nonlocal nodes_created
        if not text.strip():
            skipped.append(f"{source_label}: empty")
            return
        raw_nodes = extractor.extract(text, max_nodes=payload.max_nodes_per_doc, min_freq=1)
        for node in raw_nodes:
            title = node["title"]
            ctx = node.get("context_text") or node.get("snippet") or text[:400]
            cls = classify_bloom_multilabel(ctx)
            prob_vector = cls["prob_vector"]
            top_levels = [lv for lv, p in zip(
                ["remember","understand","apply","analyze","evaluate","create"], prob_vector
            ) if p >= 0.2]
            emb_list = embed_texts([ctx])
            embedding = emb_list[0] if emb_list else None
            existing = db.query(KnowledgeNode).filter(
                KnowledgeNode.dataset_id == payload.dataset_id,
                KnowledgeNode.title == title
            ).first()
            if existing:
                continue
            kn = KnowledgeNode(
                dataset_id=payload.dataset_id,
                title=title,
                context_text=ctx,
                prob_vector=prob_vector,
                top_levels=top_levels,
                embedding=vector_literal(embedding) if embedding else None,
            )
            db.add(kn)
            nodes_created += 1
        db.commit()

    cid = payload.course_id
    content_types = set(payload.content_types)

    # Syllabus
    if "syllabus" in content_types:
        try:
            course = cc.get_one(f"/courses/{cid}", {"include[]": "syllabus_body"})
            body = html_to_text(course.get("syllabus_body") or "")
            if body:
                process_text(body, f"syllabus:{cid}")
                documents_ingested += 1
        except Exception as e:
            skipped.append(f"syllabus: {e}")

    # Pages
    if "pages" in content_types:
        try:
            pages = cc.list_pages(cid)
            for page in pages:
                try:
                    full = cc.get_page(cid, page["url"])
                    text = html_to_text(full.get("body") or "")
                    process_text(text, f"page:{page['url']}")
                    documents_ingested += 1
                except Exception as e:
                    skipped.append(f"page {page.get('url')}: {e}")
        except Exception as e:
            skipped.append(f"pages list: {e}")

    # Assignments
    if "assignments" in content_types:
        try:
            assignments = cc.list_assignments(cid)
            for a in assignments:
                text = html_to_text(a.get("description") or "")
                name = a.get("name", "")
                combined = f"{name}\n\n{text}".strip()
                process_text(combined, f"assignment:{a['id']}")
                documents_ingested += 1
        except Exception as e:
            skipped.append(f"assignments: {e}")

    # Quizzes
    if "quizzes" in content_types:
        try:
            quizzes = cc.list_quizzes(cid)
            for q in quizzes:
                try:
                    questions = cc.list_quiz_questions(cid, q["id"])
                    q_texts = []
                    for qq in questions:
                        q_texts.append(html_to_text(qq.get("question_text") or ""))
                        for ans in qq.get("answers") or []:
                            q_texts.append(ans.get("text") or "")
                    combined = "\n".join(t for t in q_texts if t)
                    process_text(combined, f"quiz:{q['id']}")
                    documents_ingested += 1
                except Exception as e:
                    skipped.append(f"quiz {q.get('id')}: {e}")
        except Exception as e:
            skipped.append(f"quizzes: {e}")

    # Discussions
    if "discussions" in content_types:
        try:
            topics = cc.list_discussions(cid)
            for t in topics:
                text = html_to_text(t.get("message") or "")
                title = t.get("title", "")
                combined = f"{title}\n\n{text}".strip()
                process_text(combined, f"discussion:{t['id']}")
                documents_ingested += 1
        except Exception as e:
            skipped.append(f"discussions: {e}")

    return IngestResponse(
        course_id=cid,
        documents_ingested=documents_ingested,
        nodes_created=nodes_created,
        skipped=skipped,
    )
```

### 5.6 Register the Router in main.py

Add two lines to `backend/app/main.py`:

```python
# At the top imports:
from .routers import canvas  # add this line

# With the other app.include_router calls:
app.include_router(canvas.router)
```

### 5.7 Rate Limiting — Leaky Bucket

Canvas uses a **leaky bucket** algorithm. Each API call costs units. If the bucket fills, you get `429 Too Many Requests`.

- Watch the `X-Rate-Limit-Remaining` response header.
- If it drops below `300`, add a delay: `sleep_ms = 500 * x_request_cost * (300 - remaining)`.
- For a single-user ingestion script, the default limits are generous enough that `per_page=50` with no explicit delays is fine for courses under 200 items. Add a `time.sleep(0.1)` between page requests if you have very large courses.

```python
import time

def get_all_with_backoff(path: str, params: dict | None = None) -> list[dict]:
    """Like get_all() but respects Canvas rate limit headers."""
    url = f"{CANVAS_URL}/api/v1{path}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    results = []
    while url:
        resp = requests.get(url, headers=_headers(), timeout=30)
        if resp.status_code == 429:
            time.sleep(5)
            continue
        resp.raise_for_status()
        remaining = float(resp.headers.get("X-Rate-Limit-Remaining", 600))
        cost = float(resp.headers.get("X-Request-Cost", 1))
        if remaining < 300:
            delay = 0.5 * cost * (300 - remaining) / 1000
            time.sleep(max(delay, 0.1))
        data = resp.json()
        if isinstance(data, list):
            results.extend(data)
        url = _parse_next_link(resp.headers.get("Link", ""))
    return results
```

---

## 6. Step-by-Step Setup Guide

### Step 1: Generate Your Canvas API Token

1. Go to `https://<your-canvas-domain>/profile/settings` (or Account → Settings).
2. Scroll to **Approved Integrations** → **+ New Access Token**.
3. Set Purpose = "RAG Bloom Tool". Leave expiry blank for non-expiring or set a date.
4. Click **Generate Token**. Copy it now (shown only once).

### Step 2: Set Environment Variables

Edit `backend/.env` and add:

```env
CANVAS_URL=https://your-institution.instructure.com
CANVAS_TOKEN=paste_your_token_here
```

Common Canvas domain patterns:
- Hosted by Instructure: `https://yourinstitution.instructure.com`
- Self-hosted: `https://canvas.university.edu`

### Step 3: Install New Dependency

```bash
cd backend
pip install "beautifulsoup4>=4.12" "lxml>=5.0"
```

Or add to `requirements.txt`:
```
beautifulsoup4>=4.12,<5.0
lxml>=5.0,<6.0
```

### Step 4: Add the Files

Create these two files as shown in Section 7:
- `backend/app/services/canvas_client.py`
- `backend/app/routers/canvas.py`

Then register the router in `backend/app/main.py` (two lines from Section 5.6).

### Step 5: Restart the Backend

```bash
# If running directly:
uvicorn app.main:app --reload

# If running via Docker Compose:
docker compose restart backend
```

### Step 6: Verify Canvas Connection

```bash
# List your courses
curl -H "Authorization: Bearer $YOUR_APP_TOKEN" \
  http://localhost:8000/canvas/courses
```

You should see a JSON array of your Canvas courses.

### Step 7: Create a Dataset and Ingest a Course

```bash
# First create a dataset (if not already done)
curl -X POST http://localhost:8000/datasets \
  -H "Content-Type: application/json" \
  -d '{"name": "CS101 Canvas Course"}'
# Note the returned dataset id (e.g. 3)

# Ingest the Canvas course
curl -X POST http://localhost:8000/canvas/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "course_id": 12345,
    "dataset_id": 3,
    "content_types": ["syllabus", "pages", "assignments", "quizzes", "discussions"],
    "max_nodes_per_doc": 30
  }'
```

**Expected response:**
```json
{
  "course_id": 12345,
  "documents_ingested": 18,
  "nodes_created": 143,
  "skipped": []
}
```

### Step 8: View the Knowledge Graph

Open the frontend (`http://localhost:3000`) and navigate to the dataset you just populated. The knowledge graph will show Bloom-classified nodes extracted from the Canvas course.

---

## 7. Full Code Listings

### 7.1 canvas_client.py (complete)

```python
# backend/app/services/canvas_client.py
"""
Minimal Canvas LMS REST API client.
Reads CANVAS_URL and CANVAS_TOKEN from environment.
"""
import os
import re
import time
import requests
from typing import Any

CANVAS_URL = os.getenv("CANVAS_URL", "").rstrip("/")
CANVAS_TOKEN = os.getenv("CANVAS_TOKEN", "")


def _headers() -> dict:
    if not CANVAS_TOKEN:
        raise RuntimeError("CANVAS_TOKEN environment variable not set")
    return {"Authorization": f"Bearer {CANVAS_TOKEN}"}


def _parse_next_link(link_header: str) -> str | None:
    """Extract rel='next' URL from Canvas Link header."""
    for part in link_header.split(","):
        match = re.match(r'\s*<([^>]+)>;\s*rel="next"', part.strip())
        if match:
            return match.group(1)
    return None


def get_all(path: str, params: dict | None = None) -> list[dict[str, Any]]:
    """Paginate through all pages of a Canvas list endpoint."""
    if not CANVAS_URL:
        raise RuntimeError("CANVAS_URL environment variable not set")
    url = f"{CANVAS_URL}/api/v1{path}"
    if params:
        # Build query string manually so we can pass list params like include[]
        from urllib.parse import urlencode
        url += "?" + urlencode(params)
    results: list[dict] = []
    while url:
        resp = requests.get(url, headers=_headers(), timeout=30)
        if resp.status_code == 429:
            time.sleep(5)
            continue
        resp.raise_for_status()
        # Respect rate limit
        remaining = float(resp.headers.get("X-Rate-Limit-Remaining", 600))
        cost = float(resp.headers.get("X-Request-Cost", 1))
        if remaining < 300:
            delay = max(0.5 * cost * (300 - remaining) / 1000, 0.05)
            time.sleep(delay)
        data = resp.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            return [data]
        url = _parse_next_link(resp.headers.get("Link", ""))
    return results


def get_one(path: str, params: dict | None = None) -> dict[str, Any]:
    """Fetch a single Canvas resource."""
    if not CANVAS_URL:
        raise RuntimeError("CANVAS_URL environment variable not set")
    url = f"{CANVAS_URL}/api/v1{path}"
    resp = requests.get(url, headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


# Convenience wrappers

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
```

---

## Quick Reference

### All Canvas Endpoints Used

| Content | Endpoint |
|---|---|
| List courses | `GET /api/v1/courses` |
| Single course + syllabus | `GET /api/v1/courses/:id?include[]=syllabus_body` |
| Course modules | `GET /api/v1/courses/:id/modules?include[]=items` |
| Wiki pages list | `GET /api/v1/courses/:id/pages` |
| Single page body | `GET /api/v1/courses/:id/pages/:url` |
| Assignments | `GET /api/v1/courses/:id/assignments` |
| Quizzes | `GET /api/v1/courses/:id/quizzes` |
| Quiz questions | `GET /api/v1/courses/:id/quizzes/:quiz_id/questions` |
| Files | `GET /api/v1/courses/:id/files` |
| Discussions | `GET /api/v1/courses/:id/discussion_topics` |
| Announcements | `GET /api/v1/announcements?context_codes[]=course_:id` |

### Fields That Contain HTML (must strip before analysis)

| Endpoint | HTML field |
|---|---|
| Course | `syllabus_body` |
| Page | `body` |
| Assignment | `description` |
| Quiz question | `question_text`, `answers[].text` |
| Discussion topic | `message` |
| Announcement | `message` |

### Environment Variables

| Variable | Example value |
|---|---|
| `CANVAS_URL` | `https://myuniversity.instructure.com` |
| `CANVAS_TOKEN` | `11224~aBcDeFgHiJkLmNoPqRsTuVwXyZ...` |

---

## References

- [Canvas LMS REST API Documentation](https://canvas.instructure.com/doc/api/)
- [Canvas OAuth2 Authentication](https://canvas.instructure.com/doc/api/file.oauth.html)
- [Canvas Pagination](https://canvas.instructure.com/doc/api/file.pagination.html)
- [Canvas Throttling / Rate Limits](https://canvas.instructure.com/doc/api/file.throttling.html)
- [Canvas Pages API](https://canvas.instructure.com/doc/api/pages.html)
- [Canvas Modules API](https://canvas.instructure.com/doc/api/modules.html)
- [Canvas Quizzes API](https://canvas.instructure.com/doc/api/quizzes.html)
- [Canvas Quiz Questions API](https://canvas.instructure.com/doc/api/quiz_questions.html)
- [Canvas Announcements API](https://canvas.instructure.com/doc/api/announcements.html)
- [How to manage API access tokens (Instructure Community)](https://community.canvaslms.com/t5/Canvas-Basics-Guide/How-do-I-manage-API-access-tokens-in-my-user-account/ta-p/615312)
- [CanvasAPI Python wrapper](https://github.com/ucfopen/canvasapi)
