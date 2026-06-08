"""MCP Tool: get_review_plan

Returns a personalized review schedule for today based on mastery data.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from mcp import types

if TYPE_CHECKING:
    from src.mcp_server.protocol_handler import ProtocolHandler

from src.core.settings import load_settings, resolve_path
from src.core.types import MasteryRecord
from src.ingestion.storage.knowledge_point_index import KnowledgePointIndex
from src.ingestion.storage.mastery_store import MasteryStore

logger = logging.getLogger(__name__)

TOOL_NAME = "get_review_plan"
TOOL_DESCRIPTION = """Get a personalized review plan for today.

Returns knowledge points that need review, prioritized by:
1. Overdue items (next_review_time has passed)
2. Items with lowest correct_rate
3. Never-reviewed items

Use this tool to start a study session.
"""

TOOL_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "collection": {
            "type": "string",
            "description": "Collection to get review plan for.",
        },
        "max_items": {
            "type": "integer",
            "description": "Maximum number of items to review (1-50).",
            "default": 10,
            "minimum": 1,
            "maximum": 50,
        },
    },
    "required": ["collection"],
}


class GetReviewPlanTool:
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

    async def execute(
        self,
        collection: str,
        max_items: int = 10,
    ) -> types.CallToolResult:
        logger.info(f"Executing get_review_plan for collection={collection}")

        try:
            all_kps = await asyncio.to_thread(
                self.kp_index.get_by_collection, collection
            )

            if not all_kps:
                return types.CallToolResult(
                    content=[types.TextContent(
                        type="text",
                        text=f"No knowledge points found in collection '{collection}'.",
                    )],
                    isError=False,
                )

            # Get due items (overdue)
            due_records = await asyncio.to_thread(
                self.mastery_store.get_due_items, collection
            )
            due_ids = {r.knowledge_point_id for r in due_records}

            # Get all records for mastery info
            all_records = await asyncio.to_thread(
                self.mastery_store.get_all_records, collection
            )
            record_map = {r.knowledge_point_id: r for r in all_records}

            # Build review list
            kp_map = {kp["id"]: kp for kp in all_kps}

            # Priority 1: Due items
            review_items: List[Dict[str, Any]] = []
            for rec in due_records:
                kp = kp_map.get(rec.knowledge_point_id)
                if kp:
                    review_items.append({
                        "kp": kp,
                        "record": rec,
                        "priority": "overdue" if rec.review_count > 0 else "new",
                    })

            # Priority 2: Low mastery items not yet due
            remaining_kps = [
                kp for kp in all_kps
                if kp["id"] not in due_ids
            ]
            remaining_kps.sort(key=lambda kp: (
                record_map.get(kp["id"], MasteryRecord(knowledge_point_id="", collection="")).correct_rate
                if kp["id"] in record_map
                else 0.0
            ))

            for kp in remaining_kps:
                if len(review_items) >= max_items:
                    break
                rec = record_map.get(kp["id"])
                review_items.append({
                    "kp": kp,
                    "record": rec,
                    "priority": "low_mastery",
                })

            review_items = review_items[:max_items]

            # Format response
            lines = [
                f"# 今日复习计划: {collection}",
                f"",
                f"**待复习:** {len(review_items)} 个知识点",
                "",
            ]

            for i, item in enumerate(review_items, 1):
                kp = item["kp"]
                rec = item["record"]
                priority = item["priority"]

                rate = "未复习"
                if rec and rec.review_count > 0:
                    rate = f"{rec.correct_rate*100:.0f}%"

                priority_label = {
                    "overdue": "已到期",
                    "new": "新知识点",
                    "low_mastery": "需加强",
                }.get(priority, "")

                lines.append(f"### {i}. [{kp.get('category', '')}] {kp['text']}")
                lines.append(f"- 状态: {priority_label} | 掌握度: {rate}")
                if rec and rec.interval_days:
                    lines.append(f"- 当前间隔: {rec.interval_days} 天")
                lines.append(f"- 知识点ID: `{kp['id']}`")
                lines.append("")

            lines.append("---")
            lines.append("使用 `record_review_result` 工具记录每次复习的结果。")

            return types.CallToolResult(
                content=[types.TextContent(type="text", text="\n".join(lines))],
                isError=False,
            )

        except Exception as e:
            logger.exception("Error executing get_review_plan")
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=f"Error: {str(e)}")],
                isError=True,
            )


def register_tool(protocol_handler: ProtocolHandler) -> None:
    tool = GetReviewPlanTool()

    async def handler(
        collection: str,
        max_items: int = 10,
    ) -> types.CallToolResult:
        return await tool.execute(collection=collection, max_items=max_items)

    protocol_handler.register_tool(
        name=TOOL_NAME,
        description=TOOL_DESCRIPTION,
        input_schema=TOOL_INPUT_SCHEMA,
        handler=handler,
    )
    logger.info(f"Registered MCP tool: {TOOL_NAME}")
