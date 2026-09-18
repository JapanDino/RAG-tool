import enum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .base import Base


class JobType(str, enum.Enum):
    index = "index"
    annotate = "annotate"
    export = "export"
    graph = "graph"
    parse = "parse"
    audit = "audit"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class BloomLevel(str, enum.Enum):
    remember = "remember"
    understand = "understand"
    apply = "apply"
    analyze = "analyze"
    evaluate = "evaluate"
    create = "create"


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(1000))
    mime: Mapped[str] = mapped_column(String(100), default="text/plain")
    status: Mapped[str] = mapped_column(String(50), default="ready")
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    course_module_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_modules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    dataset = relationship("Dataset", lazy="joined")


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    idx: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    document = relationship("Document", lazy="joined")


class Embedding(Base):
    __tablename__ = "embeddings"
    id: Mapped[int] = mapped_column(primary_key=True)
    chunk_id: Mapped[int] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"), index=True
    )
    dim: Mapped[int] = mapped_column(Integer, default=1536)
    # vec: vector(dim) — создадим колонку и индексы в SQL-миграции
    model: Mapped[str] = mapped_column(String(100), default="text-embedding-3-small")
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class KnowledgeNode(Base):
    __tablename__ = "knowledge_nodes"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(Text)
    context_text: Mapped[str] = mapped_column(Text)
    prob_vector: Mapped[list] = mapped_column(JSON, default=list)
    top_levels: Mapped[list] = mapped_column(JSON, default=list)
    embedding_dim: Mapped[int] = mapped_column(Integer, default=1536)
    embedding_model: Mapped[str] = mapped_column(
        String(100), default="text-embedding-3-small"
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    model_info: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class KnowledgeEdge(Base):
    __tablename__ = "knowledge_edges"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    from_node_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), index=True
    )
    to_node_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), index=True
    )
    weight: Mapped[float] = mapped_column(Float, default=0.0)
    method: Mapped[str] = mapped_column(String(100), default="vector_topk")
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class NodeLabel(Base):
    __tablename__ = "node_labels"
    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), index=True
    )
    labels: Mapped[list] = mapped_column(JSON, default=list)
    annotator: Mapped[str] = mapped_column(String(200), default="default", index=True)
    source: Mapped[str] = mapped_column(String(50), default="human")
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Rubric(Base):
    __tablename__ = "rubrics"
    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[str] = mapped_column(Enum(BloomLevel), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    criteria: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BloomAnnotation(Base):
    __tablename__ = "bloom_annotations"
    id: Mapped[int] = mapped_column(primary_key=True)
    chunk_id: Mapped[int] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"), index=True
    )
    level: Mapped[str] = mapped_column(Enum(BloomLevel), index=True)
    label: Mapped[str] = mapped_column(String(200))
    rationale: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float)
    rubric_id: Mapped[int | None] = mapped_column(
        ForeignKey("rubrics.id", ondelete="SET NULL"), nullable=True, index=True
    )
    rubric = relationship("Rubric", lazy="joined")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(Enum(JobType), index=True)
    status: Mapped[str] = mapped_column(
        Enum(JobStatus), index=True, default=JobStatus.queued
    )
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[str | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(300))
    external_subject: Mapped[str | None] = mapped_column(
        String(500), nullable=True, unique=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "user_id", name="ux_organization_memberships_user"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(50), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ModelInvocationEvent(Base):
    __tablename__ = "model_invocation_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('succeeded', 'fallback', 'failed')",
            name="ck_model_invocation_events_status",
        ),
        CheckConstraint(
            "latency_ms >= 0 AND input_tokens >= 0 AND output_tokens >= 0",
            name="ck_model_invocation_events_nonnegative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    task: Mapped[str] = mapped_column(String(80), index=True)
    workflow_version: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(100))
    model_alias: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), index=True)
    failure_class: Mapped[str | None] = mapped_column(
        String(40), nullable=True, index=True
    )
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    validation_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "role IN ('student', 'instructor', 'methodologist', "
            "'program_designer', 'administrator')",
            name="ck_agent_runs_role",
        ),
        CheckConstraint(
            "route_state IN ('routed', 'clarification_required', 'unsupported')",
            name="ck_agent_runs_route_state",
        ),
        CheckConstraint(
            "status IN ('queued', 'routing', 'tool_running', 'generating', "
            "'awaiting_review', 'completed', 'abstained', 'failed', 'cancelled')",
            name="ck_agent_runs_status",
        ),
        CheckConstraint(
            "(route_state = 'routed' AND workflow IS NOT NULL) OR "
            "(route_state <> 'routed' AND workflow IS NULL)",
            name="ck_agent_runs_route_workflow",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    conversation_id: Mapped[str] = mapped_column(String(64), index=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(50), index=True)
    product_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("lti_product_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    answer_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_question_answers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    module_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    selection_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    input_digest: Mapped[str] = mapped_column(String(64))
    contract_version: Mapped[str] = mapped_column(String(20))
    policy_version: Mapped[str] = mapped_column(String(40))
    workflow: Mapped[str | None] = mapped_column(String(100), nullable=True)
    route_state: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    idempotency_digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(200))
    recovery_action: Mapped[str | None] = mapped_column(String(80), nullable=True)
    result_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AgentToolEvent(Base):
    __tablename__ = "agent_tool_events"
    __table_args__ = (
        UniqueConstraint(
            "agent_run_id", "tool_name", name="ux_agent_tool_events_run_tool"
        ),
        CheckConstraint(
            "status IN ('succeeded', 'abstained', 'failed')",
            name="ck_agent_tool_events_status",
        ),
        CheckConstraint(
            "latency_ms >= 0",
            name="ck_agent_tool_events_latency",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    tool_name: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    failure_class: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (UniqueConstraint("dataset_id", name="ux_courses_dataset_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(String(50), default="manual", index=True)
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    source_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CourseMembership(Base):
    __tablename__ = "course_memberships"
    __table_args__ = (
        UniqueConstraint("course_id", "user_id", name="ux_course_memberships_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(50), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LtiRegistration(Base):
    __tablename__ = "lti_registrations"
    __table_args__ = (
        UniqueConstraint(
            "issuer",
            "client_id",
            "deployment_id",
            name="ux_lti_registrations_platform_deployment",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    issuer: Mapped[str] = mapped_column(String(1000), index=True)
    client_id: Mapped[str] = mapped_column(String(255), index=True)
    deployment_id: Mapped[str] = mapped_column(String(255), index=True)
    authorization_endpoint: Mapped[str] = mapped_column(String(2000))
    jwks_url: Mapped[str] = mapped_column(String(2000))
    tool_launch_url: Mapped[str] = mapped_column(String(2000))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_development: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CanvasOAuthConfiguration(Base):
    __tablename__ = "canvas_oauth_configurations"
    __table_args__ = (
        UniqueConstraint(
            "registration_id", name="ux_canvas_oauth_configurations_registration"
        ),
        CheckConstraint("version > 0", name="ck_canvas_oauth_configurations_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[int] = mapped_column(
        ForeignKey("lti_registrations.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    canvas_api_origin: Mapped[str] = mapped_column(String(1000))
    oauth_client_id: Mapped[str] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CanvasOAuthAttempt(Base):
    __tablename__ = "canvas_oauth_attempts"
    __table_args__ = (
        CheckConstraint(
            "(flow_kind = 'admin' AND product_session_id IS NULL "
            "AND course_id IS NULL AND canvas_course_id IS NULL) OR "
            "(flow_kind = 'instructor' AND product_session_id IS NOT NULL "
            "AND course_id IS NOT NULL AND canvas_course_id IS NOT NULL)",
            name="ck_canvas_oauth_attempts_flow_context",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[int] = mapped_column(
        ForeignKey("lti_registrations.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    flow_kind: Mapped[str] = mapped_column(String(20), default="admin")
    product_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("lti_product_sessions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=True, index=True
    )
    canvas_course_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state_digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    redirect_uri: Mapped[str] = mapped_column(String(2000))
    canvas_api_origin: Mapped[str] = mapped_column(String(1000))
    oauth_client_id: Mapped[str] = mapped_column(String(255))
    requested_scopes: Mapped[list] = mapped_column(JSON, default=list)
    expires_at: Mapped[str] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[str | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CanvasOAuthConnection(Base):
    __tablename__ = "canvas_oauth_connections"
    __table_args__ = (
        UniqueConstraint(
            "registration_id", "user_id", name="ux_canvas_oauth_connections_user"
        ),
        CheckConstraint(
            "connection_mode IN ('fake_development')",
            name="ck_canvas_oauth_connections_mode",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[int] = mapped_column(
        ForeignKey("lti_registrations.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    canvas_api_origin: Mapped[str] = mapped_column(String(1000))
    granted_scopes: Mapped[list] = mapped_column(JSON, default=list)
    vault_reference: Mapped[str] = mapped_column(String(255), unique=True)
    connection_mode: Mapped[str] = mapped_column(String(30))
    expires_at: Mapped[str] = mapped_column(DateTime(timezone=True), index=True)
    connected_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    revoked_at: Mapped[str | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CanvasOAuthEvent(Base):
    __tablename__ = "canvas_oauth_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('configured', 'connected', 'disconnected')",
            name="ck_canvas_oauth_events_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    registration_id: Mapped[int | None] = mapped_column(
        ForeignKey("lti_registrations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(30), index=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LtiRegistrationEvent(Base):
    __tablename__ = "lti_registration_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('created', 'updated', 'activated', 'deactivated')",
            name="ck_lti_registration_events_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    registration_id: Mapped[int | None] = mapped_column(
        ForeignKey("lti_registrations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(30), index=True)
    changed_fields: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LtiSubjectBinding(Base):
    __tablename__ = "lti_subject_bindings"
    __table_args__ = (
        UniqueConstraint(
            "registration_id", "platform_subject", name="ux_lti_subject_bindings_sub"
        ),
        UniqueConstraint(
            "registration_id", "user_id", name="ux_lti_subject_bindings_user"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[int] = mapped_column(
        ForeignKey("lti_registrations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    platform_subject: Mapped[str] = mapped_column(String(255), index=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LtiContextBinding(Base):
    __tablename__ = "lti_context_bindings"
    __table_args__ = (
        UniqueConstraint(
            "registration_id",
            "platform_context_id",
            name="ux_lti_context_bindings_context",
        ),
        UniqueConstraint(
            "registration_id", "course_id", name="ux_lti_context_bindings_course"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[int] = mapped_column(
        ForeignKey("lti_registrations.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    platform_context_id: Mapped[str] = mapped_column(String(255), index=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LtiBindingCandidate(Base):
    __tablename__ = "lti_binding_candidates"
    __table_args__ = (
        UniqueConstraint(
            "registration_id",
            "candidate_type",
            "identifier_digest",
            name="ux_lti_binding_candidates_identifier",
        ),
        CheckConstraint(
            "candidate_type IN ('subject', 'context')",
            name="ck_lti_binding_candidates_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'bound', 'dismissed', 'expired')",
            name="ck_lti_binding_candidates_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[int] = mapped_column(
        ForeignKey("lti_registrations.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    candidate_type: Mapped[str] = mapped_column(String(20), index=True)
    identifier_digest: Mapped[str] = mapped_column(String(64), index=True)
    platform_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    seen_count: Mapped[int] = mapped_column(Integer, default=1)
    first_seen_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    expires_at: Mapped[str] = mapped_column(DateTime(timezone=True), index=True)
    resolved_at: Mapped[str | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    resolved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), nullable=True, index=True
    )


class LtiBindingEvent(Base):
    __tablename__ = "lti_binding_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('bound', 'dismissed')",
            name="ck_lti_binding_events_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    registration_id: Mapped[int | None] = mapped_column(
        ForeignKey("lti_registrations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    candidate_id: Mapped[int | None] = mapped_column(
        ForeignKey("lti_binding_candidates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(20), index=True)
    target_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    target_course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LtiLaunchAttempt(Base):
    __tablename__ = "lti_launch_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[int] = mapped_column(
        ForeignKey("lti_registrations.id", ondelete="CASCADE"), index=True
    )
    state_digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    nonce_digest: Mapped[str] = mapped_column(String(64))
    target_link_uri: Mapped[str] = mapped_column(String(2000))
    expires_at: Mapped[str] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[str | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LtiLaunchAuditEvent(Base):
    __tablename__ = "lti_launch_audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[int | None] = mapped_column(
        ForeignKey("lti_registrations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    outcome: Mapped[str] = mapped_column(String(20), index=True)
    reason_code: Mapped[str] = mapped_column(String(50), index=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LtiProductSession(Base):
    __tablename__ = "lti_product_sessions"
    __table_args__ = (
        CheckConstraint(
            "role IN ('student', 'instructor')",
            name="ck_lti_product_sessions_role",
        ),
        Index(
            "ux_lti_product_sessions_active_scope",
            "registration_id",
            "user_id",
            "course_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[int] = mapped_column(
        ForeignKey("lti_registrations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(50), index=True)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[str] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[str | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Program(Base):
    __tablename__ = "programs"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="ux_programs_org_code"),
        CheckConstraint("version > 0", name="ck_programs_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProgramCourse(Base):
    __tablename__ = "program_courses"
    __table_args__ = (
        UniqueConstraint(
            "program_id", "course_id", name="ux_program_courses_program_course"
        ),
        UniqueConstraint(
            "program_id", "position", name="ux_program_courses_program_position"
        ),
        CheckConstraint("position > 0", name="ck_program_courses_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    added_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Competency(Base):
    __tablename__ = "competencies"
    __table_args__ = (
        UniqueConstraint("program_id", "code", name="ux_competencies_program_code"),
        UniqueConstraint("program_id", "id", name="ux_competencies_program_id_id"),
        CheckConstraint("position >= 0", name="ck_competencies_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProgramPrerequisiteRelation(Base):
    __tablename__ = "program_prerequisite_relations"
    __table_args__ = (
        UniqueConstraint(
            "program_id",
            "prerequisite_competency_id",
            "target_competency_id",
            name="ux_program_prerequisites_directed_pair",
        ),
        ForeignKeyConstraint(
            ["program_id", "prerequisite_competency_id"],
            ["competencies.program_id", "competencies.id"],
            name="fk_program_prerequisites_prerequisite",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["program_id", "target_competency_id"],
            ["competencies.program_id", "competencies.id"],
            name="fk_program_prerequisites_target",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "prerequisite_competency_id <> target_competency_id",
            name="ck_program_prerequisites_not_self",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), index=True
    )
    prerequisite_competency_id: Mapped[int] = mapped_column(Integer, index=True)
    target_competency_id: Mapped[int] = mapped_column(Integer, index=True)
    rationale: Mapped[str] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CourseContribution(Base):
    __tablename__ = "course_contributions"
    __table_args__ = (
        UniqueConstraint(
            "competency_id",
            "course_id",
            name="ux_course_contributions_competency_course",
        ),
        ForeignKeyConstraint(
            ["program_id", "course_id"],
            ["program_courses.program_id", "program_courses.course_id"],
            name="fk_course_contributions_program_course",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "stage IN ('introduced', 'developed', 'assessed')",
            name="ck_course_contributions_stage",
        ),
        CheckConstraint(
            "evidence_type IN ('learning_objective', 'assessment_item', 'manual_note')",
            name="ck_course_contributions_evidence_type",
        ),
        CheckConstraint(
            "(evidence_type = 'manual_note' AND evidence_id IS NULL) OR "
            "(evidence_type <> 'manual_note' AND evidence_id IS NOT NULL)",
            name="ck_course_contributions_evidence_reference",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), index=True
    )
    competency_id: Mapped[int] = mapped_column(
        ForeignKey("competencies.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    stage: Mapped[str] = mapped_column(String(50), index=True)
    rationale: Mapped[str] = mapped_column(Text)
    evidence_type: Mapped[str] = mapped_column(String(50), index=True)
    evidence_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProgramChangeEvent(Base):
    __tablename__ = "program_change_events"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_program_change_events_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer)
    event_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ProgramReviewNote(Base):
    __tablename__ = "program_review_notes"
    __table_args__ = (
        UniqueConstraint(
            "program_id",
            "finding_key",
            name="ux_program_review_notes_program_finding",
        ),
        CheckConstraint(
            "decision IN ('act', 'observe', 'dismiss')",
            name="ck_program_review_notes_decision",
        ),
        CheckConstraint("version > 0", name="ck_program_review_notes_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    program_id: Mapped[int] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), index=True
    )
    finding_key: Mapped[str] = mapped_column(String(160))
    finding_kind: Mapped[str] = mapped_column(String(50), index=True)
    source_digest: Mapped[str] = mapped_column(String(64), index=True)
    initial_draft_digest: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(String(20), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MembershipAuditEvent(Base):
    __tablename__ = "membership_audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=True, index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    previous_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    new_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    event_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CourseModule(Base):
    __tablename__ = "course_modules"
    __table_args__ = (
        UniqueConstraint("course_id", "external_id", name="ux_course_modules_external"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class CanvasOutcomeAlignment(Base):
    __tablename__ = "canvas_outcome_alignments"
    __table_args__ = (
        UniqueConstraint(
            "course_id",
            "outcome_external_id",
            "assignment_external_id",
            name="ux_canvas_outcome_alignments_pair",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    outcome_external_id: Mapped[str] = mapped_column(String(255), index=True)
    assignment_external_id: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    submission_types: Mapped[list] = mapped_column(JSON, default=list)
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AuditRun(Base):
    __tablename__ = "audit_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(50), default="queued", index=True)
    pipeline_version: Mapped[str] = mapped_column(
        String(100), default="course-audit-v1"
    )
    extractor_version: Mapped[str] = mapped_column(
        String(100), default="objective-baseline-v1"
    )
    classifier_version: Mapped[str] = mapped_column(
        String(100), default="bloom-keyword-v1"
    )
    embedding_model: Mapped[str] = mapped_column(String(200), default="")
    relation_model: Mapped[str] = mapped_column(
        String(200), default="hybrid-baseline-v1"
    )
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[str | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class LearningObjective(Base):
    __tablename__ = "learning_objectives"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    module_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_modules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    audit_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("audit_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    text: Mapped[str] = mapped_column(Text)
    normalized_text: Mapped[str] = mapped_column(Text, default="")
    bloom_vector: Mapped[list] = mapped_column(JSON, default=list)
    top_bloom_levels: Mapped[list] = mapped_column(JSON, default=list)
    source_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(100), default="baseline")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    model_info: Mapped[dict] = mapped_column(JSON, default=dict)
    review_status: Mapped[str] = mapped_column(
        String(50), default="unreviewed", index=True
    )


class LearningMaterial(Base):
    __tablename__ = "learning_materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    module_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_modules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    audit_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("audit_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    material_type: Mapped[str] = mapped_column(String(50), default="other", index=True)
    title: Mapped[str] = mapped_column(String(500))
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    source_text: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class AssessmentItem(Base):
    __tablename__ = "assessment_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    module_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_modules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    audit_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("audit_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assessment_type: Mapped[str] = mapped_column(
        String(50), default="other", index=True
    )
    title: Mapped[str] = mapped_column(String(500), default="")
    text: Mapped[str] = mapped_column(Text)
    expected_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    bloom_vector: Mapped[list] = mapped_column(JSON, default=list)
    top_bloom_levels: Mapped[list] = mapped_column(JSON, default=list)
    source_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(100), default="baseline")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    model_info: Mapped[dict] = mapped_column(JSON, default=dict)
    review_status: Mapped[str] = mapped_column(
        String(50), default="unreviewed", index=True
    )


class AlignmentEdge(Base):
    __tablename__ = "alignment_edges"
    __table_args__ = (
        UniqueConstraint(
            "audit_run_id",
            "source_type",
            "source_id",
            "target_type",
            "target_id",
            "relation_type",
            name="ux_alignment_edges_run_relation",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    audit_run_id: Mapped[int] = mapped_column(
        ForeignKey("audit_runs.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(50))
    source_id: Mapped[int] = mapped_column(Integer)
    target_type: Mapped[str] = mapped_column(String(50))
    target_id: Mapped[int] = mapped_column(Integer)
    relation_type: Mapped[str] = mapped_column(String(50), index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    method: Mapped[str] = mapped_column(String(100), default="hybrid-baseline-v1")
    model_info: Mapped[dict] = mapped_column(JSON, default=dict)
    review_status: Mapped[str] = mapped_column(
        String(50), default="unreviewed", index=True
    )
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AlignmentCandidate(Base):
    __tablename__ = "alignment_candidates"
    __table_args__ = (
        UniqueConstraint(
            "audit_run_id",
            "source_id",
            "target_id",
            "relation_type",
            name="ux_alignment_candidates_pair",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    audit_run_id: Mapped[int] = mapped_column(
        ForeignKey("audit_runs.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(50))
    source_id: Mapped[int] = mapped_column(Integer)
    target_type: Mapped[str] = mapped_column(String(50))
    target_id: Mapped[int] = mapped_column(Integer)
    relation_type: Mapped[str] = mapped_column(String(50), index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    selected: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    method: Mapped[str] = mapped_column(String(100), default="hybrid-baseline-v1")
    model_info: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CourseFinding(Base):
    __tablename__ = "course_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    module_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_modules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    audit_run_id: Mapped[int] = mapped_column(
        ForeignKey("audit_runs.id", ondelete="CASCADE"), index=True
    )
    finding_type: Mapped[str] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="medium", index=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    recommendation: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    uncertainty_reasons: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(50), default="new", index=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[str | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    model_info: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FindingReviewEvent(Base):
    __tablename__ = "finding_review_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    finding_id: Mapped[int] = mapped_column(
        ForeignKey("course_findings.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    audit_run_id: Mapped[int] = mapped_column(
        ForeignKey("audit_runs.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[str] = mapped_column(String(50))
    to_status: Mapped[str] = mapped_column(String(50))
    reviewed_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CourseCopilotSuggestion(Base):
    __tablename__ = "course_copilot_suggestions"

    id: Mapped[int] = mapped_column(primary_key=True)
    finding_id: Mapped[int] = mapped_column(
        ForeignKey("course_findings.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    audit_run_id: Mapped[int] = mapped_column(
        ForeignKey("audit_runs.id", ondelete="CASCADE"), index=True
    )
    action_type: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(500))
    draft: Mapped[str] = mapped_column(Text)
    target_bloom_level: Mapped[str] = mapped_column(String(50), index=True)
    rationale: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    retrieval_method: Mapped[str] = mapped_column(String(255))
    generation_provider: Mapped[str] = mapped_column(String(100))
    generation_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    insufficient_context: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    review_reason: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[str | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CourseInterventionDraft(Base):
    __tablename__ = "course_intervention_drafts"
    __table_args__ = (
        CheckConstraint(
            "signal_kind IN ('repeated_unsupported', 'low_helpfulness', 'mixed')",
            name="ck_course_intervention_drafts_signal_kind",
        ),
        CheckConstraint(
            "status IN ('draft', 'accepted', 'rejected')",
            name="ck_course_intervention_drafts_status",
        ),
        CheckConstraint(
            "version >= 1",
            name="ck_course_intervention_drafts_version_positive",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    source_dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    source_document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    source_chunk_id: Mapped[int] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"), index=True
    )
    source_audit_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("audit_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    aggregate_digest: Mapped[str] = mapped_column(String(64), index=True)
    signal_kind: Mapped[str] = mapped_column(String(40), index=True)
    cohort_band: Mapped[str] = mapped_column(String(20))
    event_band: Mapped[str] = mapped_column(String(20))
    window_started_at: Mapped[str] = mapped_column(DateTime(timezone=True))
    window_ended_at: Mapped[str] = mapped_column(DateTime(timezone=True))
    title: Mapped[str] = mapped_column(String(500))
    initial_content: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reviewed_at: Mapped[str | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_reason: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True
    )
    edit_distance_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    decision_latency_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CourseTutorPolicy(Base):
    __tablename__ = "course_tutor_policies"
    __table_args__ = (
        UniqueConstraint("course_id", name="ux_course_tutor_policies_course"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    answer_style: Mapped[str] = mapped_column(
        String(50), default="balanced", index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CourseTutorPolicyEvent(Base):
    __tablename__ = "course_tutor_policy_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int] = mapped_column(
        ForeignKey("course_tutor_policies.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    previous_state: Mapped[dict] = mapped_column(JSON, default=dict)
    new_state: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OrganizationTutorDataPolicy(Base):
    __tablename__ = "organization_tutor_data_policies"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", name="ux_organization_tutor_data_policies_org"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    retention_days: Mapped[int] = mapped_column(Integer, default=90)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OrganizationTutorDataPolicyEvent(Base):
    __tablename__ = "organization_tutor_data_policy_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int] = mapped_column(
        ForeignKey("organization_tutor_data_policies.id", ondelete="CASCADE"),
        index=True,
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    previous_state: Mapped[dict] = mapped_column(JSON, default=dict)
    new_state: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OrganizationAgentPolicy(Base):
    __tablename__ = "organization_agent_policies"
    __table_args__ = (
        UniqueConstraint("organization_id", name="ux_organization_agent_policies_org"),
        CheckConstraint(
            "model_mode IN ('approved_host_with_safe_fallback', 'deterministic_only')",
            name="ck_organization_agent_policies_model_mode",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    learner_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    instructor_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    program_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    model_mode: Mapped[str] = mapped_column(
        String(50), default="approved_host_with_safe_fallback"
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OrganizationAgentPolicyEvent(Base):
    __tablename__ = "organization_agent_policy_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int] = mapped_column(
        ForeignKey("organization_agent_policies.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    previous_state: Mapped[dict] = mapped_column(JSON, default=dict)
    new_state: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TutorDataDeletionEvent(Base):
    __tablename__ = "tutor_data_deletion_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    subject_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reason: Mapped[str] = mapped_column(String(50), index=True)
    policy_version: Mapped[int] = mapped_column(Integer, default=0)
    cutoff: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answers_deleted: Mapped[int] = mapped_column(Integer, default=0)
    feedback_events_deleted: Mapped[int] = mapped_column(Integer, default=0)
    agent_runs_deleted: Mapped[int] = mapped_column(Integer, default=0)
    agent_run_cutoff: Mapped[str | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CourseQuestionAnswer(Base):
    __tablename__ = "course_question_answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    asked_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    retrieval_method: Mapped[str] = mapped_column(String(255))
    generation_provider: Mapped[str] = mapped_column(String(100))
    generation_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    insufficient_context: Mapped[bool] = mapped_column(
        Boolean, default=False, index=True
    )
    response_mode: Mapped[str] = mapped_column(String(50), default="answer", index=True)
    policy_reason: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    tutor_policy_version: Mapped[int] = mapped_column(Integer, default=0)
    tutor_answer_style: Mapped[str] = mapped_column(
        String(50), default="balanced", index=True
    )
    feedback_status: Mapped[str] = mapped_column(
        String(50), default="unreviewed", index=True
    )
    feedback_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[str | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CourseQaFeedbackEvent(Base):
    __tablename__ = "course_qa_feedback_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    answer_id: Mapped[int] = mapped_column(
        ForeignKey("course_question_answers.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    from_status: Mapped[str] = mapped_column(String(50))
    to_status: Mapped[str] = mapped_column(String(50))
    reviewed_by: Mapped[str] = mapped_column(String(255))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CourseEvaluationProtocol(Base):
    __tablename__ = "course_evaluation_protocols"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(50), index=True)
    protocol_version: Mapped[str] = mapped_column(String(100))
    dataset_name: Mapped[str] = mapped_column(String(255))
    dataset_hash: Mapped[str] = mapped_column(String(64), index=True)
    thresholds: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    checks: Mapped[list] = mapped_column(JSON, default=list)
    methodology: Mapped[list] = mapped_column(JSON, default=list)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
