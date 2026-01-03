from fastapi import FastAPI
from .routers import datasets, search, export, annotate, jobs, status

app = FastAPI(title="RAG Bloom API", version="0.2.0")
app.include_router(datasets.router)
app.include_router(search.router)
app.include_router(export.router)
app.include_router(annotate.router)
app.include_router(jobs.router)
app.include_router(status.router)

@app.get("/health")
def health(): return {"ok": True}
