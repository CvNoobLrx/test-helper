"""Monitoring router — traces, config, evaluation."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from src.api.dependencies import get_config_service, get_trace_service

router = APIRouter()


@router.get("/traces")
async def list_traces(trace_type: Optional[str] = None, limit: int = 100):
    ts = get_trace_service()
    traces = ts.list_traces(trace_type=trace_type, limit=limit)
    return {"traces": traces}


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str):
    ts = get_trace_service()
    trace = ts.get_trace(trace_id)
    if trace is None:
        return {"error": "Trace not found"}
    timings = ts.get_stage_timings(trace)
    return {"trace": trace, "stage_timings": timings}


@router.get("/config")
async def get_config():
    cs = get_config_service()
    cards = cs.get_component_cards()
    from dataclasses import asdict
    return {"components": [asdict(c) for c in cards]}


class EvalRequest(BaseModel):
    collection: str = "default"
    top_k: int = 5


@router.post("/evaluation/run")
async def run_evaluation(req: EvalRequest):
    try:
        from src.observability.evaluation.eval_runner import EvalRunner
        from src.api.dependencies import get_settings
        from src.core.query_engine.hybrid_search import create_hybrid_search
        from src.core.query_engine.reranker import create_core_reranker
        from src.libs.embedding.embedding_factory import EmbeddingFactory
        from src.libs.vector_store.vector_store_factory import VectorStoreFactory
        from src.ingestion.storage.bm25_indexer import BM25Indexer
        from src.core.settings import resolve_path

        settings = get_settings()
        embedding_client = EmbeddingFactory.create(settings)
        vector_store = VectorStoreFactory.create(settings, collection_name=req.collection)
        bm25 = BM25Indexer(index_dir=str(resolve_path(f"data/db/bm25/{req.collection}")))

        from src.core.query_engine.dense_retriever import create_dense_retriever
        from src.core.query_engine.sparse_retriever import create_sparse_retriever
        from src.core.query_engine.query_processor import QueryProcessor

        dense = create_dense_retriever(settings=settings, embedding_client=embedding_client, vector_store=vector_store)
        sparse = create_sparse_retriever(settings=settings, bm25_indexer=bm25, vector_store=vector_store)
        hybrid = create_hybrid_search(
            settings=settings,
            query_processor=QueryProcessor(),
            dense_retriever=dense,
            sparse_retriever=sparse,
        )
        reranker = create_core_reranker(settings=settings)

        runner = EvalRunner(hybrid_search=hybrid, reranker=reranker, settings=settings)
        import asyncio
        result = asyncio.run(runner.run(top_k=req.top_k, collection=req.collection))

        return {"result": result}
    except Exception as exc:
        return {"error": str(exc)}
