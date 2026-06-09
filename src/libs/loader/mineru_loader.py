"""MinerU-backed PDF loader.

This loader makes MinerU the preferred PDF parser while keeping the rest of
the ingestion contract unchanged: loaders return a single ``Document`` with
Markdown-like text and optional image metadata.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shlex
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from src.core.types import Document
from src.libs.loader.base_loader import BaseLoader

logger = logging.getLogger(__name__)


class MinerULoader(BaseLoader):
    """PDF loader using a local MinerU CLI as the primary parser.

    The loader looks for either ``mineru`` or ``magic-pdf`` on PATH. A custom
    command can be supplied through ``mineru_command`` or the ``MINERU_COMMAND``
    environment variable.
    """

    SUPPORTED_EXTENSIONS = {".pdf"}
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}

    def __init__(
        self,
        extract_images: bool = True,
        image_storage_dir: str | Path = "data/images",
        mineru_output_root: str | Path = "data/mineru",
        mineru_command: Optional[str] = None,
        mineru_language: Optional[str] = None,
        fallback_to_legacy: bool = True,
        ocr_settings: Any | None = None,
        **_: Any,
    ) -> None:
        self.extract_images = extract_images
        self.image_storage_dir = Path(image_storage_dir)
        self.output_root = Path(mineru_output_root)
        self.mineru_command = mineru_command or os.environ.get("MINERU_COMMAND")
        self.mineru_language = mineru_language or os.environ.get("MINERU_LANG")
        self.fallback_to_legacy = fallback_to_legacy
        self.ocr_settings = ocr_settings

    def load(self, file_path: str | Path) -> Document:
        path = self._validate_file(file_path)
        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported PDF format: {path.suffix}")

        doc_hash = self._compute_file_hash(path)
        output_dir = self.output_root / doc_hash
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            command_used = self._run_mineru(path, output_dir)
            text_content = self._load_markdown(output_dir)
            content_items = self._load_content_list(output_dir)
            if not text_content.strip():
                text_content = self._build_text_from_content_list(content_items)
            if not text_content.strip():
                raise RuntimeError("MinerU produced no readable Markdown or content list text")
        except Exception as exc:
            if not self.fallback_to_legacy:
                raise RuntimeError(f"MinerU PDF parsing failed for {path}: {exc}") from exc
            logger.warning("MinerU parsing failed for %s; falling back to legacy PdfLoader: %s", path, exc)
            return self._fallback_load(path)

        metadata: Dict[str, Any] = {
            "source_path": str(path),
            "doc_type": "pdf",
            "doc_hash": doc_hash,
            "title": self._extract_title(text_content) or path.stem,
            "parser": "mineru",
            "mineru_output_dir": str(output_dir),
            "mineru_command": command_used,
        }

        page_count = self._infer_page_count(content_items)
        if page_count:
            metadata["page_count"] = page_count

        if self.extract_images:
            images = self._collect_image_metadata(content_items, output_dir, doc_hash)
            if not images:
                images = self._collect_image_files(output_dir, doc_hash)
            if images:
                metadata["images"] = images

        return Document(id=f"doc_{doc_hash[:16]}", text=text_content, metadata=metadata)

    def _run_mineru(self, pdf_path: Path, output_dir: Path) -> str:
        last_error = ""
        args = ["-p", str(pdf_path), "-o", str(output_dir), "-m", "auto"]
        if self.mineru_language:
            args.extend(["--lang", self.mineru_language])

        for command in self._candidate_commands():
            try:
                completed = subprocess.run(
                    [*command, *args],
                    capture_output=True,
                    check=True,
                    text=True,
                )
                if completed.stderr:
                    logger.debug("MinerU stderr: %s", completed.stderr.strip())
                return " ".join(command)
            except FileNotFoundError as exc:
                last_error = str(exc)
                continue
            except subprocess.CalledProcessError as exc:
                last_error = (exc.stderr or exc.stdout or str(exc)).strip()
                logger.warning("MinerU command failed (%s): %s", " ".join(command), last_error)
                continue

        raise RuntimeError(last_error or "MinerU command not found")

    def _candidate_commands(self) -> list[list[str]]:
        if self.mineru_command:
            return [shlex.split(self.mineru_command)]
        return [["mineru"], ["magic-pdf"]]

    def _load_markdown(self, output_dir: Path) -> str:
        markdown_file = self._find_latest_file(output_dir, lambda p: p.suffix.lower() == ".md")
        if markdown_file is None:
            return ""
        return markdown_file.read_text(encoding="utf-8", errors="ignore").strip()

    def _load_content_list(self, output_dir: Path) -> list[dict[str, Any]]:
        content_file = self._find_latest_file(
            output_dir,
            lambda p: p.suffix.lower() == ".json" and "content_list" in p.name.lower(),
        )
        if content_file is None:
            return []
        try:
            data = json.loads(content_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to read MinerU content list %s: %s", content_file, exc)
            return []
        return list(self._flatten_dicts(data))

    def _build_text_from_content_list(self, content_items: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for item in content_items:
            text = item.get("text") or item.get("content")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
        return "\n\n".join(parts)

    def _collect_image_metadata(
        self,
        content_items: list[dict[str, Any]],
        output_dir: Path,
        doc_hash: str,
    ) -> list[dict[str, Any]]:
        images: list[dict[str, Any]] = []
        sequence_by_page: dict[int, int] = defaultdict(int)

        for item in content_items:
            source = self._extract_image_path_value(item)
            if not source:
                continue

            source_path = self._resolve_output_path(output_dir, source)
            if source_path is None:
                continue

            page_num = self._page_num(item)
            sequence_key = page_num or 0
            sequence_by_page[sequence_key] += 1
            image_id = f"{doc_hash[:8]}_{page_num or 1}_{sequence_by_page[sequence_key]}"
            stored_path = self._copy_image(source_path, doc_hash, image_id)

            image_metadata: dict[str, Any] = {
                "id": image_id,
                "path": self._display_path(stored_path),
                "page": page_num,
                "position": {
                    "page": page_num,
                    "source": str(source),
                },
            }
            caption = item.get("caption") or item.get("description") or item.get("text")
            if isinstance(caption, str) and caption.strip():
                image_metadata["caption"] = caption.strip()
            images.append(image_metadata)

        return images

    def _collect_image_files(self, output_dir: Path, doc_hash: str) -> list[dict[str, Any]]:
        images: list[dict[str, Any]] = []
        for index, source_path in enumerate(self._iter_image_files(output_dir), start=1):
            image_id = f"{doc_hash[:8]}_1_{index}"
            stored_path = self._copy_image(source_path, doc_hash, image_id)
            images.append(
                {
                    "id": image_id,
                    "path": self._display_path(stored_path),
                    "page": None,
                    "position": {"page": None, "source": str(source_path)},
                }
            )
        return images

    def _copy_image(self, source_path: Path, doc_hash: str, image_id: str) -> Path:
        image_dir = self.image_storage_dir / doc_hash
        image_dir.mkdir(parents=True, exist_ok=True)
        extension = source_path.suffix.lower() or ".png"
        target_path = image_dir / f"{image_id}{extension}"
        if source_path.resolve() != target_path.resolve():
            shutil.copy2(source_path, target_path)
        return target_path

    def _fallback_load(self, path: Path) -> Document:
        from src.libs.loader.pdf_loader import PdfLoader

        loader = PdfLoader(
            extract_images=self.extract_images,
            image_storage_dir=self.image_storage_dir,
            ocr_settings=self.ocr_settings,
        )
        document = loader.load(path)
        document.metadata["parser"] = "legacy_pdf_loader"
        document.metadata["mineru_fallback"] = True
        return document

    def _compute_file_hash(self, file_path: Path) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _extract_title(self, text: str) -> Optional[str]:
        for line in text.splitlines()[:20]:
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
        for line in text.splitlines()[:20]:
            stripped = line.strip()
            if stripped and not stripped.startswith("!"):
                return stripped[:120]
        return None

    def _infer_page_count(self, content_items: list[dict[str, Any]]) -> Optional[int]:
        pages = [self._page_num(item) for item in content_items]
        pages = [page for page in pages if page is not None]
        return max(pages) if pages else None

    def _extract_image_path_value(self, item: dict[str, Any]) -> Optional[str]:
        item_type = str(item.get("type", "")).lower()
        candidates = [
            item.get("img_path"),
            item.get("image_path"),
            item.get("image"),
            item.get("path"),
        ]
        for value in candidates:
            if isinstance(value, str) and self._looks_like_image_path(value):
                return value
        if item_type in {"image", "figure"}:
            for value in candidates:
                if isinstance(value, str) and value.strip():
                    return value
        return None

    def _resolve_output_path(self, output_dir: Path, value: str) -> Optional[Path]:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = output_dir / candidate
        if candidate.exists():
            return candidate.resolve()

        filename = Path(value).name
        if not filename:
            return None
        for match in output_dir.rglob(filename):
            if match.is_file():
                return match.resolve()
        return None

    def _iter_image_files(self, output_dir: Path) -> Iterable[Path]:
        for path in output_dir.rglob("*"):
            if path.is_file() and path.suffix.lower() in self.IMAGE_EXTENSIONS:
                yield path

    def _page_num(self, item: dict[str, Any]) -> Optional[int]:
        for key in ("page_idx", "page_num", "page"):
            value = item.get(key)
            if value is None:
                continue
            try:
                page = int(value)
            except (TypeError, ValueError):
                continue
            return page + 1 if key == "page_idx" else page
        return None

    def _looks_like_image_path(self, value: str) -> bool:
        return Path(value).suffix.lower() in self.IMAGE_EXTENSIONS

    def _display_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(Path.cwd()))
        except ValueError:
            return str(path.resolve())

    def _find_latest_file(self, output_dir: Path, predicate: Any) -> Optional[Path]:
        matches = [path for path in output_dir.rglob("*") if path.is_file() and predicate(path)]
        if not matches:
            return None
        return max(matches, key=lambda path: path.stat().st_mtime)

    def _flatten_dicts(self, value: Any) -> Iterable[dict[str, Any]]:
        if isinstance(value, dict):
            yield value
            for child in value.values():
                if isinstance(child, (list, dict)):
                    yield from self._flatten_dicts(child)
        elif isinstance(value, list):
            for child in value:
                yield from self._flatten_dicts(child)
