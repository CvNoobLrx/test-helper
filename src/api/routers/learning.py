"""Learning router — mastery, knowledge points, quiz, review."""

from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from src.api.dependencies import get_settings
from src.api.collection_names import storage_collection

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


def _existing_content_refs(collection: str) -> tuple[set[str], set[str]]:
    try:
        from src.api.dependencies import get_data_service

        ds = get_data_service()
        docs = ds.list_documents(collection)
        chunk_ids: set[str] = set()
        source_refs: set[str] = set()
        for doc in docs:
            source_hash = doc.get("source_hash")
            if not source_hash:
                continue
            for chunk in ds.get_chunks(source_hash, collection):
                cid = chunk.get("id")
                if cid:
                    chunk_ids.add(cid)
                metadata = chunk.get("metadata") or {}
                source_ref = metadata.get("source_ref")
                if source_ref:
                    source_refs.add(str(source_ref))
        return chunk_ids, source_refs
    except Exception:
        return set(), set()


def _existing_chunk_ids(collection: str) -> set[str]:
    chunk_ids, _source_refs = _existing_content_refs(collection)
    return chunk_ids


def _filter_existing_knowledge_points(kps: List[dict], collection: str) -> List[dict]:
    existing_chunks, existing_sources = _existing_content_refs(collection)
    if not existing_chunks and not existing_sources:
        return []
    return [
        kp for kp in kps
        if kp.get("chunk_id") in existing_chunks
        or str(kp.get("source_ref") or "") in existing_sources
    ]


def _prioritize_knowledge_points(
    kps: List[dict],
    max_items: int = 60,
    max_per_topic: int = 8,
) -> List[dict]:
    """Keep the learning page focused on review-level points, not every fragment."""
    grouped: Dict[str, List[dict]] = {}
    for kp in kps:
        topic = str(kp.get("topic") or "综合考点").strip() or "综合考点"
        grouped.setdefault(topic, []).append(kp)

    selected: List[dict] = []
    for topic in sorted(grouped):
        items = sorted(
            grouped[topic],
            key=lambda item: (
                -int(item.get("importance", 0) or 0),
                len(_kp_text(item)),
            ),
        )
        selected.extend(items[:max_per_topic])

    return sorted(
        selected,
        key=lambda item: (
            str(item.get("topic", "")),
            -int(item.get("importance", 0) or 0),
            str(item.get("subtopic", "")),
        ),
    )[:max_items]


def _current_knowledge_points(collection: str) -> List[dict]:
    idx = _get_kp_index(collection)
    filtered = _filter_existing_knowledge_points(
        _dedupe_knowledge_points(idx.get_by_collection(collection)),
        collection,
    )
    return _prioritize_knowledge_points(filtered)


def _sync_mastery_records(collection: str) -> None:
    store = _get_mastery_store(collection)
    from src.core.types import MasteryRecord

    kps = _current_knowledge_points(collection)
    valid_ids = {kp.get("id") for kp in kps if kp.get("id")}
    stale_ids = [
        record.knowledge_point_id
        for record in store.get_all_records(collection)
        if record.knowledge_point_id not in valid_ids
    ]
    if stale_ids:
        store.remove_records(stale_ids, collection)

    for kp in kps:
        kp_id = kp.get("id")
        if kp_id and store.get_record(kp_id, collection) is None:
            store.update_record(MasteryRecord(knowledge_point_id=kp_id, collection=collection))


@router.get("/mastery")
async def get_mastery(collection: str = "default"):
    collection = storage_collection(collection)
    _sync_mastery_records(collection)
    store = _get_mastery_store(collection)
    stats = store.get_stats(collection)
    return {"collection": collection, "stats": stats}


@router.get("/knowledge-points")
async def list_knowledge_points(collection: str = "default"):
    collection = storage_collection(collection)
    kps = _current_knowledge_points(collection)
    return {"knowledge_points": kps}


@router.get("/review-plan")
async def get_review_plan(collection: str = "default", max_items: int = 10):
    collection = storage_collection(collection)
    _sync_mastery_records(collection)
    store = _get_mastery_store(collection)
    kps_by_id = {
        kp.get("id"): kp
        for kp in _current_knowledge_points(collection)
    }
    due = [
        item for item in store.get_due_items(collection)
        if item.knowledge_point_id in kps_by_id
    ][:max_items]
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
    collection = storage_collection(req.collection)
    kps = _current_knowledge_points(collection)
    if not kps:
        return {"questions": [], "error": "No knowledge points found"}

    from src.core.settings import resolve_path
    prompt_path = resolve_path("config/prompts/quiz_generation.txt")
    prompt_template = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""

    kp_text = "\n".join(f"- {_kp_text(kp)}" for kp in kps[:20])
    prompt = prompt_template.replace("{{knowledge_points}}", kp_text)
    prompt = prompt.replace("{{num_questions}}", str(req.num_questions))
    prompt = prompt.replace("{{difficulty}}", req.difficulty)

    try:
        from src.libs.llm import LLMFactory, Message

        settings = get_settings()
        llm = LLMFactory.create(settings)
        response = llm.chat(
            [Message(role="user", content=prompt)],
            temperature=0.0,
            max_tokens=1200,
        )
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
            raw = re.sub(r"\s*```$", "", raw).strip()
        questions = json.loads(raw)
        if isinstance(questions, dict):
            questions = questions.get("questions", [])
        if not isinstance(questions, list):
            return {"questions": [], "error": "Quiz response is not a list"}
        return {"questions": questions}
    except Exception as exc:
        return {"questions": [], "error": str(exc)}


@router.post("/review/submit")
async def submit_review(req: ReviewSubmitRequest):
    collection = storage_collection(req.collection)
    store = _get_mastery_store(collection)
    from src.core.types import MasteryRecord
    from src.ingestion.storage.spaced_repetition import calculate_next_review

    existing = store.get_record(req.knowledge_point_id, collection)
    if existing is None:
        existing = MasteryRecord(
            knowledge_point_id=req.knowledge_point_id,
            collection=collection,
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
    collection = storage_collection(collection)
    _sync_mastery_records(collection)
    store = _get_mastery_store(collection)
    stats = store.get_stats(collection)
    return {"collection": collection, **stats}
