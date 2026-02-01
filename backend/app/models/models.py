from sqlalchemy import String, Integer, Text, JSON, DateTime, ForeignKey, Enum, Float, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base
import enum

class JobType(str, enum.Enum): index="index"; annotate="annotate"; export="export"
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
    id: Mapped[int] = mapped_column(primary_key=True)
    chunk_id: Mapped[int] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"), index=True)
    dim: Mapped[int] = mapped_column(Integer, default=1536)
    # vec: vector(dim) — создадим колонку и индексы в SQL-миграции
    model: Mapped[str] = mapped_column(String(100), default="text-embedding-3-small")
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

class KnowledgeNode(Base):
    __tablename__ = "knowledge_nodes"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)
    chunk_id: Mapped[int | None] = mapped_column(ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    context_text: Mapped[str] = mapped_column(Text)
    prob_vector: Mapped[dict] = mapped_column(JSON, default=dict)
    top_levels: Mapped[list] = mapped_column(JSON, default=list)
    embedding_dim: Mapped[int] = mapped_column(Integer, default=1536)
    embedding_model: Mapped[str] = mapped_column(String(100), default="text-embedding-3-small")
    version: Mapped[int] = mapped_column(Integer, default=1)
    model_info: Mapped[dict] = mapped_column(JSON, default=dict)
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
