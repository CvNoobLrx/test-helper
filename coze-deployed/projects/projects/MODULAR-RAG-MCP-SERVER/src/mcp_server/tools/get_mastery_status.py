"""MCP Tool: get_mastery_status

Shows mastery levels for knowledge points in a collection.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

from mcp import types

if TYPE_CHECKING:
    from src.mcp_server.protocol_handler import ProtocolHandler

from src.core.settings import load_settings, resolve_path
from src.ingestion.storage.knowledge_point_index import KnowledgePointIndex
from src.ingestion.storage.mastery_store import MasteryStore

logger = logging.getLogger(__name__)

TOOL_NAME = "get_mastery_status"
TOOL_DESCRIPTION = """Show mastery status for knowledge points in a collection.

Returns an overview of the student's mastery levels:
- Total knowledge points
- Mastered (correct_rate >= 80%)
- Learning (50%-80%)
- Needs review (<50% or never reviewed)

Optionally filter by knowledge point category.
"""

TOOL_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "collection": {
            "type": "string",
            "description": "Collection to check mastery for.",
        },
        "category": {
            "type": "string",
            "description": "Filter by knowledge point category (e.g., '概念', '公式').",
        },
    },
    "required": ["collection"],
}


class GetMasteryStatusTool:
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
        category: Optional[str] = None,
    ) -> types.CallToolResult:
        logger.info(f"Executing get_mastery_status for collection={collection}")

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

            if category:
                all_kps = [kp for kp in all_kps if kp.get("category") == category]

            records = await asyncio.to_thread(
                self.mastery_store.get_all_records, collection
            )
            record_map = {r.knowledge_point_id: r for r in records}

            mastered = []
            learning = []
            needs_review = []

            for kp in all_kps:
                rec = record_map.get(kp["id"])
                if rec is None or rec.review_count == 0:
                    needs_review.append(kp)
                elif rec.correct_rate >= 0.8:
                    mastered.append(kp)
                elif rec.correct_rate >= 0.5:
                    learning.append(kp)
                else:
                    needs_review.append(kp)

            total = len(all_kps)
            lines = [
                f"# 掌握度报告: {collection}",
                f"",
                f"**总知识点数:** {total}",
                f"**已掌握 (>=80%):** {len(mastered)} ({len(mastered)*100//max(total,1)}%)",
                f"**学习中 (50-80%):** {len(learning)} ({len(learning)*100//max(total,1)}%)",
                f"**需复习 (<50%):** {len(needs_review)} ({len(needs_review)*100//max(total,1)}%)",
                "",
            ]

            if category:
                lines[1] = f"**分类筛选:** {category}"

            if needs_review:
                lines.append("## 需要复习的知识点")
                for kp in needs_review[:10]:
                    rec = record_map.get(kp["id"])
                    rate = f"{rec.correct_rate*100:.0f}%" if rec and rec.review_count > 0 else "未复习"
                    lines.append(f"- [{kp.get('category', '')}] {kp['text']} (掌握度: {rate})")
                if len(needs_review) > 10:
                    lines.append(f"  ... 还有 {len(needs_review) - 10} 个")

            return types.CallToolResult(
                content=[types.TextContent(type="text", text="\n".join(lines))],
                isError=False,
            )

        except Exception as e:
            logger.exception("Error executing get_mastery_status")
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=f"Error: {str(e)}")],
                isError=True,
            )


def register_tool(protocol_handler: ProtocolHandler) -> None:
    tool = GetMasteryStatusTool()

    async def handler(
        collection: str,
        category: Optional[str] = None,
    ) -> types.CallToolResult:
        return await tool.execute(collection=collection, category=category)

    protocol_handler.register_tool(
        name=TOOL_NAME,
        description=TOOL_DESCRIPTION,
        input_schema=TOOL_INPUT_SCHEMA,
        handler=handler,
    )
    logger.info(f"Registered MCP tool: {TOOL_NAME}")
