"""Graph-RAG graph inspection endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from src.api.collection_names import storage_collection
from src.api.dependencies import get_data_service
from src.core.settings import resolve_path
from src.ingestion.storage.graph_index import GraphIndex

router = APIRouter()


@router.get("")
async def get_graph(collection: Optional[str] = None, limit: int = 250):
    collection_name = storage_collection(collection or "default")
    graph_index = GraphIndex(db_path=str(resolve_path("data/db/graph/graph_index.db")))
    payload = graph_index.get_graph(collection_name, limit=max(1, min(limit, 1000)))

    disabled_hashes: set[str] = set()
    try:
        disabled_hashes = set(get_data_service().list_disabled_document_hashes(collection_name))
    except Exception:
        disabled_hashes = set()

    if disabled_hashes:
        nodes = [
            node
            for node in payload.get("nodes", [])
            if str(node.get("doc_hash") or (node.get("metadata") or {}).get("doc_hash") or "") not in disabled_hashes
        ]
        node_ids = {str(node.get("id")) for node in nodes}
        edges = [
            edge
            for edge in payload.get("edges", [])
            if edge.get("source") in node_ids
            and edge.get("target") in node_ids
            and str((edge.get("metadata") or {}).get("doc_hash", "")) not in disabled_hashes
        ]
        payload["nodes"] = nodes
        payload["edges"] = edges
        payload["stats"] = {
            **payload.get("stats", {}),
            "visible_node_count": len(nodes),
            "visible_edge_count": len(edges),
            "disabled_document_count": len(disabled_hashes),
        }

    return payload
