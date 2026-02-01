from fastapi import APIRouter
from ..schemas.schemas import ExtractNodesIn, ExtractNodesOut, ClassifyNodesIn, ClassifyNodesOut
from ..utils.node_extract import extract_nodes_from_text
from ..utils.bloom import classify_bloom_multilabel

router = APIRouter(prefix="/analyze", tags=["analyze"])

@router.post("/extract", response_model=ExtractNodesOut)
def extract_nodes(payload: ExtractNodesIn):
    nodes = extract_nodes_from_text(
        payload.text,
        max_nodes=payload.max_nodes,
        min_freq=payload.min_freq,
    )
    return {"nodes": nodes}

@router.post("/classify", response_model=ClassifyNodesOut)
def classify_nodes(payload: ClassifyNodesIn):
    out_nodes = []
    for node in payload.nodes:
        text = node.context_snippet or node.title
        result = classify_bloom_multilabel(text)
        out_nodes.append({
            "title": node.title,
            "prob_vector": result["prob_vector"],
            "top_levels": result["top_levels"],
        })
    return {"nodes": out_nodes}
