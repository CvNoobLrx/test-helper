"""Knowledge Point Index for persisting extracted knowledge points.

Stores knowledge point definitions as JSON files, following the same
atomic-write pattern as BM25Indexer.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional

from src.observability.logger import get_logger

logger = get_logger(__name__)


class KnowledgePointIndex:
    """Stores and retrieves knowledge point definitions.

    Persists as JSON at: data/db/knowledge_points/{collection}_kp.json

    JSON Schema:
        {
            "metadata": {"collection": str, "total_count": int, "last_updated": str},
            "knowledge_points": {
                "kp_id": {"id", "chunk_id", "text", "category", "importance", "source_ref"}
            }
        }
    """

    def __init__(self, index_dir: str = "data/db/knowledge_points"):
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Dict[str, Any]] = {}  # collection -> data

    def _get_index_path(self, collection: str) -> Path:
        return self.index_dir / f"{collection}_kp.json"

    def load(self, collection: str) -> bool:
        path = self._get_index_path(collection)
        if not path.exists():
            self._cache[collection] = {
                "metadata": {"collection": collection, "total_count": 0},
                "knowledge_points": {},
            }
            return False

        try:
            with open(path, "r", encoding="utf-8") as f:
                self._cache[collection] = json.load(f)
            return True
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load KP index for {collection}: {e}")
            self._cache[collection] = {
                "metadata": {"collection": collection, "total_count": 0},
                "knowledge_points": {},
            }
            return False

    def _ensure_loaded(self, collection: str) -> None:
        if collection not in self._cache:
            self.load(collection)

    def _save(self, collection: str) -> None:
        self._ensure_loaded(collection)
        data = self._cache[collection]
        data["metadata"]["total_count"] = len(data["knowledge_points"])

        from datetime import datetime, timezone
        data["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()

        path = self._get_index_path(collection)
        fd, tmp_path = tempfile.mkstemp(dir=str(self.index_dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(path))
            logger.debug(f"Saved KP index for {collection}: {data['metadata']['total_count']} KPs")
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def add_knowledge_points(
        self,
        knowledge_points: List[Dict[str, Any]],
        collection: str = "default",
    ) -> None:
        """Add knowledge points to the index.

        Args:
            knowledge_points: List of KP dicts with id, chunk_id, text, category, importance
            collection: Collection name
        """
        if not knowledge_points:
            return

        self._ensure_loaded(collection)
        kps = self._cache[collection]["knowledge_points"]

        for kp in knowledge_points:
            kp_id = kp.get("id")
            if not kp_id:
                continue
            kps[kp_id] = {
                "id": kp_id,
                "chunk_id": kp.get("chunk_id", ""),
                "text": kp.get("text", ""),
                "topic": kp.get("topic", ""),
                "subtopic": kp.get("subtopic", ""),
                "category": kp.get("category", "general"),
                "importance": kp.get("importance", 3),
                "exam_focus": kp.get("exam_focus", ""),
                "source_ref": kp.get("source_ref", ""),
            }

        self._save(collection)
        logger.info(f"Added {len(knowledge_points)} KPs to {collection} index")

    def get_by_id(self, kp_id: str, collection: str = "default") -> Optional[Dict[str, Any]]:
        self._ensure_loaded(collection)
        return self._cache[collection]["knowledge_points"].get(kp_id)

    def get_by_collection(self, collection: str) -> List[Dict[str, Any]]:
        self._ensure_loaded(collection)
        return list(self._cache[collection]["knowledge_points"].values())

    def get_by_chunk(self, chunk_id: str, collection: str = "default") -> List[Dict[str, Any]]:
        self._ensure_loaded(collection)
        return [
            kp for kp in self._cache[collection]["knowledge_points"].values()
            if kp.get("chunk_id") == chunk_id
        ]

    def remove_by_chunk(self, chunk_id: str, collection: str = "default") -> int:
        self._ensure_loaded(collection)
        kps = self._cache[collection]["knowledge_points"]
        to_remove = [kid for kid, kp in kps.items() if kp.get("chunk_id") == chunk_id]
        for kid in to_remove:
            del kps[kid]
        if to_remove:
            self._save(collection)
        return len(to_remove)

    def get_total_count(self, collection: str = "default") -> int:
        self._ensure_loaded(collection)
        return len(self._cache[collection]["knowledge_points"])
