"""PDF Loader implementation using MarkItDown.

This module implements PDF parsing with image extraction support,
converting PDFs to standardized Markdown format with image placeholders.

Features:
- Text extraction and Markdown conversion via MarkItDown
- Image extraction and storage
- Image placeholder insertion with metadata tracking
- Graceful degradation if image extraction fails
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from markitdown import MarkItDown
    MARKITDOWN_AVAILABLE = True
except ImportError:
    MARKITDOWN_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

from PIL import Image
import io

from src.core.types import Document
from src.libs.loader.base_loader import BaseLoader
from src.libs.ocr.rapidocr_engine import OCRBlock, OCRUnavailableError, RapidOCREngine

logger = logging.getLogger(__name__)


class PdfLoader(BaseLoader):
    """PDF Loader using MarkItDown for text extraction and Markdown conversion.

    This loader:
    1. Extracts text from PDF and converts to Markdown
    2. Extracts images and saves to data/images/{doc_hash}/
    3. Inserts image placeholders in the format [IMAGE: {image_id}]
    4. Records image metadata in Document.metadata.images

    Configuration:
        extract_images: Enable/disable image extraction (default: True)
        image_storage_dir: Base directory for image storage (default: data/images)

    Graceful Degradation:
        If image extraction fails, logs warning and continues with text-only parsing.
    """

    def __init__(
        self,
        extract_images: bool = True,
        image_storage_dir: str | Path = "data/images",
        ocr_settings: Any | None = None,
    ):
        """Initialize PDF Loader.

        Args:
            extract_images: Whether to extract images from PDFs.
            image_storage_dir: Base directory for storing extracted images.
        """
        if not MARKITDOWN_AVAILABLE:
            raise ImportError(
                "MarkItDown is required for PdfLoader. "
                "Install with: pip install markitdown"
            )

        self.extract_images = extract_images
        self.image_storage_dir = Path(image_storage_dir)
        self._markitdown = MarkItDown()
        self.ocr_mode = str(getattr(ocr_settings, "mode", "auto") or "auto").lower()
        self.ocr_provider = str(getattr(ocr_settings, "provider", "rapidocr") or "rapidocr").lower()
        self.ocr_dpi = int(getattr(ocr_settings, "dpi", 180) or 180)
        self.ocr_min_text_chars_per_page = int(
            getattr(ocr_settings, "min_text_chars_per_page", 30) or 0
        )
        self.ocr_max_pages = getattr(ocr_settings, "max_pages", None)
        self._ocr_engine: RapidOCREngine | None = None

    def load(self, file_path: str | Path) -> Document:
        """Load and parse a PDF file.

        Args:
            file_path: Path to the PDF file.

        Returns:
            Document with Markdown text and metadata.

        Raises:
            FileNotFoundError: If the PDF file doesn't exist.
            ValueError: If the file is not a valid PDF.
            RuntimeError: If parsing fails critically.
        """
        # Validate file
        path = self._validate_file(file_path)
        if path.suffix.lower() != '.pdf':
            raise ValueError(f"File is not a PDF: {path}")

        # Compute document hash for unique ID and image directory
        doc_hash = self._compute_file_hash(path)
        doc_id = f"doc_{doc_hash[:16]}"

        # Parse PDF with MarkItDown
        try:
            result = self._markitdown.convert(str(path))
            text_content = result.text_content if hasattr(result, 'text_content') else str(result)
        except Exception as e:
            logger.error(f"Failed to parse PDF {path}: {e}")
            raise RuntimeError(f"PDF parsing failed: {e}") from e

        # Initialize metadata
        metadata: Dict[str, Any] = {
            "source_path": str(path),
            "doc_type": "pdf",
            "doc_hash": doc_hash,
        }

        page_infos = self._collect_page_infos(path)
        if page_infos:
            metadata["page_count"] = len(page_infos)

        text_content, ocr_metadata = self._apply_ocr_fallback(
            path,
            text_content,
            page_infos,
        )
        metadata.update(ocr_metadata)

        # Extract title from first heading if available
        title = self._extract_title(text_content)
        metadata["title"] = title or path.stem

        # Handle image extraction (with graceful degradation)
        if self.extract_images:
            try:
                text_content, images_metadata = self._extract_and_process_images(
                    path, text_content, doc_hash
                )
                if images_metadata:
                    metadata["images"] = images_metadata
            except Exception as e:
                logger.warning(
                    f"Image extraction failed for {path}, continuing with text-only: {e}"
                )

        return Document(
            id=doc_id,
            text=text_content,
            metadata=metadata
        )

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of file content.

        Args:
            file_path: Path to file.

        Returns:
            Hex string of SHA256 hash.
        """
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _extract_title(self, text: str) -> Optional[str]:
        """Extract title from first Markdown heading or first non-empty line.

        Args:
            text: Markdown text content.

        Returns:
            Title string if found, None otherwise.
        """
        lines = text.split('\n')

        def _looks_synthetic(value: str) -> bool:
            stripped = value.strip()
            return (
                stripped.startswith("[PDF文本提取为空")
                or stripped.startswith("# OCR 补充内容")
                or stripped.startswith("## OCR Page")
            )

        # First try to find a markdown heading
        for line in lines[:20]:  # Check first 20 lines
            line = line.strip()
            if line.startswith('# ') and not _looks_synthetic(line):
                return line[2:].strip()

        # Fallback: use first non-empty line as title
        for line in lines[:10]:
            line = line.strip()
            if line and len(line) > 0 and not _looks_synthetic(line):
                return line

        return None

    def _collect_page_infos(self, pdf_path: Path) -> list[dict[str, Any]]:
        if not PYMUPDF_AVAILABLE:
            logger.warning("PyMuPDF not available, OCR page detection is disabled")
            return []

        try:
            doc = fitz.open(pdf_path)
        except Exception as exc:
            logger.warning("Failed to open PDF for page inspection: %s", exc)
            return []

        try:
            page_infos: list[dict[str, Any]] = []
            for index in range(len(doc)):
                page = doc[index]
                try:
                    native_text = page.get_text("text") or ""
                except Exception:
                    native_text = ""
                page_infos.append(
                    {
                        "page_num": index + 1,
                        "native_text_chars": len(native_text.strip()),
                        "image_count": len(page.get_images(full=True)),
                    }
                )
            return page_infos
        finally:
            doc.close()

    def _apply_ocr_fallback(
        self,
        pdf_path: Path,
        text_content: str,
        page_infos: list[dict[str, Any]],
    ) -> tuple[str, dict[str, Any]]:
        metadata: dict[str, Any] = {
            "ocr_used": False,
            "ocr_provider": self.ocr_provider,
            "ocr_pages": [],
            "ocr_blocks": [],
        }

        if self.ocr_mode == "off":
            return self._ensure_non_empty_text(text_content), metadata

        if self.ocr_provider != "rapidocr":
            logger.warning("Unsupported OCR provider '%s'; skipping OCR", self.ocr_provider)
            return self._ensure_non_empty_text(text_content), metadata

        if not PYMUPDF_AVAILABLE:
            return self._ensure_non_empty_text(text_content), metadata

        target_pages = self._select_ocr_pages(page_infos)
        if not target_pages:
            return self._ensure_non_empty_text(text_content), metadata

        try:
            engine = self._get_ocr_engine()
            engine.ensure_loaded()
        except OCRUnavailableError as exc:
            logger.warning("%s", exc)
            return self._ensure_non_empty_text(text_content), metadata

        pages_metadata: list[dict[str, Any]] = []
        all_blocks: list[OCRBlock] = []
        doc = fitz.open(pdf_path)
        try:
            for page_info in target_pages:
                page_num = int(page_info["page_num"])
                try:
                    page = doc[page_num - 1]
                    image = self._render_page(page)
                    blocks = engine.recognize(image, page_num=page_num)
                except Exception as exc:
                    logger.warning("OCR failed for page %s in %s: %s", page_num, pdf_path, exc)
                    blocks = []

                all_blocks.extend(blocks)
                pages_metadata.append(
                    {
                        "page_num": page_num,
                        "native_text_chars": page_info.get("native_text_chars", 0),
                        "image_count": page_info.get("image_count", 0),
                        "ocr_block_count": len(blocks),
                    }
                )
        finally:
            doc.close()

        block_dicts = [block.to_dict() for block in all_blocks]
        metadata.update(
            {
                "ocr_used": bool(target_pages),
                "ocr_pages": pages_metadata,
                "ocr_blocks": block_dicts,
            }
        )

        ocr_markdown = self._build_ocr_markdown(all_blocks)
        if ocr_markdown:
            if text_content.strip():
                text_content = f"{text_content.rstrip()}\n\n---\n\n# OCR 补充内容\n\n{ocr_markdown}"
            else:
                text_content = ocr_markdown

        return self._ensure_non_empty_text(text_content), metadata

    def _select_ocr_pages(self, page_infos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not page_infos:
            return []

        selected: list[dict[str, Any]] = []
        for page_info in page_infos:
            if self.ocr_max_pages is not None and len(selected) >= int(self.ocr_max_pages):
                break

            native_chars = int(page_info.get("native_text_chars", 0) or 0)
            should_ocr = self.ocr_mode == "always" or (
                self.ocr_mode == "auto"
                and native_chars < self.ocr_min_text_chars_per_page
            )
            if should_ocr:
                selected.append(page_info)
        return selected

    def _get_ocr_engine(self) -> RapidOCREngine:
        if self._ocr_engine is None:
            self._ocr_engine = RapidOCREngine()
        return self._ocr_engine

    def _render_page(self, page: Any) -> Image.Image:
        zoom = max(self.ocr_dpi, 1) / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        mode = "RGB" if pix.n < 4 else "RGBA"
        return Image.frombytes(mode, (pix.width, pix.height), pix.samples).convert("RGB")

    def _build_ocr_markdown(self, blocks: list[OCRBlock]) -> str:
        blocks_by_page: dict[int, list[OCRBlock]] = {}
        for block in blocks:
            blocks_by_page.setdefault(block.page_num, []).append(block)

        sections: list[str] = []
        for page_num in sorted(blocks_by_page):
            lines = [block.text for block in blocks_by_page[page_num] if block.text.strip()]
            if lines:
                sections.append(f"## OCR Page {page_num}\n\n" + "\n".join(lines))
        return "\n\n".join(sections).strip()

    def _ensure_non_empty_text(self, text: str) -> str:
        if text and text.strip():
            return text
        return "[PDF文本提取为空；如果这是扫描件或拍照PDF，请安装 OCR 可选依赖后重新上传。]"

    def _extract_and_process_images(
        self,
        pdf_path: Path,
        text_content: str,
        doc_hash: str
    ) -> tuple[str, List[Dict[str, Any]]]:
        """Extract images from PDF and insert placeholders.

        Uses PyMuPDF to extract images, save them to disk, and insert
        placeholders in the text content.

        Args:
            pdf_path: Path to PDF file.
            text_content: Extracted text content.
            doc_hash: Document hash for image directory.

        Returns:
            Tuple of (modified_text, images_metadata_list)
        """
        if not self.extract_images:
            logger.debug(f"Image extraction disabled for {pdf_path}")
            return text_content, []

        if not PYMUPDF_AVAILABLE:
            logger.warning(f"PyMuPDF not available, skipping image extraction for {pdf_path}")
            return text_content, []

        images_metadata = []
        modified_text = text_content

        try:
            # Create image storage directory
            image_dir = self.image_storage_dir / doc_hash
            image_dir.mkdir(parents=True, exist_ok=True)

            # Open PDF with PyMuPDF
            doc = fitz.open(pdf_path)

            # Track text offset for placeholder insertion
            text_offset = 0

            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images(full=True)

                for img_index, img_info in enumerate(image_list):
                    try:
                        # Extract image
                        xref = img_info[0]
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]

                        # Generate image ID and filename
                        image_id = self._generate_image_id(doc_hash, page_num + 1, img_index + 1)
                        image_filename = f"{image_id}.{image_ext}"
                        image_path = image_dir / image_filename

                        # Save image
                        with open(image_path, "wb") as img_file:
                            img_file.write(image_bytes)

                        # Get image dimensions
                        try:
                            img = Image.open(io.BytesIO(image_bytes))
                            width, height = img.size
                        except Exception:
                            width, height = 0, 0

                        # Create placeholder
                        placeholder = f"[IMAGE: {image_id}]"

                        # Insert placeholder at end of current page's content
                        # (simplified - in production, you'd parse page boundaries)
                        insert_position = len(modified_text)
                        modified_text += f"\n{placeholder}\n"

                        # Convert path to be relative to project root or absolute
                        try:
                            relative_path = image_path.relative_to(Path.cwd())
                        except ValueError:
                            # If not in cwd, use absolute path
                            relative_path = image_path.absolute()

                        # Record metadata
                        image_metadata = {
                            "id": image_id,
                            "path": str(relative_path),
                            "page": page_num + 1,
                            "text_offset": insert_position + 1,  # +1 for newline
                            "text_length": len(placeholder),
                            "position": {
                                "width": width,
                                "height": height,
                                "page": page_num + 1,
                                "index": img_index
                            }
                        }
                        images_metadata.append(image_metadata)

                        logger.debug(f"Extracted image {image_id} from page {page_num + 1}")

                    except Exception as e:
                        logger.warning(f"Failed to extract image {img_index} from page {page_num + 1}: {e}")
                        continue

            doc.close()

            if images_metadata:
                logger.info(f"Extracted {len(images_metadata)} images from {pdf_path}")
            else:
                logger.debug(f"No images found in {pdf_path}")

            return modified_text, images_metadata

        except Exception as e:
            logger.warning(f"Image extraction failed for {pdf_path}: {e}")
            # Graceful degradation: return original text without images
            return text_content, []

    @staticmethod
    def _generate_image_id(doc_hash: str, page: int, sequence: int) -> str:
        """Generate unique image ID.

        Args:
            doc_hash: Document hash.
            page: Page number (0-based).
            sequence: Image sequence on page (0-based).

        Returns:
            Unique image ID string.
        """
        return f"{doc_hash[:8]}_{page}_{sequence}"
