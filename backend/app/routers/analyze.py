import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import KnowledgeNode
from ..schemas.schemas import (
    AnalyzeChunkOut,
    AnalyzeContentIn,
    AnalyzeContentOut,
    AnalyzeEdgeOut,
    AnalyzeIn,
    AnalyzeOut,
    ClassifyNodesIn,
    ClassifyNodesOut,
    ExtractNodesIn,
    ExtractNodesOut,
)
from ..services.bloom_classifier import bloom_probabilities
from ..services.bloom_multilabel import classify_bloom_multilabel
from ..services.chunking import split_into_chunks
from ..services.embedding import embed_texts
from ..services.embedding_provider import current_embedding_model
from ..services.node_extractor import get_node_extractor
from ..utils.bloom import LEVEL_ORDER
from ..utils.vector import vector_literal

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


def competing_levels(prob_vector: list[float], limit: int = 3) -> list[dict]:
    ranked = sorted(
        (
            {"level": level, "probability": float(prob_vector[idx] or 0)}
            for idx, level in enumerate(LEVEL_ORDER)
        ),
        key=lambda item: item["probability"],
        reverse=True,
    )
    return ranked[:limit]


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
    nodes = get_node_extractor().extract(
        payload.text,
        max_nodes=payload.max_nodes or 100,
        min_freq=payload.min_freq or 1,
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
        out_nodes.append(
            {
                "title": node.title,
                "prob_vector": result["prob_vector"],
                "top_levels": result["top_levels"],
                "rationale": result.get("rationale"),
                "triggers": result.get("triggers"),
                "competing_levels": competing_levels(result["prob_vector"]),
            }
        )
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
    node_explanations: list[dict] = []
    embedding_dim = payload.embedding_dim or 1536
    if embedding_dim != 1536:
        raise HTTPException(400, "embedding_dim must be 1536 for current storage")
    actual_embedding_model = current_embedding_model()
    requested_embedding_model = (payload.embedding_model or "").strip() or None
    min_prob = payload.min_prob or 0.2
    max_levels = payload.max_levels or 2

    for node in nodes:
        text_for_cls = node.get("context_snippet") or node["title"]
        cls = classify_bloom_multilabel(
            text_for_cls, min_prob=min_prob, max_levels=max_levels
        )
        explanation = {
            "rationale": cls.get("rationale"),
            "triggers": cls.get("triggers") or {},
            "competing_levels": competing_levels(cls["prob_vector"]),
        }
        node_explanations.append(explanation)

        # Avoid collapsing nodes from different documents or contexts into one record.
        existing = (
            db.query(KnowledgeNode)
            .filter(
                KnowledgeNode.dataset_id == payload.dataset_id,
                KnowledgeNode.document_id == payload.document_id,
                KnowledgeNode.title == node["title"],
                KnowledgeNode.context_text == node["context_snippet"],
            )
            .first()
        )
        if existing:
            existing.context_text = node["context_snippet"]
            existing.prob_vector = cls["prob_vector"]
            existing.top_levels = cls["top_levels"]
            existing.embedding_model = actual_embedding_model
            existing.model_info = {
                "extractor": payload.extractor or "semantic-v1",
                "extractor_version": payload.extractor or "semantic-v1",
                "classifier": payload.classifier or "keyword-v1",
                "classifier_version": payload.classifier or "keyword-v1",
                "confidence_version": "prob-gap-v1",
                "node_type": node.get("node_type"),
                "frequency": node.get("frequency"),
                "source": node.get("source"),
                "rationale": explanation["rationale"],
                "triggers": explanation["triggers"],
                "competing_levels": explanation["competing_levels"],
                "requested_embedding_model": requested_embedding_model,
            }
            kn = existing
        else:
            kn = KnowledgeNode(
                dataset_id=payload.dataset_id,
                document_id=payload.document_id,
                title=node["title"],
                context_text=node["context_snippet"],
                prob_vector=cls["prob_vector"],
                top_levels=cls["top_levels"],
                embedding_dim=embedding_dim,
                embedding_model=actual_embedding_model,
                model_info={
                    "extractor": payload.extractor or "semantic-v1",
                    "extractor_version": payload.extractor or "semantic-v1",
                    "classifier": payload.classifier or "keyword-v1",
                    "classifier_version": payload.classifier or "keyword-v1",
                    "confidence_version": "prob-gap-v1",
                    "node_type": node.get("node_type"),
                    "frequency": node.get("frequency"),
                    "source": node.get("source"),
                    "rationale": explanation["rationale"],
                    "triggers": explanation["triggers"],
                    "competing_levels": explanation["competing_levels"],
                    "requested_embedding_model": requested_embedding_model,
                },
            )
            db.add(kn)
        stored_nodes.append(kn)

    db.commit()
    for kn in stored_nodes:
        db.refresh(kn)

    embed_inputs = [f"{kn.title}. {kn.context_text}".strip() for kn in stored_nodes]
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
                "frequency": (kn.model_info or {}).get("frequency"),
                "rationale": explanation.get("rationale"),
                "triggers": explanation.get("triggers"),
                "competing_levels": explanation.get("competing_levels"),
            }
            for kn, explanation in zip(stored_nodes, node_explanations)
        ]
    }
