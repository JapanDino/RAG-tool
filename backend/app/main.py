import os
import secrets
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .routers import (
    agent_api,
    agent_runtime,
    analyze,
    annotate,
    audits,
    canvas_oauth,
    canvas_sync,
    copilot,
    course_map,
    courses,
    datasets,
    evaluate,
    evaluation_protocols,
    evidence_packs,
    export,
    graph,
    identity,
    integrations,
    jobs,
    labeling,
    lti,
    nodes,
    organization_agent_policy,
    programs,
    rubrics,
    search,
    status,
    taxonomy,
    teacher_workspace,
    tutor_data,
    tutor_policy,
)
from .routers.labeling import nodes_router as labeling_nodes_router
from .services.node_extractor import get_node_extractor

app = FastAPI(title="RAG Bloom API", version="0.2.0")


def configured_cors() -> tuple[list[str], bool]:
    configured = os.getenv("CORS_ALLOW_ORIGINS", "*").strip()
    if (
        os.getenv("APP_ENV", "development").strip().lower() == "production"
        and configured == "*"
    ):
        raise RuntimeError("CORS_ALLOW_ORIGINS must be explicit in production")
    if configured == "*":
        return ["*"], False
    origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
    if not origins:
        raise RuntimeError("CORS_ALLOW_ORIGINS must contain at least one origin")
    for origin in origins:
        parsed = urlparse(origin)
        if (
            origin == "*"
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise RuntimeError(
                "CORS_ALLOW_ORIGINS must contain only exact HTTP(S) origins"
            )
    return origins, True


# A credentialed product session is allowed only for explicitly trusted origins.
allow_origins, allow_credentials = configured_cors()

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def protect_mutating_requests(request: Request, call_next):
    write_key = os.getenv("API_WRITE_KEY", "").strip()
    lti_platform_post = request.url.path in {
        "/integrations/lti/login",
        "/integrations/lti/launch",
    }
    agent_product_request = request.url.path.startswith("/agent/v1/")
    if (
        write_key
        and request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and not lti_platform_post
        and not agent_product_request
    ):
        supplied = request.headers.get("X-API-Key", "")
        if not secrets.compare_digest(supplied, write_key):
            return JSONResponse(
                status_code=401, content={"detail": "invalid API write key"}
            )
    return await call_next(request)


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
app.include_router(courses.router)
app.include_router(course_map.router)
app.include_router(audits.router)
app.include_router(canvas_oauth.router)
app.include_router(canvas_oauth.course_router)
app.include_router(canvas_sync.router)
app.include_router(integrations.router)
app.include_router(lti.router)
app.include_router(copilot.router)
app.include_router(evaluation_protocols.router)
app.include_router(evidence_packs.router)
app.include_router(identity.router)
app.include_router(teacher_workspace.router)
app.include_router(tutor_policy.router)
app.include_router(tutor_data.course_router)
app.include_router(tutor_data.organization_router)
app.include_router(organization_agent_policy.router)
app.include_router(programs.router)
app.include_router(agent_api.router)
app.include_router(agent_runtime.router)


@app.get("/health")
def health():
    embedding_provider = os.getenv("EMBEDDING_PROVIDER", "hash").strip().lower()
    if embedding_provider == "local":
        embedding_model = f"local:{os.getenv('EMBEDDING_MODEL_LOCAL', 'intfloat/multilingual-e5-small')}:padded1536"
    elif embedding_provider == "openai":
        embedding_model = (
            f"openai:{os.getenv('OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small')}"
        )
    elif embedding_provider == "random":
        embedding_model = "random:test-only"
    else:
        embedding_model = "hash:v1:1536"
    embedding_degraded = embedding_provider in {"hash", "random"}
    classifier_mode = os.getenv("BLOOM_CLASSIFIER", "keyword").strip().lower()
    llm_available = bool(os.getenv("OPENAI_API_KEY", "").strip())
    return {
        "ok": True,
        "quality": {
            "extractor": get_node_extractor().name,
            "embedding_model": embedding_model,
            "embedding_degraded": embedding_degraded,
            "classifier": classifier_mode,
            "llm_available": llm_available,
        },
    }
