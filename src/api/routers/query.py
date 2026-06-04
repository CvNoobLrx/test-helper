"""Query router — RAG query with SSE streaming."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.dependencies import get_settings
from src.api.collection_names import storage_collection
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
        "chunk_id": data.get("chunk_id", ""),
        "source": data.get("source", ""),
        "score": data.get("score", 0),
        "text_snippet": data.get("text_snippet", data.get("text", ""))[:200],
        **({"page": data["page"]} if data.get("page") is not None else {}),
    }


def _build_context(citations: list[dict], max_chars: int = 6000) -> str:
    parts = []
    used = 0
    for citation in citations:
        snippet = (citation.get("text_snippet") or "").strip()
        if not snippet:
            continue
        source = citation.get("source") or "unknown"
        page = f", page {citation['page']}" if citation.get("page") is not None else ""
        block = f"[{citation.get('index')}], source: {source}{page}\n{snippet}"
        if used + len(block) > max_chars:
            break
        used += len(block)
        parts.append(block)
    return "\n\n".join(parts)


def _generate_answer(query: str, citations: list[dict], fallback: str) -> tuple[str, dict]:
    if not citations:
        return fallback, {"answer_mode": "empty"}

    context = _build_context(citations)
    if not context:
        return fallback, {"answer_mode": "retrieval"}

    try:
        from src.libs.llm import LLMFactory, Message

        settings = get_settings()
        llm = LLMFactory.create(settings)
        prompt = f"""你是期末复习助手。请只根据下面的资料片段回答用户问题。

要求：
- 先判断资料是否足以回答问题。
- 如果问题与资料库无关，或资料中没有依据，请直接说明“资料库中没有找到相关依据”，不要硬凑答案。
- 如果可以回答，请用自然、简洁的中文总结，不要照搬大段原文。
- 关键结论后标注引用编号，如 [1]、[2]。
- 最后给出“可继续复习的问题”2-3 个。

用户问题：
{query}

资料片段：
{context}
"""
        response = llm.chat(
            [Message(role="user", content=prompt)],
            temperature=0.0,
            max_tokens=900,
        )
        content = response.content.strip()
        if content:
            return content, {"answer_mode": "llm"}
    except Exception as exc:
        return fallback, {"answer_mode": "retrieval_fallback", "answer_error": str(exc)}

    return fallback, {"answer_mode": "retrieval_fallback"}


@router.post("")
async def query_knowledge(req: QueryRequest):
    """Non-streaming RAG query."""
    from src.mcp_server.tools.query_knowledge_hub import QueryKnowledgeHubTool

    collection = storage_collection(req.collection)
    settings = get_settings()
    tool = QueryKnowledgeHubTool(settings=settings)
    tool.config.enable_rerank = req.enable_rerank

    response = await tool.execute(
        query=req.query,
        top_k=req.top_k,
        collection=collection,
    )
    citations = [_citation_to_dict(c, i) for i, c in enumerate(response.citations)]
    answer, answer_meta = _generate_answer(req.query, citations, response.content)

    return {
        "answer": answer,
        "citations": citations,
        "metadata": {**response.metadata, **answer_meta},
        "is_empty": response.is_empty,
    }


@router.post("/stream")
async def query_stream(req: QueryRequest):
    """SSE streaming RAG query."""
    from src.mcp_server.tools.query_knowledge_hub import QueryKnowledgeHubTool

    def event_stream():
        try:
            collection = storage_collection(req.collection)
            settings = get_settings()
            tool = QueryKnowledgeHubTool(settings=settings)
            tool.config.enable_rerank = req.enable_rerank

            yield sse_event("stage", {"stage": "searching", "message": "Searching knowledge base..."})

            import asyncio
            response = asyncio.run(tool.execute(
                query=req.query,
                top_k=req.top_k,
                collection=collection,
            ))

            citations = [_citation_to_dict(c, i) for i, c in enumerate(response.citations)]

            yield sse_event("stage", {"stage": "generating", "message": "Generating answer..."})
            answer, answer_meta = _generate_answer(req.query, citations, response.content)

            yield sse_event("stage", {"stage": "complete", "message": "Answer complete"})

            yield sse_event("token", {"text": answer})

            yield sse_event("done", {
                "citations": citations,
                "metadata": {**response.metadata, **answer_meta},
                "is_empty": response.is_empty,
            })
        except Exception as exc:
            yield sse_event("error", {"error": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
