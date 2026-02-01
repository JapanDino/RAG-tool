from pydantic import BaseModel
from typing import Optional, Literal, List

BloomLevel = Literal["remember","understand","apply","analyze","evaluate","create"]

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

class ExtractNodesOut(BaseModel):
    nodes: List[ExtractNodeOut]

class ClassifyNodeIn(BaseModel):
    title: str
    context_snippet: Optional[str] = None

class ClassifyNodesIn(BaseModel):
    nodes: List[ClassifyNodeIn]

class ClassifyNodeOut(BaseModel):
    title: str
    prob_vector: List[float]
    top_levels: List[BloomLevel]

class ClassifyNodesOut(BaseModel):
    nodes: List[ClassifyNodeOut]
