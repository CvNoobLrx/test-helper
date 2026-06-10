"""SQLite-backed lightweight graph index for Graph-RAG."""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class GraphNodeRecord:
    id: str
    type: str
    label: str
    collection: str
    importance: float = 1.0
    aliases: list[str] = field(default_factory=list)
    doc_hash: str = ""
    chunk_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdgeRecord:
    id: str
    source: str
    target: str
    type: str
    collection: str
    weight: float = 1.0
    evidence_chunk_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class GraphIndex:
    """Persist and query a lightweight document graph."""

    def __init__(self, db_path: str = "data/db/graph/graph_index.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_database()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_database(self) -> None:
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS graph_nodes (
                    node_id TEXT PRIMARY KEY,
                    collection TEXT NOT NULL,
                    type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    aliases_json TEXT NOT NULL,
                    importance REAL NOT NULL DEFAULT 1.0,
                    doc_hash TEXT NOT NULL DEFAULT '',
                    chunk_ids_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS graph_edges (
                    edge_id TEXT PRIMARY KEY,
                    collection TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    weight REAL NOT NULL DEFAULT 1.0,
                    evidence_chunk_ids_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_graph_nodes_collection ON graph_nodes(collection)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_graph_nodes_doc_hash ON graph_nodes(doc_hash)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_graph_edges_collection ON graph_edges(collection)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges(source_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_graph_edges_target ON graph_edges(target_id)"
            )
            conn.commit()
        finally:
            conn.close()

    def upsert_document_graph(
        self,
        collection: str,
        doc_hash: str,
        nodes: List[GraphNodeRecord],
        edges: List[GraphEdgeRecord],
    ) -> None:
        conn = self._connect()
        try:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "DELETE FROM graph_edges WHERE collection = ? AND metadata_json LIKE ?",
                (collection, f'%"{doc_hash}"%'),
            )
            conn.execute(
                "DELETE FROM graph_nodes WHERE collection = ? AND doc_hash = ?",
                (collection, doc_hash),
            )
            for node in nodes:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO graph_nodes (
                        node_id, collection, type, label, aliases_json, importance,
                        doc_hash, chunk_ids_json, metadata_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        node.id,
                        collection,
                        node.type,
                        node.label,
                        json.dumps(node.aliases, ensure_ascii=False),
                        float(node.importance),
                        node.doc_hash,
                        json.dumps(node.chunk_ids, ensure_ascii=False),
                        json.dumps(node.metadata, ensure_ascii=False),
                        now,
                    ),
                )
            for edge in edges:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO graph_edges (
                        edge_id, collection, source_id, target_id, type, weight,
                        evidence_chunk_ids_json, metadata_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        edge.id,
                        collection,
                        edge.source,
                        edge.target,
                        edge.type,
                        float(edge.weight),
                        json.dumps(edge.evidence_chunk_ids, ensure_ascii=False),
                        json.dumps(edge.metadata, ensure_ascii=False),
                        now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def remove_document(self, collection: str, doc_hash: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "DELETE FROM graph_edges WHERE collection = ? AND metadata_json LIKE ?",
                (collection, f'%"{doc_hash}"%'),
            )
            conn.execute(
                "DELETE FROM graph_nodes WHERE collection = ? AND doc_hash = ?",
                (collection, doc_hash),
            )
            conn.commit()
        finally:
            conn.close()

    def get_graph(self, collection: str, limit: int = 250) -> dict[str, Any]:
        conn = self._connect()
        try:
            node_rows = conn.execute(
                """
                SELECT * FROM graph_nodes
                WHERE collection = ?
                ORDER BY importance DESC, label ASC
                LIMIT ?
                """,
                (collection, limit),
            ).fetchall()
            node_ids = [row["node_id"] for row in node_rows]
            edge_rows = []
            if node_ids:
                placeholders = ",".join("?" for _ in node_ids)
                edge_rows = conn.execute(
                    f"""
                    SELECT * FROM graph_edges
                    WHERE collection = ?
                      AND source_id IN ({placeholders})
                      AND target_id IN ({placeholders})
                    ORDER BY weight DESC, edge_id ASC
                    """,
                    [collection, *node_ids, *node_ids],
                ).fetchall()
            nodes = [self._node_from_row(row) for row in node_rows]
            edges = [self._edge_from_row(row) for row in edge_rows]
            stats = self.get_stats(collection)
            return {"nodes": nodes, "edges": edges, "stats": stats}
        finally:
            conn.close()

    def get_stats(self, collection: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            node_count = conn.execute(
                "SELECT COUNT(*) FROM graph_nodes WHERE collection = ?",
                (collection,),
            ).fetchone()[0]
            edge_count = conn.execute(
                "SELECT COUNT(*) FROM graph_edges WHERE collection = ?",
                (collection,),
            ).fetchone()[0]
            isolated_count = conn.execute(
                """
                SELECT COUNT(*) FROM graph_nodes n
                WHERE n.collection = ?
                  AND NOT EXISTS (
                      SELECT 1 FROM graph_edges e
                      WHERE e.collection = n.collection
                        AND (e.source_id = n.node_id OR e.target_id = n.node_id)
                  )
                """,
                (collection,),
            ).fetchone()[0]
            updated = conn.execute(
                "SELECT MAX(updated_at) FROM graph_nodes WHERE collection = ?",
                (collection,),
            ).fetchone()[0]
            return {
                "node_count": int(node_count or 0),
                "edge_count": int(edge_count or 0),
                "isolated_count": int(isolated_count or 0),
                "updated_at": updated,
            }
        finally:
            conn.close()

    def search_nodes(
        self,
        collection: str,
        terms: List[str],
        limit: int = 20,
    ) -> List[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM graph_nodes WHERE collection = ?",
                (collection,),
            ).fetchall()
            scored: list[tuple[float, sqlite3.Row]] = []
            lowered_terms = [term.lower() for term in terms if term]
            for row in rows:
                label = str(row["label"] or "").lower()
                aliases = [alias.lower() for alias in json.loads(row["aliases_json"] or "[]")]
                metadata = json.loads(row["metadata_json"] or "{}")
                searchable = " ".join(
                    [label, " ".join(aliases), json.dumps(metadata, ensure_ascii=False).lower()]
                )
                score = 0.0
                for term in lowered_terms:
                    if not term:
                        continue
                    if term in label:
                        score += 4.0
                    elif any(term in alias for alias in aliases):
                        score += 3.0
                    elif term in searchable:
                        score += 1.0
                if score > 0:
                    scored.append((score, row))
            scored.sort(key=lambda item: (-item[0], item[1]["label"]))
            return [self._node_from_row(row, score=score) for score, row in scored[:limit]]
        finally:
            conn.close()

    def get_neighbors(
        self,
        collection: str,
        node_ids: List[str],
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not node_ids:
            return [], []
        conn = self._connect()
        try:
            placeholders = ",".join("?" for _ in node_ids)
            node_rows = conn.execute(
                f"""
                SELECT * FROM graph_nodes
                WHERE collection = ?
                  AND node_id IN (
                      SELECT target_id FROM graph_edges WHERE collection = ? AND source_id IN ({placeholders})
                      UNION
                      SELECT source_id FROM graph_edges WHERE collection = ? AND target_id IN ({placeholders})
                  )
                LIMIT ?
                """,
                [collection, collection, *node_ids, collection, *node_ids, limit],
            ).fetchall()
            edge_rows = conn.execute(
                f"""
                SELECT * FROM graph_edges
                WHERE collection = ?
                  AND (source_id IN ({placeholders}) OR target_id IN ({placeholders}))
                LIMIT ?
                """,
                [collection, *node_ids, *node_ids, limit],
            ).fetchall()
            return (
                [self._node_from_row(row) for row in node_rows],
                [self._edge_from_row(row) for row in edge_rows],
            )
        finally:
            conn.close()

    def _node_from_row(self, row: sqlite3.Row, score: float | None = None) -> dict[str, Any]:
        payload = {
            "id": row["node_id"],
            "type": row["type"],
            "label": row["label"],
            "collection": row["collection"],
            "importance": row["importance"],
            "aliases": json.loads(row["aliases_json"] or "[]"),
            "doc_hash": row["doc_hash"],
            "chunk_ids": json.loads(row["chunk_ids_json"] or "[]"),
            "metadata": json.loads(row["metadata_json"] or "{}"),
        }
        if score is not None:
            payload["score"] = score
        return payload

    def _edge_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["edge_id"],
            "source": row["source_id"],
            "target": row["target_id"],
            "type": row["type"],
            "collection": row["collection"],
            "weight": row["weight"],
            "evidence_chunk_ids": json.loads(row["evidence_chunk_ids_json"] or "[]"),
            "metadata": json.loads(row["metadata_json"] or "{}"),
        }
