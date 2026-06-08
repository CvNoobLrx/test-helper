"""Runtime warmup and lightweight benchmark endpoints."""

from __future__ import annotations

import time

from fastapi import APIRouter
from pydantic import BaseModel

from src.api.collection_names import storage_collection
from src.api.dependencies import get_settings
from src.api.runtime_state import runtime_state, utc_now

router = APIRouter()


class WarmupRequest(BaseModel):
    collection: str = "default"
    include_llm: bool = False


class BenchmarkRequest(BaseModel):
    query: str = "这门课有哪些高频考点？"
    collection: str = "default"
    top_k: int = 5
    enable_rerank: bool = False


def _component(name: str, status: str, elapsed_ms: float, extra: dict | None = None) -> dict:
    return {
        "name": name,
        "status": status,
        "elapsed_ms": round(elapsed_ms, 2),
        **(extra or {}),
    }


@router.get("/status")
async def get_runtime_status():
    return runtime_state.to_dict()


@router.post("/warmup")
async def warmup(req: WarmupRequest):
    settings = get_settings()
    collection = storage_collection(req.collection)
    runtime_state.warmup_started_at = utc_now()
    started = time.monotonic()
    components: dict[str, dict] = {}

    t0 = time.monotonic()
    try:
        from src.libs.embedding.embedding_factory import EmbeddingFactory

        embedder = EmbeddingFactory.create(settings)
        # A tiny query initializes tokenizer/model without doing expensive indexing.
        vector = embedder.embed(["warmup"], input_type="query")[0]
        components["embedding"] = _component(
            "embedding",
            "ready",
            (time.monotonic() - t0) * 1000,
            {"provider": settings.embedding.provider, "model": settings.embedding.model, "dimensions": len(vector)},
        )
    except Exception as exc:
        components["embedding"] = _component("embedding", "error", (time.monotonic() - t0) * 1000, {"error": str(exc)})

    t0 = time.monotonic()
    try:
        from src.libs.vector_store.vector_store_factory import VectorStoreFactory

        vector_store = VectorStoreFactory.create(settings, collection_name=collection)
        count = getattr(vector_store, "collection", None).count() if hasattr(vector_store, "collection") else None
        components["vector_store"] = _component(
            "vector_store",
            "ready",
            (time.monotonic() - t0) * 1000,
            {"provider": settings.vector_store.provider, "collection": collection, "count": count},
        )
    except Exception as exc:
        components["vector_store"] = _component("vector_store", "error", (time.monotonic() - t0) * 1000, {"error": str(exc)})

    t0 = time.monotonic()
    try:
        from src.core.settings import resolve_path
        from src.ingestion.storage.bm25_indexer import BM25Indexer

        bm25 = BM25Indexer(index_dir=str(resolve_path(f"data/db/bm25/{collection}")))
        loaded = bm25.load(collection)
        stats = getattr(bm25, "_metadata", {}) if loaded else {}
        components["bm25"] = _component(
            "bm25",
            "ready" if loaded else "missing",
            (time.monotonic() - t0) * 1000,
            {"collection": collection, "stats": stats},
        )
    except Exception as exc:
        components["bm25"] = _component("bm25", "error", (time.monotonic() - t0) * 1000, {"error": str(exc)})

    if req.include_llm:
        t0 = time.monotonic()
        try:
            from src.libs.llm import LLMFactory

            LLMFactory.create(settings)
            components["llm"] = _component(
                "llm",
                "ready",
                (time.monotonic() - t0) * 1000,
                {"provider": settings.llm.provider, "model": settings.llm.model},
            )
        except Exception as exc:
            components["llm"] = _component("llm", "error", (time.monotonic() - t0) * 1000, {"error": str(exc)})

    runtime_state.components = components
    runtime_state.warmed = all(item.get("status") == "ready" for item in components.values())
    runtime_state.warmup_finished_at = utc_now()
    runtime_state.warmup_elapsed_ms = round((time.monotonic() - started) * 1000, 2)
    return runtime_state.to_dict()


@router.post("/benchmark")
async def benchmark(req: BenchmarkRequest):
    from src.api.routers.query import QueryRequest, run_rag_query

    started = time.monotonic()
    result = await run_rag_query(
        QueryRequest(
            query=req.query,
            collection=req.collection,
            top_k=req.top_k,
            enable_rerank=req.enable_rerank,
        )
    )
    elapsed_ms = round((time.monotonic() - started) * 1000, 2)
    benchmark_result = {
        "query": req.query,
        "collection": storage_collection(req.collection),
        "top_k": req.top_k,
        "enable_rerank": req.enable_rerank,
        "elapsed_ms": elapsed_ms,
        "citation_count": len(result.get("citations", [])),
        "answer_mode": (result.get("metadata") or {}).get("answer_mode", ""),
    }
    runtime_state.last_benchmark = benchmark_result
    return benchmark_result
