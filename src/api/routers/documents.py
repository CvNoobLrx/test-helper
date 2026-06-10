"""Documents router — CRUD, upload with ingestion, SSE progress."""

from __future__ import annotations

from pathlib import Path
from queue import Queue
from threading import Thread
from typing import Optional
import mimetypes

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from src.api.dependencies import get_data_service, get_settings
from src.api.collection_names import storage_collection
from src.api.streaming import sse_event
from src.core.settings import resolve_path

router = APIRouter()


class DocumentEnabledRequest(BaseModel):
    enabled: bool


def _document_or_404(doc_id: str, collection: str) -> dict:
    ds = get_data_service()
    detail = ds.get_document_detail(doc_id, collection)
    if detail is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return detail


def _filename_from_path(source_path: str) -> str:
    return Path(source_path).name or "document"


@router.get("")
async def list_documents(collection: Optional[str] = None):
    ds = get_data_service()
    collection = storage_collection(collection or "default")
    return {"documents": ds.list_documents(collection)}


@router.get("/{doc_id}")
async def get_document(doc_id: str, collection: Optional[str] = None):
    ds = get_data_service()
    collection = storage_collection(collection or "default")
    detail = ds.get_document_detail(doc_id, collection)
    if detail is None:
        return {"error": "Document not found"}
    return detail


@router.get("/{doc_id}/chunks")
async def get_document_chunks(doc_id: str, collection: Optional[str] = None):
    ds = get_data_service()
    collection = storage_collection(collection or "default")
    return {"chunks": ds.get_chunks(doc_id, collection)}


@router.get("/{doc_id}/images")
async def get_document_images(doc_id: str, collection: Optional[str] = None):
    ds = get_data_service()
    collection = storage_collection(collection or "default")
    return {"images": ds.get_images(doc_id, collection)}


@router.get("/{doc_id}/preview")
async def get_document_preview(doc_id: str, collection: Optional[str] = None):
    ds = get_data_service()
    collection = storage_collection(collection or "default")
    detail = _document_or_404(doc_id, collection)
    source_path = str(detail.get("source_path") or "")
    filename = _filename_from_path(source_path)
    chunks = ds.get_chunks(doc_id, collection)

    def chunk_order(chunk: dict) -> int:
        metadata = chunk.get("metadata") or {}
        try:
            return int(metadata.get("chunk_index", 0))
        except (TypeError, ValueError):
            return 0

    markdown_parts = [
        str(chunk.get("text") or "").strip()
        for chunk in sorted(chunks, key=chunk_order)
        if str(chunk.get("text") or "").strip()
    ]

    return {
        "doc_id": doc_id,
        "filename": filename,
        "source_path": source_path,
        "extension": Path(filename).suffix.lower(),
        "original_url": f"/api/documents/{doc_id}/original?collection={collection}",
        "markdown": "\n\n---\n\n".join(markdown_parts),
    }


@router.get("/{doc_id}/original")
async def get_document_original(doc_id: str, collection: Optional[str] = None):
    collection = storage_collection(collection or "default")
    detail = _document_or_404(doc_id, collection)
    source_path = Path(str(detail.get("source_path") or ""))
    if not source_path.exists() or not source_path.is_file():
        raise HTTPException(status_code=404, detail="Original file not found")

    media_type = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
    return FileResponse(
        source_path,
        media_type=media_type,
        filename=source_path.name,
        content_disposition_type="inline",
    )


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, collection: str = "default"):
    ds = get_data_service()
    collection = storage_collection(collection)
    chunks = ds.get_chunks(doc_id, collection)
    chunk_ids = [chunk.get("id") for chunk in chunks if chunk.get("id")]
    result = ds.delete_document(doc_id, collection, source_hash=doc_id)
    removed_kps: list[str] = []
    mastery_removed = 0
    graph_removed = False
    if chunk_ids:
        try:
            from src.ingestion.storage.knowledge_point_index import KnowledgePointIndex
            from src.ingestion.storage.mastery_store import MasteryStore

            settings = get_settings()
            kp_index = KnowledgePointIndex(index_dir=str(resolve_path("data/db/knowledge_points")))
            removed_kps = kp_index.remove_by_chunks(chunk_ids, collection)
            data_dir = settings.mastery.data_dir if settings.mastery else "data/db/mastery"
            mastery = MasteryStore(data_dir=str(resolve_path(data_dir)))
            mastery_removed = mastery.remove_records(removed_kps, collection)
        except Exception:
            removed_kps = []
            mastery_removed = 0
    try:
        from src.ingestion.storage.graph_index import GraphIndex

        graph_index = GraphIndex(db_path=str(resolve_path("data/db/graph/graph_index.db")))
        graph_index.remove_document(collection, doc_id)
        graph_removed = True
    except Exception:
        graph_removed = False
    if hasattr(result, "__dict__"):
        from dataclasses import asdict
        payload = asdict(result)
        payload["knowledge_points_deleted"] = len(removed_kps)
        payload["mastery_records_deleted"] = mastery_removed
        payload["graph_removed"] = graph_removed
        return payload
    return {
        "deleted": True,
        "knowledge_points_deleted": len(removed_kps),
        "mastery_records_deleted": mastery_removed,
        "graph_removed": graph_removed,
    }


@router.post("/{doc_id}/enabled")
async def set_document_enabled(
    doc_id: str,
    payload: DocumentEnabledRequest,
    collection: str = "default",
):
    ds = get_data_service()
    collection = storage_collection(collection)
    documents = ds.list_documents(collection)
    if not any(doc.get("source_hash") == doc_id for doc in documents):
        raise HTTPException(status_code=404, detail="Document not found")

    updated = ds.set_document_enabled(doc_id, payload.enabled, collection)
    if not updated:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "source_hash": doc_id,
        "collection": collection,
        "enabled": payload.enabled,
    }


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    collection: str = Form("default"),
):
    """Upload a file and run ingestion. Returns SSE stream of progress events."""
    collection = storage_collection(collection)
    suffix = Path(file.filename).suffix
    original_name = Path(file.filename or f"upload{suffix}").name
    safe_name = "".join(ch if ch.isalnum() or ch in "._- ()[]" else "_" for ch in original_name)
    if not safe_name:
        safe_name = f"upload{suffix or '.dat'}"
    upload_dir = resolve_path(f"data/uploads/{collection}")
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path = upload_dir / safe_name
    try:
        content = await file.read()
        upload_path.write_bytes(content)
        file_path = str(upload_path)

        def event_stream():
            events: Queue[tuple[str, object]] = Queue()

            def run_pipeline() -> None:
                try:
                    def on_progress(stage_name: str, current: int, total: int):
                        events.put(("progress", {"stage": stage_name, "current": current, "total": total}))

                    from src.core.trace.trace_context import TraceContext
                    from src.ingestion.pipeline import IngestionPipeline
                    from src.observability.logger import write_trace

                    settings = get_settings()
                    pipeline = IngestionPipeline(settings, collection=collection)
                    trace = TraceContext(
                        trace_type="ingestion",
                        metadata={
                            "collection": collection,
                            "file_path": file_path,
                            "file_name": safe_name,
                        },
                    )

                    result = pipeline.run(file_path, trace=trace, on_progress=on_progress)
                    trace.metadata.update({
                        "success": result.success,
                        "doc_id": result.doc_id,
                        "chunk_count": result.chunk_count,
                        "image_count": result.image_count,
                        "error": result.error,
                    })
                    trace.finish()
                    write_trace(trace.to_dict())
                    events.put(("complete", result.to_dict()))
                except Exception as exc:
                    try:
                        trace.metadata.update({"success": False, "error": str(exc)})
                        trace.finish()
                        write_trace(trace.to_dict())
                    except Exception:
                        pass
                    events.put(("error", {"error": str(exc)}))

            worker = Thread(target=run_pipeline, daemon=True)
            worker.start()

            while True:
                event, payload = events.get()
                yield sse_event(event, payload)
                if event in {"complete", "error"}:
                    break

        return StreamingResponse(event_stream(), media_type="text/event-stream")
    except Exception as exc:
        return {"error": str(exc)}
