from pydantic import BaseModel, field_validator
from typing import Optional, Literal, List, Union
from datetime import datetime


def _enum_to_str(v):
    """Coerce SQLAlchemy str-enum objects to plain strings for Pydantic Literal validation."""
    return v.value if hasattr(v, "value") else v

BloomLevel = Literal["remember","understand","apply","analyze","evaluate","create"]
NodeType = Literal["proper_noun","concept","skill","keyword","formula","other"]

class DatasetIn(BaseModel): name: str
class DatasetOut(BaseModel):
    id:int; name:str
    class Config: from_attributes=True

class DocumentOut(BaseModel):
    id:int; dataset_id:int; title:str; source:str; mime:str
    class Config: from_attributes=True

class SearchHit(BaseModel):
    chunk_id:int; text:str; score:float; document_id:int; document_title:str

class AnnotateIn(BaseModel):
    level: BloomLevel
    rubric: Optional[str]=None

class AnnotationOut(BaseModel):
    id:int; chunk_id:int; level:BloomLevel; label:str; rationale:str; score:float; version:int
    class Config: from_attributes=True

    @field_validator("level", mode="before")
    @classmethod
    def coerce_level(cls, v): return _enum_to_str(v)

class AnnotationUpdateIn(BaseModel):
    label: Optional[str] = None
    rationale: Optional[str] = None
    score: Optional[float] = None

class AnnotationWithChunkOut(BaseModel):
    id:int
    chunk_id:int
    level:BloomLevel
    label:str
    rationale:str
    score:float
    version:int
    chunk_text:str
    chunk_idx:int
    document_id:int
    document_title:str
    class Config: from_attributes=True

    @field_validator("level", mode="before")
    @classmethod
    def coerce_level(cls, v): return _enum_to_str(v)

class AnnotationListOut(BaseModel):
    total:int
    items: List[AnnotationWithChunkOut]

class RubricIn(BaseModel):
    level: BloomLevel
    name: str
    description: str
    criteria: Optional[dict] = None
    version: Optional[int] = 1
    is_active: Optional[bool] = True

class RubricOut(BaseModel):
    id:int
    level:BloomLevel
    name:str
    description:str
    criteria:dict
    version:int
    is_active:bool
    class Config: from_attributes=True

    @field_validator("level", mode="before")
    @classmethod
    def coerce_level(cls, v): return _enum_to_str(v)

class RubricListOut(BaseModel):
    total:int
    items: List[RubricOut]

class ExtractNodesIn(BaseModel):
    text: str
    max_nodes: int = 30
    min_freq: int = 1

class ExtractNodeOut(BaseModel):
    title: str
    context_snippet: str
    frequency: int
    node_type: NodeType
    source: Optional[dict] = None

class ExtractNodesOut(BaseModel):
    nodes: List[ExtractNodeOut]

class ClassifyNodeIn(BaseModel):
    title: str
    context_snippet: Optional[str] = None

class ClassifyNodesIn(BaseModel):
    nodes: List[ClassifyNodeIn]
    min_prob: Optional[float] = 0.2
    max_levels: Optional[int] = 2

class ClassifyNodeOut(BaseModel):
    title: str
    prob_vector: List[float]
    top_levels: List[BloomLevel]
    rationale: Optional[str] = None

class ClassifyNodesOut(BaseModel):
    nodes: List[ClassifyNodeOut]

class AnalyzeIn(BaseModel):
    text: str
    edge_threshold: Optional[float] = 0.2
    max_edges: Optional[int] = 50

class AnalyzeChunkOut(BaseModel):
    idx: int
    text: str
    bloom: dict[str, float]

class AnalyzeEdgeOut(BaseModel):
    source: int
    target: int
    weight: float

class AnalyzeOut(BaseModel):
    total: int
    items: List[AnalyzeChunkOut]
    edges: List[AnalyzeEdgeOut]

class KnowledgeNodeIn(BaseModel):
    dataset_id: int
    document_id: Optional[int] = None
    chunk_id: Optional[int] = None
    title: str
    context_text: str
    prob_vector: List[float]
    top_levels: List[BloomLevel]
    embedding_dim: Optional[int] = 1536
    embedding_model: Optional[str] = None
    version: Optional[int] = 1
    model_info: Optional[dict] = None

class KnowledgeNodeOut(BaseModel):
    id: int
    dataset_id: int
    document_id: Optional[int] = None
    chunk_id: Optional[int] = None
    title: str
    context_text: str
    prob_vector: List[float]
    top_levels: List[BloomLevel]
    embedding_dim: int
    embedding_model: str
    version: int
    model_info: dict
    created_at: Optional[Union[datetime, str]] = None

    class Config:
        from_attributes = True

class KnowledgeNodeUpdateIn(BaseModel):
    title: Optional[str] = None
    context_text: Optional[str] = None
    prob_vector: Optional[List[float]] = None
    top_levels: Optional[List[BloomLevel]] = None
    embedding_dim: Optional[int] = None
    embedding_model: Optional[str] = None
    version: Optional[int] = None
    model_info: Optional[dict] = None

class KnowledgeNodeBulkIn(BaseModel):
    nodes: List[KnowledgeNodeIn]

class KnowledgeNodeListOut(BaseModel):
    total: int
    items: List[KnowledgeNodeOut]

class KnowledgeNodeSearchHit(BaseModel):
    node_id: int
    title: str
    context_text: str
    score: float
    dataset_id: int
    document_id: Optional[int] = None
    chunk_id: Optional[int] = None

class NodeLabelsIn(BaseModel):
    labels: List[BloomLevel]
    annotator: str = "default"

class NodeLabelsOut(BaseModel):
    node_id: int
    annotator: str
    labels: List[BloomLevel]
    created_at: Optional[Union[datetime, str]] = None

class LabelQueueItem(BaseModel):
    id: int
    title: str
    context_text: str
    prob_vector: List[float]
    top_levels: List[BloomLevel]
    frequency: Optional[int] = None
    rationale: Optional[str] = None
    labeled: bool = False
    labels: Optional[List[BloomLevel]] = None

class LabelQueueOut(BaseModel):
    total: int
    labeled: int
    items: List[LabelQueueItem]

class NodeMergeIn(BaseModel):
    target_id: int
    source_ids: List[int]

class NodeMergeOut(BaseModel):
    ok: bool
    target_id: int
    merged: int

class AnalyzeContentIn(BaseModel):
    text: str
    dataset_id: int
    document_id: Optional[int] = None
    max_nodes: int = 30
    min_freq: int = 1
    min_prob: Optional[float] = 0.2
    max_levels: Optional[int] = 2
    embedding_dim: Optional[int] = 1536
    embedding_model: Optional[str] = None
    extractor: Optional[str] = "heuristic-v1"
    classifier: Optional[str] = "keyword-v1"

class AnalyzeNodeOut(BaseModel):
    id: int
    title: str
    context_text: str
    prob_vector: List[float]
    top_levels: List[BloomLevel]
    frequency: Optional[int] = None
    rationale: Optional[str] = None

class AnalyzeContentOut(BaseModel):
    nodes: List[AnalyzeNodeOut]

class GraphNodeOut(BaseModel):
    id: int
    title: str
    context_text: str
    prob_vector: List[float]
    top_levels: List[BloomLevel]
    frequency: Optional[int] = None
    rationale: Optional[str] = None

class GraphEdgeOut(BaseModel):
    from_id: int
    to_id: int
    weight: float

class GraphOut(BaseModel):
    nodes: List[GraphNodeOut]
    edges: List[GraphEdgeOut]

class GraphRebuildIn(BaseModel):
    dataset_id: int
    embedding_model: Optional[str] = None
    top_k: int = 5
    min_score: float = 0.2
    max_edges: int = 200
    include_cooccurrence: bool = True
    limit_nodes: int = 500
    co_window: int = 2

class GraphRebuildOut(BaseModel):
    job_id: int
