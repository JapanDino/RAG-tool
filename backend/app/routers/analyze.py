import re

from fastapi import APIRouter

from ..schemas.schemas import AnalyzeIn, AnalyzeOut, AnalyzeChunkOut, AnalyzeEdgeOut
from ..services.bloom_classifier import bloom_probabilities
from ..services.chunking import split_into_chunks


router = APIRouter(prefix="/analyze", tags=["analyze"])

WORD_RE = re.compile(r"[\\w-]+", re.UNICODE)


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
