# AURUS continuation checkpoint

Prepared: 2026-09-18. This is a source-code continuation checkpoint, not a
production release or approval to connect to Canvas.

## Open the correct checkout

Repository: https://github.com/JapanDino/RAG-tool

Branch: `J-D-polish-ui-and-stability` (use this branch, not `main`).

For a new checkout in PowerShell:

```powershell
git clone --branch J-D-polish-ui-and-stability --single-branch https://github.com/JapanDino/RAG-tool.git RAG-tool-canvas-agent
Set-Location RAG-tool-canvas-agent
git status --short --branch
git log -1 --format="%H %s"
git config user.name JapanDino
git config user.email klim.i.rumyantsev@gmail.com
```

If the target folder already exists, inspect its root, remote, branch and dirty
state first. Preserve local changes; do not reset, clean, or overwrite it. In a
clean checkout of the correct branch, use `git pull --ff-only`.

## Read first and resume

1. `AGENTS.md`.
2. `development/STATUS.md`: Current batch, Next batch, Known gaps, External blockers.
3. Any current spec in `development/specs/active/`; this checkpoint has none.
4. `development/specs/queued/M05-clean-self-hosted-canvas-verification.md`.
5. Only the architecture, design and integration documents relevant to the next task.

B09 research protocol freeze is complete offline. The next track is clean
self-hosted Canvas verification, conditional on an approved isolated
environment. Real Canvas transport, school access, production model-host calls,
participant collection and research activation remain blocked as documented in
STATUS. Do not rerun the completed work described in the historical August 2
online handoff. Keep the known implementation limitations visible.

## Recreate the development environment

Use Python 3.11 or 3.12 for a fresh environment matching the declared dependency
ranges, Node.js 22, npm, and Docker Desktop for the full local stack.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm --prefix frontend ci
if (!(Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
if (!(Test-Path frontend/.env.local)) { Copy-Item frontend/.env.example frontend/.env.local }
```

For Python 3.12, substitute `py -3.12`. Configure ignored environment files for
the chosen local setup, then run `docker compose up --build`. See README.md and
README_DOCKER_SETUP.md for the stack; the workspace is at
http://localhost:3000/workspace.

Quality checks from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm --prefix frontend run lint
npm --prefix frontend run build
.\.venv\Scripts\pre-commit.exe run --all-files
git diff --check
```

For the synthetic browser matrix, first activate the environment with
`.\.venv\Scripts\Activate.ps1` so the test services use its Python. Install Chromium with
`npm --prefix frontend exec -- playwright install chromium`, then run
`npm --prefix frontend run test:canvas-simulator`. Its config starts isolated
test services and expects free ports 3000 and 8000 by default. Do not run it
against an existing live stack.

## What Git carries

The checkpoint includes source, dependency manifests and frontend lockfile,
migrations through 0049, synthetic fixtures, tests, research protocol,
development specs, decisions and handoffs.

Git does not carry `.secrets/`, backend/frontend local environment files,
Claude/Cursor settings, browser sessions, `output/`, `.tmp/`, logs, local QA
screenshots, installed dependencies, model caches, or Docker database volumes.
Recreate local settings from the examples. Any separately needed secrets must
be provisioned through a secure channel; never paste them into Git or agent
prompts. Existing local database contents are not backed up by this checkpoint.

## Checkpoint verification

Fresh verification results are recorded in `development/STATUS.md` under the
2026-09-18 transfer checkpoint. Earlier browser and production-readiness claims
retain their original dates and limits. The final transfer response identifies
the pushed commit and remote verification result.
