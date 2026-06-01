"""Documents router — CRUD, upload with ingestion, SSE progress."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import StreamingResponse

from src.api.dependencies import get_data_service, get_settings
from src.api.streaming import sse_event

router = APIRouter()


@router.get("")
async def list_documents(collection: Optional[str] = None):
    ds = get_data_service()
    return {"documents": ds.list_documents(collection)}


@router.get("/{doc_id}")
async def get_document(doc_id: str, collection: Optional[str] = None):
    ds = get_data_service()
    detail = ds.get_document_detail(doc_id, collection)
    if detail is None:
        return {"error": "Document not found"}
    return detail


@router.get("/{doc_id}/chunks")
async def get_document_chunks(doc_id: str, collection: Optional[str] = None):
    ds = get_data_service()
    return {"chunks": ds.get_chunks(doc_id, collection)}


@router.get("/{doc_id}/images")
async def get_document_images(doc_id: str, collection: Optional[str] = None):
    ds = get_data_service()
    return {"images": ds.get_images(doc_id, collection)}


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, collection: str = "default"):
    ds = get_data_service()
    result = ds.delete_document(doc_id, collection, source_hash=doc_id)
    if hasattr(result, "__dict__"):
        from dataclasses import asdict
        return asdict(result)
    return {"deleted": True}


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    collection: str = Form("default"),
):
    """Upload a file and run ingestion. Returns SSE stream of progress events."""
    suffix = Path(file.filename).suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        content = await file.read()
        tmp.write(content)
        tmp.flush()
        tmp.close()
        file_path = tmp.name

        def event_stream():
            stages = []
            def on_progress(stage_name: str, current: int, total: int):
                stages.append({"stage": stage_name, "current": current, "total": total})

            try:
                from src.ingestion.pipeline import IngestionPipeline
                settings = get_settings()
                pipeline = IngestionPipeline(settings, collection=collection)

                result = pipeline.run(file_path, on_progress=on_progress)

                for s in stages:
                    yield sse_event("progress", s)

                yield sse_event("complete", result.to_dict())
            except Exception as exc:
                yield sse_event("error", {"error": str(exc)})

        return StreamingResponse(event_stream(), media_type="text/event-stream")
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except Exception:
            pass
