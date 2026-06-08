"""Image/Screenshot Loader with dual-channel processing.

This module implements loading of screenshots and photos as documents:
- Channel 1: Stores the image file in the image storage directory
- Channel 2: Uses Vision LLM to generate a detailed text description
  that becomes searchable via RAG

Features:
- Vision LLM-based image description for search indexing
- Image file storage with metadata tracking
- Graceful degradation if Vision LLM is unavailable
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

from src.core.types import Document
from src.libs.loader.base_loader import BaseLoader
from src.libs.llm.base_vision_llm import BaseVisionLLM, ImageInput

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

# Default prompt for Vision LLM image description
DEFAULT_IMAGE_DESCRIPTION_PROMPT = (
    "请详细描述这张图片的内容。如果是课堂笔记、板书、PPT截图或教科书页面，"
    "请提取其中的所有文字、公式、图表信息、关键概念和知识点。"
    "请用中文回答，尽可能详细和准确，以便后续用于知识检索。"
)


class ImageLoader(BaseLoader):
    """Image/Screenshot Loader with dual-channel processing.

    This loader processes images (screenshots, photos, notes) as documents:
    1. Stores the image file in the image storage directory
    2. Uses Vision LLM to generate a detailed text description
    3. The description becomes the Document.text, making the image searchable

    Graceful Degradation:
        If Vision LLM is unavailable, stores a minimal description
        (filename, dimensions) and logs warning.
    """

    def __init__(
        self,
        vision_llm: Optional[BaseVisionLLM] = None,
        image_storage_dir: str | Path = "data/images",
        prompt: Optional[str] = None,
        extract_images: bool = True,
    ):
        self.vision_llm = vision_llm
        self.image_storage_dir = Path(image_storage_dir)
        self.prompt = prompt or DEFAULT_IMAGE_DESCRIPTION_PROMPT

    def load(self, file_path: str | Path) -> Document:
        path = self._validate_file(file_path)
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported image format: {path.suffix}")

        doc_hash = self._compute_file_hash(path)
        doc_id = f"doc_{doc_hash[:16]}"

        # Channel 1: Store image file
        stored_image_path = self._store_image(path, doc_hash)

        # Get image dimensions
        try:
            with Image.open(path) as img:
                width, height = img.size
        except Exception:
            width, height = 0, 0

        # Channel 2: Generate text description via Vision LLM
        text_content = self._generate_description(path)

        image_id = f"{doc_hash[:8]}_screenshot_1"
        placeholder = f"[IMAGE: {image_id}]"
        full_text = f"{text_content}\n\n{placeholder}"

        try:
            relative_path = stored_image_path.relative_to(Path.cwd())
        except ValueError:
            relative_path = stored_image_path.absolute()

        images_metadata = [
            {
                "id": image_id,
                "path": str(relative_path),
                "page": 1,
                "text_offset": len(text_content) + 2,
                "text_length": len(placeholder),
                "position": {
                    "width": width,
                    "height": height,
                    "page": 1,
                    "index": 0,
                },
            }
        ]

        metadata: Dict[str, Any] = {
            "source_path": str(path),
            "doc_type": "image",
            "doc_hash": doc_hash,
            "title": path.stem,
            "images": images_metadata,
        }

        return Document(id=doc_id, text=full_text, metadata=metadata)

    def _compute_file_hash(self, file_path: Path) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _store_image(self, source_path: Path, doc_hash: str) -> Path:
        ext = source_path.suffix.lower()
        image_dir = self.image_storage_dir / doc_hash
        image_dir.mkdir(parents=True, exist_ok=True)

        image_filename = f"{doc_hash[:8]}_screenshot_1{ext}"
        dest_path = image_dir / image_filename
        shutil.copy2(source_path, dest_path)
        logger.info(f"Stored image at {dest_path}")
        return dest_path

    def _generate_description(self, image_path: Path) -> str:
        if self.vision_llm is None:
            logger.warning("Vision LLM not available, using minimal description")
            return self._minimal_description(image_path)

        try:
            image_input = ImageInput(path=str(image_path))
            response = self.vision_llm.chat_with_image(
                text=self.prompt,
                image=image_input,
            )
            content = response.content if hasattr(response, "content") else str(response)
            if content and content.strip():
                return content.strip()
            logger.warning("Vision LLM returned empty response, using minimal description")
            return self._minimal_description(image_path)
        except Exception as e:
            logger.warning(f"Vision LLM failed: {e}, using minimal description")
            return self._minimal_description(image_path)

    def _minimal_description(self, image_path: Path) -> str:
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                fmt = img.format or "unknown"
            return f"图片文件: {image_path.name}, 格式: {fmt}, 尺寸: {width}x{height}"
        except Exception:
            return f"图片文件: {image_path.name}"
