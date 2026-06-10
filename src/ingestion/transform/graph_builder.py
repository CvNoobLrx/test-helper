"""Build lightweight graph records from ingested document artifacts."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

from src.core.types import Chunk, Document
from src.ingestion.storage.graph_index import GraphEdgeRecord, GraphNodeRecord


def _slug(value: str, max_len: int = 80) -> str:
    value = re.sub(r"\s+", "_", value.strip().lower())
    value = re.sub(r"[^a-z0-9_\-\u4e00-\u9fff]", "", value)
    if not value:
        value = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
    return value[:max_len]


def _stable_id(prefix: str, *parts: str) -> str:
    raw = "::".join(str(part) for part in parts if part is not None)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    readable = _slug(parts[-1] if parts else prefix, 48)
    return f"{prefix}:{readable}:{digest}"


def _kp_text(kp: Dict[str, Any]) -> str:
    return str(kp.get("text") or kp.get("content") or kp.get("topic") or "").strip()


def _importance(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 1.0
    if number > 5:
        return min(number / 20.0, 5.0)
    return max(number, 1.0)


class GraphBuilder:
    """Convert document chunks, extracted KPs, and images into graph records."""

    def build(
        self,
        *,
        collection: str,
        document: Document,
        doc_hash: str | None = None,
        chunks: List[Chunk],
        vector_id_by_chunk: Dict[str, str],
        knowledge_points: List[Dict[str, Any]],
        images: List[Dict[str, Any]],
    ) -> tuple[List[GraphNodeRecord], List[GraphEdgeRecord]]:
        doc_hash = str(doc_hash or document.metadata.get("doc_hash") or document.id)
        source_path = str(document.metadata.get("source_path") or "")
        title = str(document.metadata.get("title") or Path(source_path).name or doc_hash[:12])
        nodes: Dict[str, GraphNodeRecord] = {}
        edges: Dict[str, GraphEdgeRecord] = {}

        doc_node_id = f"document:{doc_hash}"
        nodes[doc_node_id] = GraphNodeRecord(
            id=doc_node_id,
            type="document",
            label=title,
            collection=collection,
            importance=2.0,
            doc_hash=doc_hash,
            metadata={
                "doc_hash": doc_hash,
                "source_path": source_path,
                "doc_type": document.metadata.get("doc_type", ""),
            },
        )

        chunk_to_kp_nodes: dict[str, list[str]] = defaultdict(list)
        for kp in knowledge_points:
            label = _kp_text(kp)
            if not label:
                continue
            chunk_id = str(kp.get("chunk_id") or "")
            category = str(kp.get("category") or "").lower()
            node_type = "formula" if any(token in category for token in ["公式", "formula"]) else "knowledge_point"
            node_id = _stable_id(node_type, collection, doc_hash, str(kp.get("id") or label))
            nodes[node_id] = GraphNodeRecord(
                id=node_id,
                type=node_type,
                label=label,
                collection=collection,
                importance=_importance(kp.get("importance", 3)),
                aliases=[str(kp.get("topic") or ""), str(kp.get("subtopic") or "")],
                doc_hash=doc_hash,
                chunk_ids=[chunk_id] if chunk_id else [],
                metadata={
                    "doc_hash": doc_hash,
                    "kp_id": kp.get("id", ""),
                    "category": kp.get("category", "general"),
                    "topic": kp.get("topic", ""),
                    "subtopic": kp.get("subtopic", ""),
                    "exam_focus": kp.get("exam_focus", ""),
                },
            )
            chunk_to_kp_nodes[chunk_id].append(node_id)
            self._add_edge(
                edges,
                source=doc_node_id,
                target=node_id,
                edge_type="contains",
                collection=collection,
                doc_hash=doc_hash,
                chunk_ids=[chunk_id] if chunk_id else [],
                weight=1.0 + nodes[node_id].importance / 5.0,
            )
            self._add_edge(
                edges,
                source=node_id,
                target=doc_node_id,
                edge_type="appears_in",
                collection=collection,
                doc_hash=doc_hash,
                chunk_ids=[chunk_id] if chunk_id else [],
                weight=1.0,
            )

        for chunk in chunks:
            vector_id = vector_id_by_chunk.get(chunk.id, chunk.id)
            chapter = str(chunk.metadata.get("title") or "").strip()
            if not chapter:
                continue
            chapter_id = _stable_id("chapter", collection, doc_hash, chapter)
            nodes.setdefault(
                chapter_id,
                GraphNodeRecord(
                    id=chapter_id,
                    type="chapter",
                    label=chapter,
                    collection=collection,
                    importance=1.5,
                    doc_hash=doc_hash,
                    chunk_ids=[vector_id],
                    metadata={"doc_hash": doc_hash, "source_path": source_path},
                ),
            )
            self._add_edge(
                edges,
                source=doc_node_id,
                target=chapter_id,
                edge_type="contains",
                collection=collection,
                doc_hash=doc_hash,
                chunk_ids=[vector_id],
                weight=1.0,
            )
            for kp_node_id in chunk_to_kp_nodes.get(vector_id, []):
                self._add_edge(
                    edges,
                    source=chapter_id,
                    target=kp_node_id,
                    edge_type="explains",
                    collection=collection,
                    doc_hash=doc_hash,
                    chunk_ids=[vector_id],
                    weight=1.0,
                )

        for img in images:
            image_id = str(img.get("id") or img.get("image_id") or "")
            if not image_id:
                continue
            node_id = f"image:{image_id}"
            label = f"Image p.{img.get('page', 0)}"
            nodes[node_id] = GraphNodeRecord(
                id=node_id,
                type="image",
                label=label,
                collection=collection,
                importance=1.0,
                doc_hash=doc_hash,
                metadata={
                    "doc_hash": doc_hash,
                    "image_id": image_id,
                    "path": img.get("path") or img.get("file_path") or "",
                    "page": img.get("page", 0),
                },
            )
            self._add_edge(
                edges,
                source=node_id,
                target=doc_node_id,
                edge_type="appears_in",
                collection=collection,
                doc_hash=doc_hash,
                chunk_ids=[],
                weight=0.8,
            )

        for kp_node_ids in chunk_to_kp_nodes.values():
            for source, target in self._pairs(kp_node_ids[:8]):
                self._add_edge(
                    edges,
                    source=source,
                    target=target,
                    edge_type="related_to",
                    collection=collection,
                    doc_hash=doc_hash,
                    chunk_ids=list(nodes[source].chunk_ids or nodes[target].chunk_ids),
                    weight=0.7,
                )

        return list(nodes.values()), list(edges.values())

    def _add_edge(
        self,
        edges: Dict[str, GraphEdgeRecord],
        *,
        source: str,
        target: str,
        edge_type: str,
        collection: str,
        doc_hash: str,
        chunk_ids: List[str],
        weight: float,
    ) -> None:
        edge_id = _stable_id("edge", collection, source, edge_type, target, ",".join(chunk_ids))
        edges[edge_id] = GraphEdgeRecord(
            id=edge_id,
            source=source,
            target=target,
            type=edge_type,
            collection=collection,
            weight=weight,
            evidence_chunk_ids=chunk_ids,
            metadata={"doc_hash": doc_hash},
        )

    def _pairs(self, values: Iterable[str]) -> Iterable[tuple[str, str]]:
        items = list(dict.fromkeys(values))
        for index, source in enumerate(items):
            for target in items[index + 1 :]:
                yield source, target
