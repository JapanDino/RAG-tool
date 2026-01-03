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
    id:int; chunk_id:int; level:BloomLevel; label:str; rationale:str; score:float
    class Config: from_attributes=True
