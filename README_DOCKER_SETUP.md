# RAG Bloom Project: Local Dev Quickstart

## Recommended local mode

The most reliable local setup is:

1. `db + redis + backend` in Docker
2. `frontend` locally via `npm`
3. lightweight offline-first defaults in `backend/.env`
   - `EMBEDDING_PROVIDER=hash`
   - `NODE_EXTRACTOR=heuristic`

This avoids large model downloads during startup.

## One-command start on Windows PowerShell

From the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-local.ps1
```

The script will:

- build and start `db`, `redis`, and `backend`
- wait for `http://127.0.0.1:8000/health`
- install frontend dependencies if needed
- launch the Next.js dev server in a new PowerShell window

## Manual start

### 1. Start backend infrastructure

```powershell
docker compose up -d --build db redis backend
```

Check backend health:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health
```

Expected response:

```json
{"ok":true}
```

### 2. Install frontend dependencies

```powershell
cd frontend
npm install --fetch-timeout=600000 --fetch-retries=10 --fetch-retry-mintimeout=20000 --fetch-retry-maxtimeout=120000
```

### 3. Start frontend

```powershell
$env:NEXT_PUBLIC_API_BASE="http://localhost:8000"
npm run dev
```

Frontend:

[http://127.0.0.1:3000](http://127.0.0.1:3000)

Backend:

[http://127.0.0.1:8000](http://127.0.0.1:8000)

## Useful commands

Check the local stack:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check-local.ps1
```

Tail backend logs:

```powershell
docker compose logs --tail=80 backend
```

Stop services:

```powershell
docker compose down
```
