"""Learning router — mastery, knowledge points, quiz, review."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from src.api.dependencies import get_settings

router = APIRouter()


class QuizRequest(BaseModel):
    collection: str = "default"
    num_questions: int = 5
    difficulty: str = "medium"


class ReviewSubmitRequest(BaseModel):
    collection: str = "default"
    knowledge_point_id: str
    quality: int  # 0-5 SM-2 quality rating


def _get_mastery_store(collection: str):
    from src.core.settings import resolve_path
    from src.api.dependencies import get_settings
    from src.ingestion.storage.mastery_store import MasteryStore

    settings = get_settings()
    data_dir = settings.mastery.data_dir if settings.mastery else "data/db/mastery"
    return MasteryStore(data_dir=str(resolve_path(data_dir)))


def _get_kp_index(collection: str):
    from src.core.settings import resolve_path
    from src.ingestion.storage.knowledge_point_index import KnowledgePointIndex
    return KnowledgePointIndex(index_dir=str(resolve_path("data/db/knowledge_points")))


@router.get("/mastery")
async def get_mastery(collection: str = "default"):
    store = _get_mastery_store(collection)
    stats = store.get_stats(collection)
    return {"collection": collection, "stats": stats}


@router.get("/knowledge-points")
async def list_knowledge_points(collection: str = "default"):
    idx = _get_kp_index(collection)
    return {"knowledge_points": idx.get_by_collection(collection)}


@router.get("/review-plan")
async def get_review_plan(collection: str = "default", max_items: int = 10):
    store = _get_mastery_store(collection)
    due = store.get_due_items(collection)[:max_items]
    from dataclasses import asdict
    return {"review_items": [asdict(item) for item in due]}


@router.post("/quiz/generate")
async def generate_quiz(req: QuizRequest):
    idx = _get_kp_index(req.collection)
    kps = idx.get_by_collection(req.collection)
    if not kps:
        return {"questions": [], "error": "No knowledge points found"}

    from src.core.settings import resolve_path
    prompt_path = resolve_path("config/prompts/quiz_generation.txt")
    prompt_template = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""

    kp_text = "\n".join(f"- {kp.content}" for kp in kps[:20])
    prompt = prompt_template.replace("{{knowledge_points}}", kp_text)
    prompt = prompt.replace("{{num_questions}}", str(req.num_questions))
    prompt = prompt.replace("{{difficulty}}", req.difficulty)

    try:
        from src.libs.llm.llm_factory import LLMFactory
        settings = get_settings()
        llm = LLMFactory.create(settings)
        import asyncio
        response = asyncio.run(llm.generate(prompt))

        import json
        questions = json.loads(response)
        return {"questions": questions}
    except Exception as exc:
        return {"questions": [], "error": str(exc)}


@router.post("/review/submit")
async def submit_review(req: ReviewSubmitRequest):
    store = _get_mastery_store(req.collection)
    from src.core.types import MasteryRecord
    from src.ingestion.storage.spaced_repetition import calculate_next_review

    existing = store.get_record(req.knowledge_point_id, req.collection)
    if existing is None:
        existing = MasteryRecord(
            knowledge_point_id=req.knowledge_point_id,
            collection=req.collection,
        )

    settings = get_settings()
    min_ease_factor = settings.mastery.min_ease_factor if settings.mastery else 1.3
    updated = calculate_next_review(
        req.quality,
        existing,
        min_ease_factor=min_ease_factor,
    )
    store.update_record(updated)

    return {"success": True}


@router.get("/stats")
async def get_stats(collection: str = "default"):
    store = _get_mastery_store(collection)
    stats = store.get_stats(collection)
    return {"collection": collection, **stats}
