"""Factory for document loaders based on file extension.

Maps file extensions to the appropriate loader class,
following the same Factory pattern as EmbeddingFactory.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional, Type

from src.libs.loader.base_loader import BaseLoader

logger = logging.getLogger(__name__)

# Extension -> loader class mapping
_LOADER_REGISTRY: Dict[str, Type[BaseLoader]] = {}


def _register_builtin_loaders() -> None:
    """Register built-in loader providers at module load time."""
    from src.libs.loader.pdf_loader import PdfLoader

    for ext in (".pdf",):
        _LOADER_REGISTRY[ext] = PdfLoader

    try:
        from src.libs.loader.ppt_loader import PptLoader
        for ext in PptLoader.SUPPORTED_EXTENSIONS:
            _LOADER_REGISTRY[ext] = PptLoader
    except ImportError:
        logger.debug("PptLoader not available (python-pptx not installed)")

    try:
        from src.libs.loader.image_loader import ImageLoader, SUPPORTED_EXTENSIONS
        for ext in SUPPORTED_EXTENSIONS:
            _LOADER_REGISTRY[ext] = ImageLoader
    except ImportError:
        logger.debug("ImageLoader not available")


_register_builtin_loaders()


class LoaderFactory:
    """Factory for creating document loaders based on file extension.

    Usage:
        loader = LoaderFactory.create("report.pptx", image_storage_dir="data/images")
        doc = loader.load("report.pptx")
    """

    _EXTENSION_MAP: Dict[str, Type[BaseLoader]] = _LOADER_REGISTRY

    @classmethod
    def create(
        cls,
        file_path: str | Path,
        **kwargs,
    ) -> BaseLoader:
        """Create a loader appropriate for the given file extension.

        Args:
            file_path: Path to the file (extension determines loader type).
            **kwargs: Passed to the loader constructor.

        Returns:
            An instance of the appropriate loader.

        Raises:
            ValueError: If the file extension is not supported.
        """
        ext = Path(file_path).suffix.lower()
        loader_cls = cls._EXTENSION_MAP.get(ext)

        if loader_cls is None:
            supported = ", ".join(sorted(cls._EXTENSION_MAP.keys()))
            raise ValueError(
                f"No loader registered for extension '{ext}'. "
                f"Supported extensions: {supported}"
            )

        logger.info(f"Creating {loader_cls.__name__} for {ext} files")
        return loader_cls(**kwargs)

    @classmethod
    def register(cls, extension: str, loader_class: Type[BaseLoader]) -> None:
        """Register a loader for a given file extension.

        Args:
            extension: File extension including the dot (e.g., '.docx').
            loader_class: Loader class to use for this extension.
        """
        if not issubclass(loader_class, BaseLoader):
            raise TypeError(f"{loader_class} must be a subclass of BaseLoader")
        cls._EXTENSION_MAP[extension.lower()] = loader_class
        logger.info(f"Registered {loader_class.__name__} for {extension}")

    @classmethod
    def list_extensions(cls) -> list[str]:
        """Return sorted list of supported file extensions."""
        return sorted(cls._EXTENSION_MAP.keys())
