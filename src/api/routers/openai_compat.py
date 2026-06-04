"""OpenAI-compatible chat completion endpoints."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.dependencies import get_settings
from src.api.routers.query import QueryRequest, run_rag_query

router = APIRouter()


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"] | str
    content: str | list[Any] | None = ""


class ChatCompletionRequest(BaseModel):
    model: str = "final-review-rag"
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    top_k: int = 5
    collection: str = "default"
    enable_rerank: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


def _message_text(content: str | list[Any] | None) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict):
            if item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            elif "text" in item:
                parts.append(str(item.get("text", "")))
        else:
            parts.append(str(item))
    return "\n".join(part for part in parts if part).strip()


def _last_user_message(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return _message_text(message.content)
    return _message_text(messages[-1].content) if messages else ""


def _collection_from_request(req: ChatCompletionRequest) -> str:
    value = req.metadata.get("collection") if isinstance(req.metadata, dict) else None
    return str(value or req.collection or "default")


def _chunk(content: str, model: str, chunk_id: str | None = None, finish_reason: str | None = None) -> dict:
    return {
        "id": chunk_id or f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"content": content} if content else {},
                "finish_reason": finish_reason,
            }
        ],
    }


def _sse_data(data: dict | str) -> str:
    if isinstance(data, str):
        return f"data: {data}\n\n"
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/models")
async def list_models():
    settings = get_settings()
    return {
        "object": "list",
        "data": [
            {
                "id": "final-review-rag",
                "object": "model",
                "created": 0,
                "owned_by": "final-review-helper",
            },
            {
                "id": settings.llm.model,
                "object": "model",
                "created": 0,
                "owned_by": settings.llm.provider,
            },
        ],
    }


@router.post("/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    query = _last_user_message(req.messages).strip()
    if not query:
        return {
            "error": {
                "message": "messages must contain a non-empty user message",
                "type": "invalid_request_error",
            }
        }

    async def run() -> dict:
        return await run_rag_query(
            QueryRequest(
                query=query,
                collection=_collection_from_request(req),
                top_k=req.top_k,
                enable_rerank=req.enable_rerank,
            )
        )

    if req.stream:
        async def event_stream():
            chunk_id = f"chatcmpl-{uuid.uuid4().hex}"
            yield _sse_data(_chunk("", req.model, chunk_id=chunk_id))
            try:
                result = await run()
                content = str(result.get("answer") or "")
                yield _sse_data(_chunk(content, req.model, chunk_id=chunk_id))
                yield _sse_data({
                    **_chunk("", req.model, chunk_id=chunk_id, finish_reason="stop"),
                    "citations": result.get("citations", []),
                    "metadata": result.get("metadata", {}),
                })
            except Exception as exc:
                yield _sse_data({
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": req.model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "error"}],
                    "error": str(exc),
                })
            yield _sse_data("[DONE]")

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    result = await run()
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    content = str(result.get("answer") or "")
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "citations": result.get("citations", []),
        "metadata": result.get("metadata", {}),
    }
