"""Monitoring router — traces, config, evaluation."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from src.api.dependencies import get_config_service, get_trace_service
from src.api.collection_names import storage_collection

router = APIRouter()


@router.get("/traces")
async def list_traces(trace_type: Optional[str] = None, limit: int = 100):
    ts = get_trace_service()
    traces = ts.list_traces(trace_type=trace_type, limit=limit)
    if trace_type == "ingestion":
        traces = _merge_ingestion_document_traces(traces, limit)
    return {"traces": traces}


def _merge_ingestion_document_traces(existing: list[dict], limit: int) -> list[dict]:
    """Show historical uploaded documents even if older runs did not write traces."""
    try:
        from src.api.dependencies import get_data_service

        ds = get_data_service()
        known_doc_ids = {
            str(trace.get("metadata", {}).get("doc_id") or "")
            for trace in existing
        }
        synthetic: list[dict] = []
        for collection in ds.list_collections():
            for doc in ds.list_documents(collection):
                doc_id = str(doc.get("source_hash") or "")
                if not doc_id or doc_id in known_doc_ids:
                    continue
                synthetic.append({
                    "trace_id": f"document-{doc_id}",
                    "trace_type": "ingestion",
                    "started_at": doc.get("processed_at") or "",
                    "finished_at": doc.get("processed_at") or "",
                    "total_elapsed_ms": 0,
                    "stages": [
                        {
                            "stage": "uploaded",
                            "timestamp": doc.get("processed_at") or "",
                            "elapsed_ms": 0,
                            "data": {
                                "collection": collection,
                                "file_path": doc.get("source_path", ""),
                                "chunk_count": doc.get("chunk_count", 0),
                                "image_count": doc.get("image_count", 0),
                                "historical": True,
                            },
                        }
                    ],
                    "metadata": {
                        "collection": collection,
                        "file_path": doc.get("source_path", ""),
                        "file_name": str(doc.get("source_path", "")).split("\\")[-1].split("/")[-1],
                        "doc_id": doc_id,
                        "chunk_count": doc.get("chunk_count", 0),
                        "image_count": doc.get("image_count", 0),
                        "success": True,
                        "historical": True,
                    },
                })
        traces = [*existing, *synthetic]
        traces.sort(key=lambda item: item.get("started_at", ""), reverse=True)
        return traces[:limit]
    except Exception:
        return existing


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

        collection = storage_collection(req.collection)
        settings = get_settings()
        embedding_client = EmbeddingFactory.create(settings)
        vector_store = VectorStoreFactory.create(settings, collection_name=collection)
        bm25 = BM25Indexer(index_dir=str(resolve_path(f"data/db/bm25/{collection}")))

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
        result = asyncio.run(runner.run(top_k=req.top_k, collection=collection))

        return {"result": result}
    except Exception as exc:
        return {"error": str(exc)}
