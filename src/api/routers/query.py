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
            {
                "index": c.get("index", i + 1),
                "source": c.get("source", ""),
                "score": c.get("score", 0),
                "text_snippet": c.get("text", "")[:200],
            }
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
                    {
                        "index": c.get("index", i + 1),
                        "source": c.get("source", ""),
                        "score": c.get("score", 0),
                        "text_snippet": c.get("text", "")[:200],
                    }
                    for i, c in enumerate(response.citations)
                ],
                "metadata": response.metadata,
                "is_empty": response.is_empty,
            })
        except Exception as exc:
            yield sse_event("error", {"error": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
