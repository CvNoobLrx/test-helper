"""Mastery Store for tracking student's knowledge point mastery.

Persists mastery data as JSON files, following the same atomic-write
pattern as BM25Indexer.
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

from src.core.types import MasteryRecord
from src.observability.logger import get_logger

logger = get_logger(__name__)


class MasteryStore:
    """Stores and retrieves mastery records for knowledge points.

    Persists as JSON at: data/db/mastery/{collection}_mastery.json

    JSON Schema:
        {
            "metadata": {
                "collection": str,
                "total_knowledge_points": int,
                "last_updated": str
            },
            "records": {
                "kp_id": {MasteryRecord fields}
            }
        }
    """

    def __init__(self, data_dir: str = "data/db/mastery"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Dict[str, Any]] = {}

    def _get_file_path(self, collection: str) -> Path:
        return self.data_dir / f"{collection}_mastery.json"

    def load(self, collection: str) -> bool:
        path = self._get_file_path(collection)
        if not path.exists():
            self._cache[collection] = {
                "metadata": {"collection": collection, "total_knowledge_points": 0},
                "records": {},
            }
            return False

        try:
            with open(path, "r", encoding="utf-8") as f:
                self._cache[collection] = json.load(f)
            return True
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load mastery data for {collection}: {e}")
            self._cache[collection] = {
                "metadata": {"collection": collection, "total_knowledge_points": 0},
                "records": {},
            }
            return False

    def _ensure_loaded(self, collection: str) -> None:
        if collection not in self._cache:
            self.load(collection)

    def _save(self, collection: str) -> None:
        self._ensure_loaded(collection)
        data = self._cache[collection]
        data["metadata"]["total_knowledge_points"] = len(data["records"])
        data["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()

        path = self._get_file_path(collection)
        fd, tmp_path = tempfile.mkstemp(dir=str(self.data_dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(path))
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def get_record(self, knowledge_point_id: str, collection: str = "default") -> Optional[MasteryRecord]:
        self._ensure_loaded(collection)
        record_dict = self._cache[collection]["records"].get(knowledge_point_id)
        if record_dict is None:
            return None
        return MasteryRecord.from_dict(record_dict)

    def get_all_records(self, collection: str = "default") -> List[MasteryRecord]:
        self._ensure_loaded(collection)
        return [
            MasteryRecord.from_dict(r)
            for r in self._cache[collection]["records"].values()
        ]

    def update_record(self, record: MasteryRecord) -> None:
        collection = record.collection
        self._ensure_loaded(collection)
        self._cache[collection]["records"][record.knowledge_point_id] = record.to_dict()
        self._save(collection)

    def get_due_items(
        self,
        collection: str = "default",
        now: Optional[datetime] = None,
    ) -> List[MasteryRecord]:
        """Get knowledge points due for review.

        Args:
            collection: Collection name
            now: Current time (for testing; defaults to utcnow)

        Returns:
            List of MasteryRecords where next_review_time <= now
        """
        if now is None:
            now = datetime.now(timezone.utc)

        self._ensure_loaded(collection)
        due_items = []

        for record_dict in self._cache[collection]["records"].values():
            next_review_str = record_dict.get("next_review_time")
            if next_review_str is None:
                # Never reviewed - always due
                due_items.append(MasteryRecord.from_dict(record_dict))
                continue

            try:
                next_review = datetime.fromisoformat(next_review_str)
                if next_review.tzinfo is None:
                    next_review = next_review.replace(tzinfo=timezone.utc)
                if next_review <= now:
                    due_items.append(MasteryRecord.from_dict(record_dict))
            except ValueError:
                due_items.append(MasteryRecord.from_dict(record_dict))

        return due_items

    def get_stats(self, collection: str = "default") -> Dict[str, Any]:
        """Get mastery statistics for a collection.

        Returns:
            Dict with total, mastered, learning, needs_review counts
        """
        records = self.get_all_records(collection)

        mastered = 0
        learning = 0
        needs_review = 0

        for r in records:
            if r.review_count == 0:
                needs_review += 1
            elif r.correct_rate >= 0.8:
                mastered += 1
            elif r.correct_rate >= 0.5:
                learning += 1
            else:
                needs_review += 1

        return {
            "total": len(records),
            "mastered": mastered,
            "learning": learning,
            "needs_review": needs_review,
        }
