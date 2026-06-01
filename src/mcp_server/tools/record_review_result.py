"""MCP Tool: record_review_result

Records a review answer and updates mastery using SM-2 spaced repetition.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

from mcp import types

if TYPE_CHECKING:
    from src.mcp_server.protocol_handler import ProtocolHandler

from src.core.settings import load_settings, resolve_path
from src.core.types import MasteryRecord
from src.ingestion.storage.mastery_store import MasteryStore
from src.ingestion.storage.spaced_repetition import calculate_next_review

logger = logging.getLogger(__name__)

TOOL_NAME = "record_review_result"
TOOL_DESCRIPTION = """Record the result of a knowledge point review.

Updates the mastery record using SM-2 spaced repetition algorithm.
The quality parameter indicates how well the student recalled:

- 0: Complete blackout
- 1: Incorrect, but recognized the answer
- 2: Incorrect, but answer seemed easy
- 3: Correct with serious difficulty
- 4: Correct after hesitation
- 5: Perfect response

The system automatically calculates the next review date.
"""

TOOL_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "knowledge_point_id": {
            "type": "string",
            "description": "The knowledge point ID being reviewed.",
        },
        "quality": {
            "type": "integer",
            "description": "Recall quality (0-5).",
            "minimum": 0,
            "maximum": 5,
        },
        "collection": {
            "type": "string",
            "description": "Collection name.",
        },
    },
    "required": ["knowledge_point_id", "quality", "collection"],
}


class RecordReviewResultTool:
    def __init__(self):
        self._settings = None
        self._mastery_store = None

    @property
    def settings(self):
        if self._settings is None:
            self._settings = load_settings()
        return self._settings

    @property
    def mastery_store(self) -> MasteryStore:
        if self._mastery_store is None:
            data_dir = "data/db/mastery"
            if self.settings.mastery:
                data_dir = self.settings.mastery.data_dir
            self._mastery_store = MasteryStore(data_dir=str(resolve_path(data_dir)))
        return self._mastery_store

    async def execute(
        self,
        knowledge_point_id: str,
        quality: int,
        collection: str,
    ) -> types.CallToolResult:
        logger.info(
            f"Executing record_review_result: kp={knowledge_point_id}, "
            f"quality={quality}, collection={collection}"
        )

        try:
            # Get or create mastery record
            record = await asyncio.to_thread(
                self.mastery_store.get_record, knowledge_point_id, collection
            )

            if record is None:
                record = MasteryRecord(
                    knowledge_point_id=knowledge_point_id,
                    collection=collection,
                )

            # Calculate next review using SM-2
            min_ef = 1.3
            if self.settings.mastery:
                min_ef = self.settings.mastery.min_ease_factor

            updated_record = calculate_next_review(quality, record, min_ease_factor=min_ef)

            # Save updated record
            await asyncio.to_thread(self.mastery_store.update_record, updated_record)

            quality_labels = {
                0: "完全遗忘", 1: "认出但想不起来", 2: "想起但很困难",
                3: "正确但费力", 4: "正确稍有犹豫", 5: "完美回忆",
            }

            lines = [
                "# 复习结果已记录",
                "",
                f"**知识点:** {knowledge_point_id}",
                f"**回忆质量:** {quality} - {quality_labels.get(quality, '')}",
                f"**累计复习:** {updated_record.review_count} 次",
                f"**正确率:** {updated_record.correct_rate*100:.1f}%",
                f"**当前间隔:** {updated_record.interval_days} 天",
                f"**下次复习:** {updated_record.next_review_time}",
                f"**Ease Factor:** {updated_record.ease_factor}",
            ]

            return types.CallToolResult(
                content=[types.TextContent(type="text", text="\n".join(lines))],
                isError=False,
            )

        except Exception as e:
            logger.exception("Error executing record_review_result")
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=f"Error: {str(e)}")],
                isError=True,
            )


def register_tool(protocol_handler: ProtocolHandler) -> None:
    tool = RecordReviewResultTool()

    async def handler(
        knowledge_point_id: str,
        quality: int,
        collection: str,
    ) -> types.CallToolResult:
        return await tool.execute(
            knowledge_point_id=knowledge_point_id,
            quality=quality,
            collection=collection,
        )

    protocol_handler.register_tool(
        name=TOOL_NAME,
        description=TOOL_DESCRIPTION,
        input_schema=TOOL_INPUT_SCHEMA,
        handler=handler,
    )
    logger.info(f"Registered MCP tool: {TOOL_NAME}")
