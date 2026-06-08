"""Optional OCR backends for scanned document ingestion."""

from .rapidocr_engine import OCRBlock, OCRUnavailableError, RapidOCREngine

__all__ = ["OCRBlock", "OCRUnavailableError", "RapidOCREngine"]
