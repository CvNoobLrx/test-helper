from pathlib import Path

import pytest

from src.libs.loader.pdf_loader import PdfLoader
from src.libs.ocr.rapidocr_engine import OCRBlock, OCRUnavailableError


fitz = pytest.importorskip("fitz")


class _UnavailableEngine:
    def ensure_loaded(self) -> None:
        raise OCRUnavailableError("RapidOCR is missing")


class _FakeEngine:
    def ensure_loaded(self) -> None:
        return None

    def recognize(self, image, page_num: int):
        return [
            OCRBlock(
                id=f"ocr_p{page_num}_001",
                page_num=page_num,
                bbox=[[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]],
                text="1. 细胞的基本结构是什么？",
                score=0.99,
            ),
            OCRBlock(
                id=f"ocr_p{page_num}_002",
                page_num=page_num,
                bbox=[[0.0, 12.0], [10.0, 12.0], [10.0, 22.0], [0.0, 22.0]],
                text="答案：细胞膜、细胞质和细胞核。",
                score=0.98,
            ),
        ]


def _make_loader() -> PdfLoader:
    loader = PdfLoader.__new__(PdfLoader)
    loader.ocr_mode = "auto"
    loader.ocr_provider = "rapidocr"
    loader.ocr_dpi = 180
    loader.ocr_min_text_chars_per_page = 30
    loader.ocr_max_pages = None
    loader._ocr_engine = None
    return loader


def _write_blank_pdf(path: Path) -> None:
    doc = fitz.open()
    doc.new_page()
    doc.save(path)
    doc.close()


def test_pdf_loader_keeps_plain_text_when_ocr_is_missing(tmp_path):
    loader = _make_loader()
    loader._get_ocr_engine = lambda: _UnavailableEngine()

    text, metadata = PdfLoader._apply_ocr_fallback(
        loader,
        tmp_path / "scan.pdf",
        "",
        [{"page_num": 1, "native_text_chars": 0, "image_count": 1}],
    )

    assert metadata["ocr_used"] is False
    assert metadata["ocr_pages"] == []
    assert metadata["ocr_blocks"] == []
    assert "OCR 可选依赖" in text


def test_pdf_loader_appends_ocr_markdown_when_blocks_exist(tmp_path):
    pdf_path = tmp_path / "scan.pdf"
    _write_blank_pdf(pdf_path)

    loader = _make_loader()
    loader._get_ocr_engine = lambda: _FakeEngine()

    text, metadata = PdfLoader._apply_ocr_fallback(
        loader,
        pdf_path,
        "",
        [{"page_num": 1, "native_text_chars": 0, "image_count": 1}],
    )

    assert metadata["ocr_used"] is True
    assert len(metadata["ocr_pages"]) == 1
    assert metadata["ocr_pages"][0]["ocr_block_count"] == 2
    assert len(metadata["ocr_blocks"]) == 2
    assert "## OCR Page 1" in text
    assert "细胞膜" in text
