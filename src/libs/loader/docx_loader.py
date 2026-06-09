"""DOCX loader implementation using MarkItDown."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional
from xml.etree import ElementTree as ET

try:
    from markitdown import MarkItDown
    MARKITDOWN_AVAILABLE = True
except ImportError:
    MARKITDOWN_AVAILABLE = False

from src.core.types import Document
from src.libs.loader.base_loader import BaseLoader


class DocxLoader(BaseLoader):
    """Loader for DOCX files."""

    SUPPORTED_EXTENSIONS = {".docx"}

    def __init__(self) -> None:
        if not MARKITDOWN_AVAILABLE:
            raise ImportError(
                "MarkItDown is required for DocxLoader. "
                "Install with: pip install markitdown"
            )
        self._markitdown = MarkItDown()

    def load(self, file_path: str | Path) -> Document:
        path = self._validate_file(file_path)
        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported Word format: {path.suffix}")

        doc_hash = self._compute_file_hash(path)
        doc_id = f"doc_{doc_hash[:16]}"

        try:
            result = self._markitdown.convert(str(path))
            text_content = result.text_content if hasattr(result, "text_content") else str(result)
        except Exception:
            text_content = self._extract_docx_text(path)
            if not text_content.strip():
                raise RuntimeError(f"DOCX parsing failed: {path.name}")

        metadata: Dict[str, Any] = {
            "source_path": str(path),
            "doc_type": "docx",
            "doc_hash": doc_hash,
            "title": self._extract_title(text_content) or path.stem,
        }
        return Document(id=doc_id, text=text_content, metadata=metadata)

    def _compute_file_hash(self, file_path: Path) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _extract_title(self, text: str) -> Optional[str]:
        lines = text.splitlines()
        for line in lines[:10]:
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
        for line in lines[:10]:
            line = line.strip()
            if line:
                return line[:120]
        return None

    def _extract_docx_text(self, path: Path) -> str:
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        try:
            with zipfile.ZipFile(path) as archive:
                document_xml = archive.read("word/document.xml")
        except Exception as exc:
            raise RuntimeError(f"Unable to read DOCX XML from {path}: {exc}") from exc

        try:
            root = ET.fromstring(document_xml)
        except ET.ParseError as exc:
            raise RuntimeError(f"Unable to parse DOCX XML from {path}: {exc}") from exc

        paragraphs: list[str] = []
        for paragraph in root.findall(".//w:p", namespace):
            pieces: list[str] = []
            for node in paragraph.iter():
                tag = node.tag.rsplit("}", 1)[-1]
                if tag == "t" and node.text:
                    pieces.append(node.text)
                elif tag in {"tab"}:
                    pieces.append("\t")
                elif tag in {"br", "cr"}:
                    pieces.append("\n")
            text = "".join(pieces).strip()
            if text:
                paragraphs.append(text)

        return "\n\n".join(paragraphs).strip()
