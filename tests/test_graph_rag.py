from pathlib import Path

from src.core.query_engine.hybrid_search import HybridSearch, HybridSearchConfig
from src.core.types import RetrievalResult
from src.core.query_engine.graph_retriever import GraphRetriever
from src.ingestion.storage.graph_index import GraphEdgeRecord, GraphIndex, GraphNodeRecord


def test_graph_index_upsert_search_and_remove(tmp_path: Path):
    graph = GraphIndex(db_path=str(tmp_path / "graph.db"))
    nodes = [
        GraphNodeRecord(
            id="document:doc1",
            type="document",
            label="Doc 1",
            collection="default",
            doc_hash="doc1",
        ),
        GraphNodeRecord(
            id="kp:gravity",
            type="knowledge_point",
            label="万有引力",
            collection="default",
            doc_hash="doc1",
            chunk_ids=["chunk1"],
        ),
    ]
    edges = [
        GraphEdgeRecord(
            id="edge:doc1:gravity",
            source="document:doc1",
            target="kp:gravity",
            type="contains",
            collection="default",
            evidence_chunk_ids=["chunk1"],
            metadata={"doc_hash": "doc1"},
        )
    ]

    graph.upsert_document_graph("default", "doc1", nodes, edges)

    payload = graph.get_graph("default")
    assert len(payload["nodes"]) == 2
    assert len(payload["edges"]) == 1
    assert graph.search_nodes("default", ["引力"])[0]["id"] == "kp:gravity"

    graph.remove_document("default", "doc1")
    assert graph.get_stats("default")["node_count"] == 0


def test_graph_retriever_expands_nodes_to_chunks(tmp_path: Path):
    graph = GraphIndex(db_path=str(tmp_path / "graph.db"))
    graph.upsert_document_graph(
        "physics",
        "doc1",
        [
            GraphNodeRecord(
                id="kp:newton",
                type="knowledge_point",
                label="牛顿第二定律",
                collection="physics",
                doc_hash="doc1",
                chunk_ids=["chunk1"],
            )
        ],
        [],
    )

    class FakeVectorStore:
        def get_by_ids(self, ids):
            return [
                {
                    "id": item,
                    "text": "牛顿第二定律说明力和加速度的关系",
                    "metadata": {"doc_hash": "doc1", "source_path": "physics.pdf"},
                }
                for item in ids
            ]

    retriever = GraphRetriever(graph, FakeVectorStore(), default_collection="physics")
    results = retriever.retrieve("牛顿第二定律是什么", keywords=["牛顿"], collection="physics")

    assert [result.chunk_id for result in results] == ["chunk1"]
    assert results[0].metadata["retrieval_source"] == "graph"


def test_hybrid_search_graph_switch_controls_graph_retriever():
    class FakeDense:
        def retrieve(self, query, top_k, filters=None, trace=None):
            return [RetrievalResult(chunk_id="dense1", score=0.8, text="dense", metadata={})]

    class FakeSparse:
        def retrieve(self, keywords, top_k, collection=None, filters=None, trace=None):
            return [RetrievalResult(chunk_id="sparse1", score=0.7, text="sparse", metadata={})]

    class FakeGraph:
        def __init__(self):
            self.calls = 0

        def retrieve(self, **kwargs):
            self.calls += 1
            return [RetrievalResult(chunk_id="graph1", score=0.9, text="graph", metadata={})]

    graph = FakeGraph()
    search = HybridSearch(
        dense_retriever=FakeDense(),
        sparse_retriever=FakeSparse(),
        graph_retriever=graph,
        config=HybridSearchConfig(parallel_retrieval=False),
    )

    disabled = search.search("hello world", enable_graph=False)
    assert graph.calls == 0
    assert "graph1" not in {result.chunk_id for result in disabled}

    enabled = search.search("hello world", enable_graph=True)
    assert graph.calls == 1
    assert "graph1" in {result.chunk_id for result in enabled}
