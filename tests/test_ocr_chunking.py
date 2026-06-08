from src.core.settings import load_settings, resolve_path
from src.core.types import Document
from src.ingestion.chunking.document_chunker import DocumentChunker


def test_ocr_pages_keep_exam_questions_and_answers_together():
    settings = load_settings(resolve_path("config/settings.yaml"))
    chunker = DocumentChunker(settings)

    document = Document(
        id="doc_ocr_exam",
        text=(
            "## OCR Page 1\n\n"
            "1. 细胞的基本结构是什么？\n"
            "答案：细胞膜、细胞质和细胞核。\n"
            "2. 光合作用的主要场所是什么？\n"
            "答案：叶绿体。"
        ),
        metadata={
            "source_path": "E:/tmp/scan.pdf",
            "ocr_used": True,
            "ocr_provider": "rapidocr",
            "ocr_pages": [
                {
                    "page_num": 1,
                    "native_text_chars": 0,
                    "image_count": 1,
                    "ocr_block_count": 4,
                }
            ],
            "ocr_blocks": [
                {
                    "id": "ocr_p1_001",
                    "page_num": 1,
                    "bbox": [[0, 0], [10, 0], [10, 10], [0, 10]],
                    "text": "1. 细胞的基本结构是什么？",
                    "score": 0.99,
                },
                {
                    "id": "ocr_p1_002",
                    "page_num": 1,
                    "bbox": [[0, 12], [10, 12], [10, 22], [0, 22]],
                    "text": "答案：细胞膜、细胞质和细胞核。",
                    "score": 0.98,
                },
                {
                    "id": "ocr_p1_003",
                    "page_num": 1,
                    "bbox": [[0, 24], [10, 24], [10, 34], [0, 34]],
                    "text": "2. 光合作用的主要场所是什么？",
                    "score": 0.97,
                },
                {
                    "id": "ocr_p1_004",
                    "page_num": 1,
                    "bbox": [[0, 36], [10, 36], [10, 46], [0, 46]],
                    "text": "答案：叶绿体。",
                    "score": 0.96,
                },
            ],
        },
    )

    chunks = chunker.split_document(document)

    assert len(chunks) == 2
    assert [chunk.metadata["page_num"] for chunk in chunks] == [1, 1]
    assert all(chunk.metadata["ocr_source"] is True for chunk in chunks)
    assert chunks[0].metadata["ocr_block_refs"] == ["ocr_p1_001", "ocr_p1_002"]
    assert chunks[1].metadata["ocr_block_refs"] == ["ocr_p1_003", "ocr_p1_004"]
    assert "细胞膜" in chunks[0].text
    assert "叶绿体" in chunks[1].text
