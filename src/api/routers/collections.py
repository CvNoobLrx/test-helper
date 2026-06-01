"""Collections router."""

from fastapi import APIRouter

from src.api.dependencies import get_data_service

router = APIRouter()


@router.get("")
async def list_collections():
    ds = get_data_service()
    collections = ds.list_collections()
    result = []
    for name in collections:
        try:
            stats = ds.get_collection_stats(name)
            if not any(
                int(stats.get(key, 0) or 0)
                for key in ("document_count", "chunk_count", "image_count", "total_documents", "total_chunks", "total_images")
            ):
                continue
            result.append({"name": name, **stats})
        except Exception:
            result.append({"name": name})
    return {"collections": result}


@router.get("/{name}/stats")
async def collection_stats(name: str):
    ds = get_data_service()
    return ds.get_collection_stats(name)
