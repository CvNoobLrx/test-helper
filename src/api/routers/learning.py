"""Learning router — mastery, knowledge points, quiz, review."""

from __future__ import annotations

import re
from typing import Dict, List, Optional

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


def _kp_text(kp: dict) -> str:
    return str(kp.get("text") or kp.get("content") or "").strip()


def _normalize_kp_text(text: str) -> str:
    return re.sub(r"[\s，。,.：:；;、“”\"'（）()【】\[\]-]+", "", text).lower()


def _infer_topic(kp: dict, text: str) -> str:
    topic = str(kp.get("topic") or "").strip()
    if topic:
        return topic
    category = str(kp.get("category") or "综合考点").strip()
    source = str(kp.get("source_ref") or "").split("/")[-1].split("\\")[-1]
    if source:
        return source.rsplit(".", 1)[0]
    return category or "综合考点"


def _infer_subtopic(kp: dict, text: str) -> str:
    subtopic = str(kp.get("subtopic") or "").strip()
    if subtopic:
        return subtopic
    return text[:24].rstrip("，。,.；;")


def _is_low_quality_kp(text: str) -> bool:
    if len(text) < 8 or len(text) > 140:
        return True
    compact = _normalize_kp_text(text)
    if len(compact) < 6 or len(set(compact)) <= 4:
        return True
    low_value = ("目录", "谢谢", "thank", "参考文献", "本章", "学习目标")
    return any(item in compact for item in low_value)


def _similar_key_exists(key: str, existing: Dict[str, dict]) -> str:
    for old_key in existing:
        if key == old_key:
            return old_key
        shorter, longer = sorted((key, old_key), key=len)
        if len(shorter) >= 10 and shorter in longer:
            return old_key
    return ""


def _dedupe_knowledge_points(kps: List[dict]) -> List[dict]:
    by_text: Dict[str, dict] = {}
    for kp in kps:
        text = _kp_text(kp)
        if _is_low_quality_kp(text):
            continue
        key = _normalize_kp_text(text)
        matched_key = _similar_key_exists(key, by_text)
        existing = by_text.get(matched_key or key)
        item = {
            **kp,
            "text": text,
            "content": text,
            "topic": _infer_topic(kp, text),
            "subtopic": _infer_subtopic(kp, text),
            "exam_focus": str(kp.get("exam_focus") or "可作为简答、辨析或材料分析题复习。").strip(),
        }
        if existing is None or int(kp.get("importance", 0) or 0) > int(existing.get("importance", 0) or 0):
            by_text[matched_key or key] = item
    return sorted(
        by_text.values(),
        key=lambda item: (str(item.get("topic", "")), -int(item.get("importance", 0) or 0)),
    )


def _sync_mastery_records(collection: str) -> None:
    idx = _get_kp_index(collection)
    store = _get_mastery_store(collection)
    from src.core.types import MasteryRecord

    for kp in _dedupe_knowledge_points(idx.get_by_collection(collection)):
        kp_id = kp.get("id")
        if kp_id and store.get_record(kp_id, collection) is None:
            store.update_record(MasteryRecord(knowledge_point_id=kp_id, collection=collection))


@router.get("/mastery")
async def get_mastery(collection: str = "default"):
    _sync_mastery_records(collection)
    store = _get_mastery_store(collection)
    stats = store.get_stats(collection)
    return {"collection": collection, "stats": stats}


@router.get("/knowledge-points")
async def list_knowledge_points(collection: str = "default"):
    idx = _get_kp_index(collection)
    kps = _dedupe_knowledge_points(idx.get_by_collection(collection))
    return {"knowledge_points": kps}


@router.get("/review-plan")
async def get_review_plan(collection: str = "default", max_items: int = 10):
    _sync_mastery_records(collection)
    store = _get_mastery_store(collection)
    idx = _get_kp_index(collection)
    kps_by_id = {
        kp.get("id"): kp
        for kp in _dedupe_knowledge_points(idx.get_by_collection(collection))
    }
    due = store.get_due_items(collection)[:max_items]
    from dataclasses import asdict
    review_items = []
    for item in due:
        data = asdict(item)
        kp = kps_by_id.get(item.knowledge_point_id, {})
        data["content"] = _kp_text(kp) or item.knowledge_point_id
        data["category"] = kp.get("category", "")
        data["importance"] = kp.get("importance", 0)
        data["source_ref"] = kp.get("source_ref", "")
        data["chunk_id"] = kp.get("chunk_id", "")
        review_items.append(data)
    return {"review_items": review_items}


@router.post("/quiz/generate")
async def generate_quiz(req: QuizRequest):
    idx = _get_kp_index(req.collection)
    kps = idx.get_by_collection(req.collection)
    if not kps:
        return {"questions": [], "error": "No knowledge points found"}

    from src.core.settings import resolve_path
    prompt_path = resolve_path("config/prompts/quiz_generation.txt")
    prompt_template = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""

    kps = _dedupe_knowledge_points(kps)
    kp_text = "\n".join(f"- {_kp_text(kp)}" for kp in kps[:20])
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
    _sync_mastery_records(collection)
    store = _get_mastery_store(collection)
    stats = store.get_stats(collection)
    return {"collection": collection, **stats}
