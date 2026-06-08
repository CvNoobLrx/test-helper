"""ONNX Runtime embedding provider for lightweight deployments."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

import numpy as np

from src.libs.embedding.base_embedding import BaseEmbedding


class OnnxEmbeddingError(RuntimeError):
    """Raised when ONNX embedding inference fails."""


class OnnxEmbedding(BaseEmbedding):
    """Embedding provider backed by Hugging Face ONNX encoder models.

    The default path convention expects an ONNX file under ``onnx/model.onnx``
    in the Hugging Face repository. E5-style models automatically receive the
    recommended ``query:`` and ``passage:`` prefixes.
    """

    DEFAULT_ONNX_FILE = "onnx/model.onnx"

    def __init__(
        self,
        settings: Any,
        model_name: Optional[str] = None,
        onnx_file: Optional[str] = None,
        max_length: int = 512,
        normalize: bool = True,
        auto_e5_prefix: bool = True,
        providers: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        self.model_name = model_name or settings.embedding.model
        self.dimension = int(getattr(settings.embedding, "dimensions", 0) or 0)
        self.onnx_file = onnx_file or self.DEFAULT_ONNX_FILE
        self.max_length = int(max_length)
        self.normalize = bool(normalize)
        self.auto_e5_prefix = bool(auto_e5_prefix)
        self.providers = providers or ["CPUExecutionProvider"]
        self._tokenizer = None
        self._session = None
        self._model_dir: Optional[Path] = None
        self._extra_config = kwargs

    def _looks_like_e5(self) -> bool:
        return self.auto_e5_prefix and "e5" in (self.model_name or "").lower()

    @staticmethod
    def _with_prefix(texts: List[str], prefix: str) -> List[str]:
        out: List[str] = []
        for text in texts:
            value = text.strip()
            lowered = value.lower()
            if lowered.startswith("query:") or lowered.startswith("passage:"):
                out.append(value)
            else:
                out.append(f"{prefix}: {value}")
        return out

    def _resolve_model_dir(self) -> Path:
        if self._model_dir is not None:
            return self._model_dir

        candidate = Path(self.model_name).expanduser()
        if candidate.exists():
            self._model_dir = candidate
            return candidate

        try:
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise OnnxEmbeddingError(
                "huggingface_hub is required to download ONNX embedding models."
            ) from exc

        try:
            model_dir = snapshot_download(
                repo_id=self.model_name,
                allow_patterns=[
                    self.onnx_file,
                    "config.json",
                    "tokenizer.json",
                    "tokenizer_config.json",
                    "special_tokens_map.json",
                    "vocab.txt",
                    "*.model",
                    "sentencepiece.bpe.model",
                ],
            )
        except Exception as exc:
            raise OnnxEmbeddingError(
                f"Failed to download or locate ONNX model '{self.model_name}': {exc}"
            ) from exc

        self._model_dir = Path(model_dir)
        return self._model_dir

    def _load_tokenizer(self):
        if self._tokenizer is not None:
            return self._tokenizer
        try:
            from tokenizers import Tokenizer
        except ImportError as exc:
            raise OnnxEmbeddingError("tokenizers is required for ONNX embedding tokenization.") from exc

        model_dir = self._resolve_model_dir()
        tokenizer_path = model_dir / "tokenizer.json"
        if not tokenizer_path.exists():
            raise OnnxEmbeddingError(f"tokenizer.json not found: {tokenizer_path}")
        try:
            self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
        except Exception as exc:
            raise OnnxEmbeddingError(f"Failed to load tokenizer from {tokenizer_path}: {exc}") from exc
        return self._tokenizer

    def _load_session(self):
        if self._session is not None:
            return self._session
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise OnnxEmbeddingError("onnxruntime is required for ONNX inference.") from exc

        model_dir = self._resolve_model_dir()
        model_path = model_dir / self.onnx_file
        if not model_path.exists():
            raise OnnxEmbeddingError(f"ONNX file not found: {model_path}")

        try:
            self._session = ort.InferenceSession(str(model_path), providers=self.providers)
        except Exception as exc:
            raise OnnxEmbeddingError(f"Failed to load ONNX session {model_path}: {exc}") from exc
        return self._session

    @staticmethod
    def _mean_pool(last_hidden_state: np.ndarray, attention_mask: np.ndarray) -> np.ndarray:
        mask = attention_mask.astype(np.float32)[..., None]
        summed = (last_hidden_state * mask).sum(axis=1)
        counts = np.clip(mask.sum(axis=1), a_min=1e-9, a_max=None)
        return summed / counts

    @staticmethod
    def _normalize(vectors: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.clip(norms, a_min=1e-12, a_max=None)

    def embed(
        self,
        texts: List[str],
        trace: Optional[Any] = None,
        **kwargs: Any,
    ) -> List[List[float]]:
        self.validate_texts(texts)
        input_type = str(kwargs.get("input_type", "passage")).lower()
        max_length = int(kwargs.get("max_length", self.max_length))
        normalize = bool(kwargs.get("normalize", self.normalize))

        model_inputs = [text.strip() for text in texts]
        if self._looks_like_e5():
            prefix = "query" if input_type == "query" else "passage"
            model_inputs = self._with_prefix(model_inputs, prefix)

        tokenizer = self._load_tokenizer()
        session = self._load_session()

        tokenizer.enable_truncation(max_length=max_length)
        tokenizer.enable_padding()
        encoded_batch = tokenizer.encode_batch(model_inputs)
        input_ids = np.asarray([encoding.ids for encoding in encoded_batch], dtype=np.int64)
        attention_mask = np.asarray(
            [encoding.attention_mask for encoding in encoded_batch],
            dtype=np.int64,
        )
        token_type_ids = np.asarray([encoding.type_ids for encoding in encoded_batch], dtype=np.int64)

        encoded = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        }
        ort_inputs = {
            input_meta.name: encoded[input_meta.name]
            for input_meta in session.get_inputs()
            if input_meta.name in encoded
        }
        missing_inputs = [
            input_meta.name for input_meta in session.get_inputs() if input_meta.name not in ort_inputs
        ]
        if missing_inputs:
            raise OnnxEmbeddingError(f"Tokenizer did not provide ONNX inputs: {missing_inputs}")
        try:
            outputs = session.run(None, ort_inputs)
        except Exception as exc:
            raise OnnxEmbeddingError(f"ONNX embedding inference failed: {exc}") from exc

        last_hidden_state = np.asarray(outputs[0], dtype=np.float32)
        vectors = self._mean_pool(last_hidden_state, encoded["attention_mask"])
        if normalize:
            vectors = self._normalize(vectors)

        if vectors.ndim != 2 or vectors.shape[0] != len(texts):
            raise OnnxEmbeddingError(
                f"Unexpected embedding shape: expected ({len(texts)}, dim), got {vectors.shape}"
            )
        if self.dimension <= 0:
            self.dimension = int(vectors.shape[1])
        elif vectors.shape[1] != self.dimension:
            raise OnnxEmbeddingError(
                f"Embedding dimension mismatch: settings={self.dimension}, model={vectors.shape[1]}"
            )
        return vectors.astype(np.float32).tolist()

    def get_dimension(self) -> int:
        return self.dimension
