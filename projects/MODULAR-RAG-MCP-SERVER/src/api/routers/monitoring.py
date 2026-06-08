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
    traces = [_present_trace(trace) for trace in traces]
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
    trace = _present_trace(trace)
    timings = ts.get_stage_timings(trace)
    return {"trace": trace, "stage_timings": timings}


def _present_trace(trace: dict) -> dict:
    if trace.get("trace_type") != "ingestion":
        return trace
    return _summarize_ingestion_trace(trace)


def _stage_payload(stage: dict | None) -> dict:
    data = (stage or {}).get("data") or {}
    return data if isinstance(data, dict) else {}


def _first_stage(stages: list[dict], names: set[str]) -> dict | None:
    for stage in stages:
        if stage.get("stage") in names:
            return stage
    return None


def _last_stage(stages: list[dict], names: set[str]) -> dict | None:
    for stage in reversed(stages):
        if stage.get("stage") in names:
            return stage
    return None


def _elapsed(stage: dict | None) -> float:
    value = (stage or {}).get("elapsed_ms", 0)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _summarize_ingestion_trace(trace: dict) -> dict:
    """Collapse noisy ingestion internals into user-facing pipeline stages."""
    stages = trace.get("stages") or []
    if not isinstance(stages, list):
        stages = []
    metadata = trace.get("metadata") or {}
    if metadata.get("historical"):
        return trace

    load = _last_stage(stages, {"load", "document_loading"})
    split = _last_stage(stages, {"split", "chunking"})
    transform = _last_stage(stages, {"transform"})
    embed = _last_stage(stages, {"embed", "encoding"})
    upsert = _last_stage(stages, {"upsert", "storage"})
    batch = _last_stage(stages, {"batch_processing"})

    load_data = _stage_payload(load)
    split_data = _stage_payload(split)
    transform_data = _stage_payload(transform)
    embed_data = _stage_payload(embed)
    upsert_data = _stage_payload(upsert)
    batch_data = _stage_payload(batch)

    main_stages = [
        {
            "stage": "load",
            "label": "读取资料",
            "status": "completed" if load else "pending",
            "timestamp": (load or {}).get("timestamp", ""),
            "elapsed_ms": _elapsed(load),
            "summary": f"{load_data.get('text_length', 0)} 字，{load_data.get('image_count', metadata.get('image_count', 0))} 张图片",
            "data": {
                "doc_id": load_data.get("doc_id") or metadata.get("doc_id", ""),
                "text_length": load_data.get("text_length", 0),
                "image_count": load_data.get("image_count", metadata.get("image_count", 0)),
            },
        },
        {
            "stage": "split",
            "label": "切分片段",
            "status": "completed" if split else "pending",
            "timestamp": (split or {}).get("timestamp", ""),
            "elapsed_ms": _elapsed(split),
            "summary": f"{split_data.get('chunk_count', metadata.get('chunk_count', 0))} 个片段",
            "data": {
                "chunk_count": split_data.get("chunk_count", metadata.get("chunk_count", 0)),
                "avg_chunk_size": split_data.get("avg_chunk_size", 0),
            },
        },
        {
            "stage": "transform",
            "label": "整理与抽取",
            "status": "completed" if transform else "pending",
            "timestamp": (transform or {}).get("timestamp", ""),
            "elapsed_ms": _elapsed(transform),
            "summary": _transform_summary(transform_data),
            "data": {
                "refined_by_llm": transform_data.get("refined_by_llm", 0),
                "refined_by_rule": transform_data.get("refined_by_rule", 0),
                "enriched_by_llm": transform_data.get("enriched_by_llm", 0),
                "enriched_by_rule": transform_data.get("enriched_by_rule", 0),
                "captioned_chunks": transform_data.get("captioned_chunks", 0),
            },
        },
        {
            "stage": "embed",
            "label": "生成向量",
            "status": "completed" if embed or batch else "pending",
            "timestamp": (embed or batch or {}).get("timestamp", ""),
            "elapsed_ms": _elapsed(embed) or float(batch_data.get("total_time_seconds", 0) or 0) * 1000,
            "summary": f"{embed_data.get('dense_vector_count', batch_data.get('successful_chunks', 0))} 个向量",
            "data": {
                "dense_vector_count": embed_data.get("dense_vector_count", batch_data.get("successful_chunks", 0)),
                "dense_dimension": embed_data.get("dense_dimension", 0),
                "failed_chunks": batch_data.get("failed_chunks", 0),
            },
        },
        {
            "stage": "upsert",
            "label": "写入资料库",
            "status": "completed" if upsert else "pending",
            "timestamp": (upsert or {}).get("timestamp", ""),
            "elapsed_ms": _elapsed(upsert),
            "summary": _storage_summary(upsert_data, metadata),
            "data": {
                "vector_count": (upsert_data.get("dense_store") or {}).get("count", metadata.get("chunk_count", 0)),
                "image_count": (upsert_data.get("image_store") or {}).get("count", metadata.get("image_count", 0)),
                "collection": metadata.get("collection", ""),
            },
        },
    ]

    presented = dict(trace)
    presented["raw_stage_count"] = len(stages)
    presented["stages"] = [stage for stage in main_stages if stage["status"] == "completed"]
    if not presented["stages"] and stages:
        fallback = _first_stage(stages, {str(stages[0].get("stage", ""))})
        presented["stages"] = [{
            "stage": fallback.get("stage", "ingestion"),
            "label": "处理资料",
            "status": "completed",
            "timestamp": fallback.get("timestamp", ""),
            "elapsed_ms": _elapsed(fallback),
            "summary": "已完成",
            "data": _stage_payload(fallback),
        }]
    return presented


def _transform_summary(data: dict) -> str:
    refined = int(data.get("refined_by_llm", 0) or 0) + int(data.get("refined_by_rule", 0) or 0)
    enriched = int(data.get("enriched_by_llm", 0) or 0) + int(data.get("enriched_by_rule", 0) or 0)
    captioned = int(data.get("captioned_chunks", 0) or 0)
    parts = []
    if refined:
        parts.append(f"整理 {refined} 个片段")
    if enriched:
        parts.append(f"补充摘要 {enriched} 个片段")
    if captioned:
        parts.append(f"图片说明 {captioned} 处")
    return "，".join(parts) or "内容整理完成"


def _storage_summary(data: dict, metadata: dict) -> str:
    vector_count = (data.get("dense_store") or {}).get("count", metadata.get("chunk_count", 0))
    image_count = (data.get("image_store") or {}).get("count", metadata.get("image_count", 0))
    return f"{vector_count} 个片段，{image_count} 张图片"


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
