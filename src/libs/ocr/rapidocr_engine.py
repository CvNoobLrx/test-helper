"""RapidOCR adapter for lightweight ONNXRuntime OCR.

The dependency is optional. Import errors are raised only when OCR is actually
requested, so normal PDF ingestion keeps working without the OCR extra.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Iterable, Sequence

from PIL import Image

logger = logging.getLogger(__name__)


class OCRUnavailableError(RuntimeError):
    """Raised when the optional OCR backend is not installed or cannot start."""


@dataclass(frozen=True)
class OCRBlock:
    id: str
    page_num: int
    bbox: list[list[float]]
    text: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "page_num": self.page_num,
            "bbox": self.bbox,
            "text": self.text,
            "score": self.score,
        }


class RapidOCREngine:
    """Thin wrapper around RapidOCR with a stable return shape."""

    def __init__(
        self,
        *,
        model_version: str = "PP-OCRv5",
        model_type: str = "mobile",
        lang: str = "ch",
    ) -> None:
        self.model_version = model_version
        self.model_type = model_type
        self.lang = lang
        self._engine: Any = None

    def recognize(self, image: Image.Image, page_num: int) -> list[OCRBlock]:
        engine = self._load_engine()
        try:
            import numpy as np

            input_image = np.asarray(image.convert("RGB"))
            raw_result = engine(input_image)
        except Exception as exc:
            raise RuntimeError(f"RapidOCR recognition failed: {exc}") from exc

        parsed = self._parse_result(raw_result)
        parsed.sort(key=lambda item: (_bbox_top(item[0]), _bbox_left(item[0])))

        blocks: list[OCRBlock] = []
        for index, (bbox, text, score) in enumerate(parsed, start=1):
            clean_text = str(text or "").strip()
            if not clean_text:
                continue
            blocks.append(
                OCRBlock(
                    id=f"ocr_p{page_num}_{index:03d}",
                    page_num=page_num,
                    bbox=_normalize_bbox(bbox),
                    text=clean_text,
                    score=float(score or 0.0),
                )
            )
        return blocks

    def ensure_loaded(self) -> None:
        self._load_engine()

    def _load_engine(self) -> Any:
        if self._engine is not None:
            return self._engine

        try:
            import rapidocr as rapidocr_module
            RapidOCR = rapidocr_module.RapidOCR
            EngineType = getattr(rapidocr_module, "EngineType", None)
            LangDet = getattr(rapidocr_module, "LangDet", None)
            LangRec = getattr(rapidocr_module, "LangRec", None)
            ModelType = getattr(rapidocr_module, "ModelType", None)
            OCRVersion = getattr(rapidocr_module, "OCRVersion", None)
        except ImportError as exc:
            try:
                from rapidocr_onnxruntime import RapidOCR  # type: ignore[no-redef]
            except ImportError:
                raise OCRUnavailableError(
                    "RapidOCR is not installed. Install optional OCR dependencies with "
                    "`python -m pip install -r requirements-ocr.txt`."
                ) from exc

        params = self._ppocrv5_params(
            engine_type=locals().get("EngineType"),
            lang_det=locals().get("LangDet"),
            lang_rec=locals().get("LangRec"),
            model_type=locals().get("ModelType"),
            ocr_version=locals().get("OCRVersion"),
        )
        try:
            self._engine = RapidOCR(params=params)
        except TypeError:
            logger.warning("RapidOCR version does not accept params; falling back to default models")
            self._engine = RapidOCR()
        except Exception as exc:
            logger.warning("RapidOCR PP-OCRv5 init failed, falling back to defaults: %s", exc)
            try:
                self._engine = RapidOCR()
            except Exception as fallback_exc:
                raise OCRUnavailableError(f"RapidOCR could not start: {fallback_exc}") from fallback_exc

        return self._engine

    def _ppocrv5_params(
        self,
        *,
        engine_type: Any | None = None,
        lang_det: Any | None = None,
        lang_rec: Any | None = None,
        model_type: Any | None = None,
        ocr_version: Any | None = None,
    ) -> dict[str, Any]:
        engine_type_value = _enum_member(engine_type, "ONNXRUNTIME", "onnxruntime")
        lang_det_value = _enum_member(lang_det, "CH", self.lang)
        lang_rec_value = _enum_member(lang_rec, "CH", self.lang)
        model_type_value = _enum_member(model_type, "MOBILE", self.model_type)
        ocr_version_value = _enum_member(ocr_version, "PPOCRV5", self.model_version)

        return {
            "Det.engine_type": engine_type_value,
            "Det.lang_type": lang_det_value,
            "Det.model_type": model_type_value,
            "Det.ocr_version": ocr_version_value,
            "Rec.engine_type": engine_type_value,
            "Rec.lang_type": lang_rec_value,
            "Rec.model_type": model_type_value,
            "Rec.ocr_version": ocr_version_value,
        }

    def _parse_result(self, raw_result: Any) -> list[tuple[Any, str, float]]:
        if raw_result is None:
            return []

        result = raw_result
        if isinstance(raw_result, tuple) and raw_result:
            result = raw_result[0]

        boxes = getattr(result, "boxes", None)
        texts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        if boxes is not None and texts is not None:
            return [
                (box, str(text), _score_at(scores, index))
                for index, (box, text) in enumerate(zip(boxes, texts))
            ]

        if isinstance(result, list):
            parsed: list[tuple[Any, str, float]] = []
            for item in result:
                if isinstance(item, (list, tuple)) and len(item) >= 3:
                    parsed.append((item[0], str(item[1]), float(item[2] or 0.0)))
            return parsed

        return []


def _score_at(scores: Any, index: int) -> float:
    try:
        return float(scores[index])
    except Exception:
        return 0.0


def _enum_member(enum_cls: Any, member_name: str, fallback: Any) -> Any:
    if enum_cls is None:
        return fallback

    candidate = getattr(enum_cls, member_name, None)
    if candidate is not None:
        return candidate

    try:
        return enum_cls(fallback)
    except Exception:
        return fallback


def _normalize_bbox(bbox: Any) -> list[list[float]]:
    if hasattr(bbox, "tolist"):
        bbox = bbox.tolist()
    if not isinstance(bbox, Sequence):
        return []

    points: list[list[float]] = []
    for point in bbox:
        if hasattr(point, "tolist"):
            point = point.tolist()
        if isinstance(point, Sequence) and len(point) >= 2:
            try:
                points.append([float(point[0]), float(point[1])])
            except (TypeError, ValueError):
                continue
    return points


def _bbox_top(bbox: Any) -> float:
    points = _iter_points(bbox)
    ys = [point[1] for point in points]
    return min(ys) if ys else 0.0


def _bbox_left(bbox: Any) -> float:
    points = _iter_points(bbox)
    xs = [point[0] for point in points]
    return min(xs) if xs else 0.0


def _iter_points(bbox: Any) -> Iterable[tuple[float, float]]:
    for point in _normalize_bbox(bbox):
        if len(point) >= 2:
            yield point[0], point[1]
