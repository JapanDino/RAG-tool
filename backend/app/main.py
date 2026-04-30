import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .routers import datasets, search, export, annotate, jobs, status, rubrics, analyze, taxonomy, nodes, graph, labeling, evaluate
from .routers.labeling import nodes_router as labeling_nodes_router
from .routers.auth import router as auth_router
from .auth.core import decode_token

app = FastAPI(title="RAG Bloom API", version="0.2.0")

# ── CORS ──────────────────────────────────────────────────────────────────────
cors_origins = os.getenv("CORS_ALLOW_ORIGINS", "*").strip()
if cors_origins == "*":
    allow_origins = ["*"]
else:
    allow_origins = [o.strip() for o in cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Auth middleware ───────────────────────────────────────────────────────────
# Routes that don't require a token:
_PUBLIC_PREFIXES = ("/auth/", "/health", "/docs", "/openapi.json", "/redoc")

AUTH_ENABLED = os.getenv("AUTH_ENABLED", "true").strip().lower() != "false"


@app.middleware("http")
async def require_auth(request: Request, call_next):
    if not AUTH_ENABLED:
        return await call_next(request)
    path = request.url.path
    if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
        return await call_next(request)
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={"detail": "Not authenticated"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth_header[len("Bearer "):]
    if decode_token(token) is None:
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid or expired token"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await call_next(request)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(datasets.router)
app.include_router(search.router)
app.include_router(export.router)
app.include_router(annotate.router)
app.include_router(jobs.router)
app.include_router(status.router)
app.include_router(rubrics.router)
app.include_router(analyze.router)
app.include_router(taxonomy.router)
app.include_router(nodes.router)
app.include_router(graph.router)
app.include_router(labeling.router)
app.include_router(labeling_nodes_router)
app.include_router(evaluate.router)


@app.get("/health")
def health():
    from .services.embedding_provider import current_embedding_model
    model = current_embedding_model()
    return {"ok": True, "embedding_model": model, "semantic": not model.startswith("hash:")}
