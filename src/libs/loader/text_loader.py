"""Plain text / markdown loader implementation.

This loader handles simple UTF-8-ish text files by reading them directly
and normalizing them into the shared Document contract.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Optional

from src.core.types import Document
from src.libs.loader.base_loader import BaseLoader


class TextLoader(BaseLoader):
    """Loader for plain text and markdown files."""

    SUPPORTED_EXTENSIONS = {".txt", ".md"}

    def __init__(self, encodings: Optional[list[str]] = None) -> None:
        self.encodings = encodings or ["utf-8-sig", "utf-8", "gb18030", "gbk", "utf-16"]

    def load(self, file_path: str | Path) -> Document:
        path = self._validate_file(file_path)
        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported text format: {path.suffix}")

        doc_hash = self._compute_file_hash(path)
        doc_id = f"doc_{doc_hash[:16]}"
        text_content = self._read_text(path)
        metadata: Dict[str, Any] = {
            "source_path": str(path),
            "doc_type": "markdown" if ext == ".md" else "text",
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

    def _read_text(self, path: Path) -> str:
        last_error: Exception | None = None
        for encoding in self.encodings:
            try:
                text = path.read_text(encoding=encoding)
                return text if text.strip() else self._fallback_empty(path)
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise RuntimeError(f"Failed to read text file {path}: {last_error}") from last_error
        return self._fallback_empty(path)

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

    def _fallback_empty(self, path: Path) -> str:
        return f"[空文本文件：{path.name}]"
