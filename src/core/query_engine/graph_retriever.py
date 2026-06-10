"""Graph-aware retrieval for Graph-RAG."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from src.core.types import RetrievalResult

if TYPE_CHECKING:
    from src.ingestion.storage.graph_index import GraphIndex

logger = logging.getLogger(__name__)


@dataclass
class GraphRetrievalResult:
    results: List[RetrievalResult]
    matched_nodes: List[dict[str, Any]]
    matched_edges: List[dict[str, Any]]
    expanded_node_ids: List[str]


class GraphRetriever:
    """Expand graph nodes into chunk-level retrieval candidates."""

    def __init__(
        self,
        graph_index: "GraphIndex",
        vector_store: Any,
        default_collection: str = "default",
        top_k: int = 20,
        max_hops: int = 2,
    ) -> None:
        self.graph_index = graph_index
        self.vector_store = vector_store
        self.default_collection = default_collection
        self.top_k = top_k
        self.max_hops = max_hops

    def retrieve(
        self,
        query: str,
        keywords: Optional[List[str]] = None,
        collection: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        top_k: Optional[int] = None,
        max_hops: Optional[int] = None,
        trace: Optional[Any] = None,
    ) -> List[RetrievalResult]:
        collection_name = collection or (filters or {}).get("collection") or self.default_collection
        excluded_doc_hashes = self._excluded_doc_hashes(filters)
        effective_top_k = top_k or self.top_k
        effective_max_hops = max_hops or self.max_hops

        terms = self._build_terms(query, keywords)
        t0 = time.monotonic()
        matched_nodes = self.graph_index.search_nodes(collection_name, terms, limit=effective_top_k)
        if excluded_doc_hashes:
            matched_nodes = [node for node in matched_nodes if str(node.get("doc_hash", "")) not in excluded_doc_hashes]

        frontier = [str(node["id"]) for node in matched_nodes]
        visited = set(frontier)
        expanded_nodes: list[dict[str, Any]] = []
        expanded_edges: list[dict[str, Any]] = []

        hops = 0
        while frontier and hops < effective_max_hops:
            nodes, edges = self.graph_index.get_neighbors(collection_name, frontier, limit=effective_top_k * 2)
            if excluded_doc_hashes:
                nodes = [node for node in nodes if str(node.get("doc_hash", "")) not in excluded_doc_hashes]
                edges = [edge for edge in edges if not self._edge_matches_excluded(edge, excluded_doc_hashes)]
            next_frontier: list[str] = []
            for node in nodes:
                node_id = str(node.get("id", ""))
                if not node_id or node_id in visited:
                    continue
                visited.add(node_id)
                next_frontier.append(node_id)
                expanded_nodes.append(node)
            for edge in edges:
                if edge not in expanded_edges:
                    expanded_edges.append(edge)
            frontier = next_frontier
            hops += 1

        node_ids = list(dict.fromkeys([*([n["id"] for n in matched_nodes if n.get("id")]), *[n["id"] for n in expanded_nodes if n.get("id")]]))
        chunk_ids: list[str] = []
        evidence_chunk_ids: list[str] = []
        for node in [*matched_nodes, *expanded_nodes]:
            chunk_ids.extend([str(chunk_id) for chunk_id in node.get("chunk_ids", []) if chunk_id])
        for edge in expanded_edges:
            evidence_chunk_ids.extend([str(chunk_id) for chunk_id in edge.get("evidence_chunk_ids", []) if chunk_id])
        chunk_ids.extend(evidence_chunk_ids)
        chunk_ids = list(dict.fromkeys(chunk_ids))

        records = self._fetch_chunks(chunk_ids, excluded_doc_hashes)
        result_map: dict[str, RetrievalResult] = {}
        for rank, record in enumerate(records):
            if not record:
                continue
            metadata = dict(record.get("metadata") or {})
            metadata["retrieval_source"] = "graph"
            metadata["graph_nodes"] = node_ids
            metadata["graph_matches"] = [node.get("label") for node in matched_nodes if node.get("label")]
            metadata["graph_edges"] = [edge.get("id") for edge in expanded_edges if edge.get("id")]
            metadata["graph_hops"] = hops
            chunk_id = str(record.get("id") or "")
            score = self._score_record(rank, record, matched_nodes, expanded_nodes)
            result_map[chunk_id] = RetrievalResult(
                chunk_id=chunk_id,
                score=score,
                text=str(record.get("text") or ""),
                metadata=metadata,
            )

        results = sorted(result_map.values(), key=lambda item: (-item.score, item.chunk_id))[:effective_top_k]
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        if trace is not None:
            trace.record_stage("graph_retrieval", {
                "query": query,
                "collection": collection_name,
                "keyword_count": len(keywords or []),
                "matched_nodes": matched_nodes,
                "expanded_nodes": expanded_nodes,
                "expanded_edges": expanded_edges,
                "result_count": len(results),
                "chunk_ids": [result.chunk_id for result in results],
            }, elapsed_ms=elapsed_ms)

        return results

    def _build_terms(self, query: str, keywords: Optional[List[str]]) -> List[str]:
        terms = [query]
        if keywords:
            terms.extend(keywords)
        terms.extend(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_+-]{2,}", query))
        return [term.strip() for term in terms if term and term.strip()]

    def _fetch_chunks(self, chunk_ids: List[str], excluded_doc_hashes: set[str]) -> List[dict[str, Any]]:
        if not chunk_ids:
            return []
        try:
            records = self.vector_store.get_by_ids(chunk_ids)
        except Exception as exc:
            logger.warning("GraphRetriever failed to fetch chunks: %s", exc)
            return []
        output: list[dict[str, Any]] = []
        for record in records:
            if not record:
                continue
            metadata = record.get("metadata") or {}
            if str(metadata.get("doc_hash", "")) in excluded_doc_hashes:
                continue
            output.append(record)
        return output

    def _score_record(
        self,
        rank: int,
        record: dict[str, Any],
        matched_nodes: List[dict[str, Any]],
        expanded_nodes: List[dict[str, Any]],
    ) -> float:
        base = 1.0 / (rank + 1)
        record_text = str(record.get("text") or "").lower()
        bonus = 0.0
        for node in matched_nodes:
            label = str(node.get("label") or "").lower()
            if label and label in record_text:
                bonus += 0.15
        if expanded_nodes:
            bonus += min(len(expanded_nodes), 5) * 0.03
        return min(base + bonus, 1.0)

    def _excluded_doc_hashes(self, filters: Optional[Dict[str, Any]]) -> set[str]:
        values = (filters or {}).get("excluded_doc_hashes") or []
        if isinstance(values, (list, tuple, set)):
            return {str(v) for v in values if v}
        return {str(values)} if values else set()

    def _edge_matches_excluded(self, edge: dict[str, Any], excluded_doc_hashes: set[str]) -> bool:
        metadata = edge.get("metadata") or {}
        return str(metadata.get("doc_hash", "")) in excluded_doc_hashes
