import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..db.session import get_db
from ..models.models import KnowledgeNode
from ..schemas.schemas import (
    AnalyzeContentIn,
    AnalyzeContentOut,
    AnalyzeEdgeOut,
    AnalyzeIn,
    AnalyzeOut,
    AnalyzeChunkOut,
    ClassifyNodesIn,
    ClassifyNodesOut,
    ExtractNodesIn,
    ExtractNodesOut,
)
from ..services.bloom_classifier import bloom_probabilities
from ..services.chunking import split_into_chunks
from ..services.embedding import embed_texts
from ..services.bloom_multilabel import classify_bloom_multilabel
from ..services.node_extractor import get_node_extractor
from ..utils.vector import vector_literal

import os

router = APIRouter(prefix="/analyze", tags=["analyze"])

WORD_RE = re.compile(r"[\w-]+", re.UNICODE)


def token_set(text: str) -> set[str]:
    return set(WORD_RE.findall(text.lower()))


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = a.intersection(b)
    union = a.union(b)
    return len(inter) / len(union)


@router.post("", response_model=AnalyzeOut)
def analyze(payload: AnalyzeIn):
    chunks = split_into_chunks(payload.text)
    results = []
    for idx, chunk in enumerate(chunks):
        results.append(
            AnalyzeChunkOut(
                idx=idx,
                text=chunk,
                bloom=bloom_probabilities(chunk),
            )
        )
    edges = []
    for idx in range(len(results) - 1):
        edges.append(AnalyzeEdgeOut(source=idx, target=idx + 1, weight=1.0))

    edge_threshold = payload.edge_threshold or 0.2
    max_edges = payload.max_edges or 50
    token_sets = [token_set(item.text) for item in results]
    similarity_edges = []
    for i in range(len(token_sets)):
        for j in range(i + 1, len(token_sets)):
            weight = jaccard(token_sets[i], token_sets[j])
            if weight >= edge_threshold:
                similarity_edges.append(
                    AnalyzeEdgeOut(source=i, target=j, weight=round(weight, 4))
                )
    similarity_edges.sort(key=lambda e: e.weight, reverse=True)
    edges.extend(similarity_edges[:max_edges])
    return AnalyzeOut(total=len(results), items=results, edges=edges)


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
        result = classify_bloom_multilabel(
            text,
            min_prob=payload.min_prob or 0.2,
            max_levels=payload.max_levels or 2,
        )
        out_nodes.append({
            "title": node.title,
            "prob_vector": result["prob_vector"],
            "top_levels": result["top_levels"],
        })
    return {"nodes": out_nodes}


@router.post("/content", response_model=AnalyzeContentOut)
def analyze_content(payload: AnalyzeContentIn, db: Session = Depends(get_db)):
    nodes = get_node_extractor().extract(
        payload.text,
        max_nodes=payload.max_nodes or 30,
        min_freq=payload.min_freq or 1,
    )
    if not nodes:
        return {"nodes": []}

    stored_nodes: list[KnowledgeNode] = []
    node_rationales: list[str | None] = []
    embedding_dim = payload.embedding_dim or 1536
    if embedding_dim != 1536:
        raise HTTPException(400, "embedding_dim must be 1536 for current storage")
    embedding_model = payload.embedding_model or "text-embedding-3-small"
    min_prob = payload.min_prob or 0.2
    max_levels = payload.max_levels or 2

    # For LLM classifier: 1 call on the full text gives good context and avoids
    # N×API latency. For keyword classifier: per-node context_snippet is fast & accurate.
    use_llm = os.getenv("BLOOM_CLASSIFIER", "keyword").strip().lower() == "llm"
    cls_full = classify_bloom_multilabel(payload.text, min_prob=min_prob, max_levels=max_levels) if use_llm else None

    for node in nodes:
        if use_llm:
            cls = cls_full
        else:
            text_for_cls = node.get("context_snippet") or node["title"]
            cls = classify_bloom_multilabel(text_for_cls, min_prob=min_prob, max_levels=max_levels)
        rationale = cls.get("rationale")
        node_rationales.append(rationale)
        kn = KnowledgeNode(
            dataset_id=payload.dataset_id,
            document_id=payload.document_id,
            title=node["title"],
            context_text=node["context_snippet"],
            prob_vector=cls["prob_vector"],
            top_levels=cls["top_levels"],
            embedding_dim=embedding_dim,
            embedding_model=embedding_model,
            model_info={
                "extractor": payload.extractor or "heuristic-v1",
                "classifier": payload.classifier or "keyword-v1",
                "node_type": node.get("node_type"),
                "rationale": rationale,
            },
        )
        db.add(kn)
        stored_nodes.append(kn)

    db.commit()
    for kn in stored_nodes:
        db.refresh(kn)

    embed_inputs = [
        f"{kn.title}. {kn.context_text}".strip() for kn in stored_nodes
    ]
    vecs = embed_texts(embed_inputs, dim=embedding_dim)
    for kn, vec in zip(stored_nodes, vecs):
        db.execute(
            text("UPDATE knowledge_nodes SET vec = CAST(:v AS vector) WHERE id = :id"),
            {"v": vector_literal(vec), "id": kn.id},
        )
    db.commit()

    return {
        "nodes": [
            {
                "id": kn.id,
                "title": kn.title,
                "context_text": kn.context_text,
                "prob_vector": kn.prob_vector,
                "top_levels": kn.top_levels,
                "rationale": rationale,
            }
            for kn, rationale in zip(stored_nodes, node_rationales)
        ]
    }
