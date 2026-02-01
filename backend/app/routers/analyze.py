from fastapi import APIRouter

from ..schemas.schemas import AnalyzeIn, AnalyzeOut, AnalyzeChunkOut, AnalyzeEdgeOut
from ..services.bloom_classifier import bloom_probabilities
from ..services.chunking import split_into_chunks


router = APIRouter(prefix="/analyze", tags=["analyze"])


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
    return AnalyzeOut(total=len(results), items=results, edges=edges)
