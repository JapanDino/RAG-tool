from fastapi import APIRouter

from ..utils.taxonomy import get_taxonomy_levels

router = APIRouter(prefix="/taxonomy", tags=["taxonomy"])


@router.get("")
def list_taxonomy_levels():
    return {"levels": get_taxonomy_levels()}
