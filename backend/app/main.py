import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import datasets, search, export, annotate, jobs, status, rubrics, analyze, taxonomy, nodes, graph, labeling, evaluate
from .routers.labeling import nodes_router as labeling_nodes_router

app = FastAPI(title="RAG Bloom API", version="0.2.0")

# Frontend runs on a different origin (localhost:3000) than API (localhost:8000).
# In dev/demo we allow broad CORS by default to avoid "TypeError: Failed to fetch".
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
    return {"ok": True}
