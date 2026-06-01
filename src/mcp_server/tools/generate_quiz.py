"""MCP Tool: generate_quiz

Generates review quiz questions from knowledge points using LLM.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from mcp import types

if TYPE_CHECKING:
    from src.mcp_server.protocol_handler import ProtocolHandler

from src.core.settings import load_settings, resolve_path
from src.core.types import QuizQuestion
from src.ingestion.storage.knowledge_point_index import KnowledgePointIndex
from src.ingestion.storage.mastery_store import MasteryStore
from src.libs.llm.llm_factory import LLMFactory
from src.libs.llm.base_llm import Message

logger = logging.getLogger(__name__)

TOOL_NAME = "generate_quiz"
TOOL_DESCRIPTION = """Generate review quiz questions from knowledge points in a collection.

Creates quiz questions to help with exam preparation. Questions can be
multiple choice (MCQ), short answer, or true/false.

Options:
- Generate questions for specific knowledge points
- Auto-select knowledge points based on mastery (prioritizes low-mastery items)
- Configure difficulty and number of questions
"""

TOOL_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "collection": {
            "type": "string",
            "description": "Collection to generate quiz for.",
        },
        "num_questions": {
            "type": "integer",
            "description": "Number of questions to generate (1-20).",
            "default": 5,
            "minimum": 1,
            "maximum": 20,
        },
        "difficulty": {
            "type": "string",
            "description": "Difficulty level.",
            "enum": ["easy", "medium", "hard"],
            "default": "medium",
        },
        "knowledge_point_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Specific KP IDs to quiz on. If omitted, auto-selects based on mastery.",
        },
    },
    "required": ["collection"],
}


class GenerateQuizTool:
    def __init__(self):
        self._settings = None
        self._kp_index = None
        self._mastery_store = None

    @property
    def settings(self):
        if self._settings is None:
            self._settings = load_settings()
        return self._settings

    @property
    def kp_index(self) -> KnowledgePointIndex:
        if self._kp_index is None:
            self._kp_index = KnowledgePointIndex(
                index_dir=str(resolve_path("data/db/knowledge_points"))
            )
        return self._kp_index

    @property
    def mastery_store(self) -> MasteryStore:
        if self._mastery_store is None:
            data_dir = "data/db/mastery"
            if self.settings.mastery:
                data_dir = self.settings.mastery.data_dir
            self._mastery_store = MasteryStore(data_dir=str(resolve_path(data_dir)))
        return self._mastery_store

    def select_knowledge_points(
        self,
        collection: str,
        num_questions: int,
        kp_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        all_kps = self.kp_index.get_by_collection(collection)
        if not all_kps:
            return []

        if kp_ids:
            selected = [kp for kp in all_kps if kp["id"] in kp_ids]
            return selected[:num_questions]

        # Auto-select based on mastery (prioritize low mastery)
        records = {
            r.knowledge_point_id: r
            for r in self.mastery_store.get_all_records(collection)
        }

        def sort_key(kp):
            rec = records.get(kp["id"])
            if rec is None:
                return (0, 0)  # Never reviewed = highest priority
            return (rec.correct_rate, rec.review_count)

        all_kps.sort(key=sort_key)
        return all_kps[:num_questions]

    def generate_questions(
        self,
        kps: List[Dict[str, Any]],
        num_questions: int,
        difficulty: str,
    ) -> List[QuizQuestion]:
        try:
            llm = LLMFactory.create(self.settings)
        except Exception as e:
            logger.error(f"Failed to create LLM: {e}")
            return []

        prompt_path = resolve_path("config/prompts/quiz_generation.txt")
        if not prompt_path.exists():
            logger.error(f"Quiz generation prompt not found: {prompt_path}")
            return []

        prompt_template = prompt_path.read_text(encoding="utf-8")
        kp_text = "\n".join(
            f"- ID: {kp['id']}, 分类: {kp.get('category', 'general')}, "
            f"重要性: {kp.get('importance', 3)}, 内容: {kp['text']}"
            for kp in kps
        )

        formatted_prompt = prompt_template.replace("{knowledge_points}", kp_text)
        formatted_prompt = formatted_prompt.replace("{num_questions}", str(num_questions))
        formatted_prompt = formatted_prompt.replace("{difficulty}", difficulty)

        try:
            messages = [Message(role="user", content=formatted_prompt)]
            response = llm.chat(messages)

            response_text = response
            if hasattr(response, "content"):
                response_text = response.content
            elif not isinstance(response, str):
                response_text = str(response)

            return self._parse_questions(response_text, kps)
        except Exception as e:
            logger.error(f"LLM quiz generation failed: {e}")
            return []

    def _parse_questions(
        self,
        response: str,
        kps: List[Dict[str, Any]],
    ) -> List[QuizQuestion]:
        try:
            json_match = re.search(r"\[.*\]", response, re.DOTALL)
            if not json_match:
                return []

            raw_questions = json.loads(json_match.group())
            if not isinstance(raw_questions, list):
                return []

            kp_ids = {kp["id"] for kp in kps}
            questions = []
            for i, raw in enumerate(raw_questions):
                if not isinstance(raw, dict) or "question_text" not in raw:
                    continue

                kp_id = raw.get("knowledge_point_id", "")
                if kp_id not in kp_ids and kps:
                    kp_id = kps[i % len(kps)]["id"]

                questions.append(QuizQuestion(
                    id=f"q_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{i}",
                    knowledge_point_id=kp_id,
                    question_type=raw.get("question_type", "short_answer"),
                    question_text=raw["question_text"],
                    options=raw.get("options", []),
                    correct_answer=raw.get("correct_answer", ""),
                    explanation=raw.get("explanation", ""),
                ))

            return questions
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse quiz questions: {e}")
            return []

    async def execute(
        self,
        collection: str,
        num_questions: int = 5,
        difficulty: str = "medium",
        knowledge_point_ids: Optional[List[str]] = None,
    ) -> types.CallToolResult:
        logger.info(f"Executing generate_quiz for collection={collection}")

        try:
            kps = await asyncio.to_thread(
                self.select_knowledge_points, collection, num_questions, knowledge_point_ids
            )

            if not kps:
                return types.CallToolResult(
                    content=[types.TextContent(
                        type="text",
                        text=f"No knowledge points found in collection '{collection}'. "
                             "Please ingest documents first.",
                    )],
                    isError=False,
                )

            questions = await asyncio.to_thread(
                self.generate_questions, kps, num_questions, difficulty
            )

            if not questions:
                return types.CallToolResult(
                    content=[types.TextContent(
                        type="text",
                        text="Failed to generate quiz questions. Please try again.",
                    )],
                    isError=True,
                )

            # Format response
            lines = [f"# 复习测验 ({len(questions)} 题)\n"]
            for i, q in enumerate(questions, 1):
                lines.append(f"## 第 {i} 题 [{q.question_type}]")
                lines.append(f"**{q.question_text}**\n")
                if q.options:
                    for opt in q.options:
                        lines.append(f"- {opt}")
                    lines.append("")
                lines.append(f"**正确答案:** {q.correct_answer}")
                if q.explanation:
                    lines.append(f"**解释:** {q.explanation}")
                lines.append("---\n")

            return types.CallToolResult(
                content=[types.TextContent(type="text", text="\n".join(lines))],
                isError=False,
            )

        except Exception as e:
            logger.exception("Error executing generate_quiz")
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=f"Error: {str(e)}")],
                isError=True,
            )


def register_tool(protocol_handler: ProtocolHandler) -> None:
    tool = GenerateQuizTool()

    async def handler(
        collection: str,
        num_questions: int = 5,
        difficulty: str = "medium",
        knowledge_point_ids: Optional[List[str]] = None,
    ) -> types.CallToolResult:
        return await tool.execute(
            collection=collection,
            num_questions=num_questions,
            difficulty=difficulty,
            knowledge_point_ids=knowledge_point_ids,
        )

    protocol_handler.register_tool(
        name=TOOL_NAME,
        description=TOOL_DESCRIPTION,
        input_schema=TOOL_INPUT_SCHEMA,
        handler=handler,
    )
    logger.info(f"Registered MCP tool: {TOOL_NAME}")
