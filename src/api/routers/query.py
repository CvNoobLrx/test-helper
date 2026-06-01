"""Query router — RAG query with SSE streaming."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.dependencies import get_settings
from src.api.streaming import sse_event

router = APIRouter()


class QueryRequest(BaseModel):
    query: str
    collection: str = "default"
    top_k: int = 5
    enable_rerank: bool = True


def _citation_to_dict(citation, index: int) -> dict:
    if hasattr(citation, "to_dict"):
        data = citation.to_dict()
    elif isinstance(citation, dict):
        data = citation
    else:
        data = {
            "index": getattr(citation, "index", index + 1),
            "source": getattr(citation, "source", ""),
            "score": getattr(citation, "score", 0),
            "text_snippet": getattr(citation, "text_snippet", ""),
        }

    return {
        "index": data.get("index", index + 1),
        "source": data.get("source", ""),
        "score": data.get("score", 0),
        "text_snippet": data.get("text_snippet", data.get("text", ""))[:200],
        **({"page": data["page"]} if data.get("page") is not None else {}),
    }


@router.post("")
async def query_knowledge(req: QueryRequest):
    """Non-streaming RAG query."""
    from src.mcp_server.tools.query_knowledge_hub import QueryKnowledgeHubTool

    settings = get_settings()
    tool = QueryKnowledgeHubTool(settings=settings)
    tool.config.enable_rerank = req.enable_rerank

    response = await tool.execute(
        query=req.query,
        top_k=req.top_k,
        collection=req.collection,
    )

    return {
        "answer": response.content,
        "citations": [
            _citation_to_dict(c, i)
            for i, c in enumerate(response.citations)
        ],
        "metadata": response.metadata,
        "is_empty": response.is_empty,
    }


@router.post("/stream")
async def query_stream(req: QueryRequest):
    """SSE streaming RAG query."""
    from src.mcp_server.tools.query_knowledge_hub import QueryKnowledgeHubTool

    def event_stream():
        try:
            settings = get_settings()
            tool = QueryKnowledgeHubTool(settings=settings)
            tool.config.enable_rerank = req.enable_rerank

            yield sse_event("stage", {"stage": "searching", "message": "Searching knowledge base..."})

            import asyncio
            response = asyncio.run(tool.execute(
                query=req.query,
                top_k=req.top_k,
                collection=req.collection,
            ))

            yield sse_event("stage", {"stage": "complete", "message": "Search complete"})

            yield sse_event("token", {"text": response.content})

            yield sse_event("done", {
                "citations": [
                    _citation_to_dict(c, i)
                    for i, c in enumerate(response.citations)
                ],
                "metadata": response.metadata,
                "is_empty": response.is_empty,
            })
        except Exception as exc:
            yield sse_event("error", {"error": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
