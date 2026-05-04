from sqlalchemy import String, Integer, Text, JSON, DateTime, ForeignKey, Enum, Float, Boolean, UniqueConstraint, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base
import enum
from typing import Optional

try:
    from pgvector.sqlalchemy import Vector as _Vector
    _PGVECTOR = True
except ImportError:
    _Vector = None
    _PGVECTOR = False

class JobType(str, enum.Enum): index="index"; annotate="annotate"; export="export"; graph="graph"; parse="parse"
class JobStatus(str, enum.Enum): queued="queued"; running="running"; done="done"; failed="failed"
class BloomLevel(str, enum.Enum): remember="remember"; understand="understand"; apply="apply"; analyze="analyze"; evaluate="evaluate"; create="create"

class Dataset(Base):
    __tablename__="datasets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Document(Base):
    __tablename__="documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(1000))
    mime: Mapped[str] = mapped_column(String(100), default="text/plain")
    status: Mapped[str] = mapped_column(String(50), default="ready")
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    dataset = relationship("Dataset", lazy="joined")

class Chunk(Base):
    __tablename__="chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    document = relationship("Document", lazy="joined")

class Embedding(Base):
    __tablename__="embeddings"
    __table_args__ = (UniqueConstraint("chunk_id", name="uq_embeddings_chunk_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    chunk_id: Mapped[int] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"), index=True)
    dim: Mapped[int] = mapped_column(Integer, default=1536)
    # 1536-dim storage: local model (default: multilingual-e5-large, 1024-dim) is zero-padded for OpenAI compatibility
    vec: Mapped[Optional[list]] = mapped_column(_Vector(1536) if _PGVECTOR else JSON, nullable=True)
    model: Mapped[str] = mapped_column(String(100), nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

class KnowledgeNode(Base):
    __tablename__ = "knowledge_nodes"
    __table_args__ = (
        # Prevents duplicate nodes from concurrent Canvas ingestions.
        # Covers the non-NULL document_id case (all Canvas-ingested nodes).
        # A separate partial index (see migration 0016) covers document_id IS NULL.
        UniqueConstraint("dataset_id", "document_id", "title", name="uq_kn_dataset_doc_title"),
        # HNSW index for fast cosine similarity search over node embeddings.
        # Requires pgvector >= 0.5. Alembic autogenerate won't handle this —
        # create manually or via a migration:
        #   CREATE INDEX ix_knode_vec_hnsw ON knowledge_nodes
        #   USING hnsw (vec vector_cosine_ops) WITH (m=16, ef_construction=64);
        Index("ix_knode_vec_hnsw", "vec", postgresql_using="hnsw",
              postgresql_with={"m": 16, "ef_construction": 64},
              postgresql_ops={"vec": "vector_cosine_ops"}),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)
    chunk_id: Mapped[int | None] = mapped_column(ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    context_text: Mapped[str] = mapped_column(Text)
    prob_vector: Mapped[list] = mapped_column(JSON, default=list)
    top_levels: Mapped[list] = mapped_column(JSON, default=list)
    embedding_dim: Mapped[int] = mapped_column(Integer, default=1536)
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=True)
    # 1536-dim storage: local model (default: multilingual-e5-large, 1024-dim) is zero-padded for OpenAI compatibility
    vec: Mapped[Optional[list]] = mapped_column(_Vector(1536) if _PGVECTOR else JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    model_info: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

class KnowledgeEdge(Base):
    __tablename__ = "knowledge_edges"
    __table_args__ = (
        UniqueConstraint("dataset_id", "from_node_id", "to_node_id", "method",
                         name="uq_kedge_ds_from_to_method"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    from_node_id: Mapped[int] = mapped_column(ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), index=True)
    to_node_id: Mapped[int] = mapped_column(ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), index=True)
    weight: Mapped[float] = mapped_column(Float, default=0.0)
    method: Mapped[str] = mapped_column(String(100), default="vector_topk")
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

class NodeLabel(Base):
    __tablename__ = "node_labels"
    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), index=True)
    labels: Mapped[list] = mapped_column(JSON, default=list)
    annotator: Mapped[str] = mapped_column(String(200), default="default", index=True)
    source: Mapped[str] = mapped_column(String(50), default="human")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NodeLabelRevision(Base):
    __tablename__ = "node_label_revisions"
    __table_args__ = (
        # Prevents duplicate revision rows from concurrent set_node_labels calls.
        UniqueConstraint("node_label_id", "version", name="uq_node_label_revision_version"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    node_label_id: Mapped[int] = mapped_column(ForeignKey("node_labels.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), index=True)
    labels: Mapped[list] = mapped_column(JSON, default=list)
    annotator: Mapped[str] = mapped_column(String(200), default="default", index=True)
    source: Mapped[str] = mapped_column(String(50), default="human")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Rubric(Base):
    __tablename__="rubrics"
    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[str] = mapped_column(Enum(BloomLevel), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    criteria: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

class BloomAnnotation(Base):
    __tablename__="bloom_annotations"
    __table_args__ = (UniqueConstraint("chunk_id", "level", name="uq_bloom_chunk_level"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    chunk_id: Mapped[int] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"), index=True)
    level: Mapped[str] = mapped_column(Enum(BloomLevel), index=True)
    label: Mapped[str] = mapped_column(String(200))
    rationale: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float)
    rubric_id: Mapped[int | None] = mapped_column(ForeignKey("rubrics.id", ondelete="SET NULL"), nullable=True, index=True)
    rubric = relationship("Rubric", lazy="joined")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Job(Base):
    __tablename__="jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(Enum(JobType), index=True)
    status: Mapped[str] = mapped_column(Enum(JobStatus), index=True, default=JobStatus.queued)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
