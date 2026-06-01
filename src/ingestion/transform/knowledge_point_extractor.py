"""Knowledge point extraction transform: rule-based + optional LLM enhancement.

Extracts knowledge points from chunks and stores them in chunk metadata
as `knowledge_points` list. Each knowledge point has: text, category, importance.
"""

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path

from src.core.settings import Settings, resolve_path
from src.core.types import Chunk
from src.core.trace.trace_context import TraceContext
from src.ingestion.transform.base_transform import BaseTransform
from src.libs.llm.llm_factory import LLMFactory
from src.libs.llm.base_llm import BaseLLM, Message
from src.observability.logger import get_logger

logger = get_logger(__name__)

DEFAULT_MAX_WORKERS = 5


class KnowledgePointExtractor(BaseTransform):
    """Extracts knowledge points from chunks.

    Processing Pipeline:
        1. Rule-based extraction: Bold text, headings, bullet points, definitions
        2. (Optional) LLM extraction: Semantic knowledge point identification
        3. On LLM failure: Gracefully fallback to rule-based extraction

    Output Metadata:
        - knowledge_points: List of dicts with {id, text, category, importance}
        - extracted_by: "rule" or "llm"

    Configuration (via settings.yaml):
        - ingestion.knowledge_point_extractor.use_llm: bool
    """

    def __init__(
        self,
        settings: Settings,
        llm: Optional[BaseLLM] = None,
        prompt_path: Optional[str] = None,
    ):
        self.settings = settings
        self._llm = llm
        self._prompt_template: Optional[str] = None
        self._prompt_path = prompt_path or str(
            resolve_path("config/prompts/knowledge_point_extraction.txt")
        )

        kp_config = {}
        if hasattr(settings, "ingestion") and settings.ingestion is not None:
            ingestion_config = settings.ingestion
            if hasattr(ingestion_config, "knowledge_point_extractor") and ingestion_config.knowledge_point_extractor:
                kp_config = ingestion_config.knowledge_point_extractor
            elif isinstance(ingestion_config, dict):
                kp_config = ingestion_config.get("knowledge_point_extractor", {})

        self.use_llm = kp_config.get("use_llm", False) if kp_config else False

    @property
    def llm(self) -> Optional[BaseLLM]:
        if self.use_llm and self._llm is None:
            try:
                self._llm = LLMFactory.create(self.settings)
                logger.info("LLM initialized for knowledge point extraction")
            except Exception as e:
                logger.warning(f"Failed to initialize LLM: {e}. Falling back to rule-based only.")
                self.use_llm = False
        return self._llm

    def transform(
        self,
        chunks: List[Chunk],
        trace: Optional[TraceContext] = None,
    ) -> List[Chunk]:
        if not chunks:
            return []

        if self.use_llm and self.llm:
            return self._transform_parallel(chunks, trace)
        return self._transform_sequential(chunks, trace)

    def _extract_single_chunk(
        self,
        chunk: Chunk,
        chunk_index: int,
        trace: Optional[TraceContext] = None,
    ) -> Tuple[Chunk, str, Optional[str]]:
        try:
            rule_kps = self._rule_based_extract(chunk.text, chunk.id, chunk_index)

            if self.use_llm and self.llm:
                llm_kps = self._llm_extract(chunk.text, chunk.id, chunk_index, trace)
                if llm_kps:
                    kps = llm_kps
                    extracted_by = "llm"
                else:
                    kps = rule_kps
                    extracted_by = "rule"
            else:
                kps = rule_kps
                extracted_by = "rule"

            final_metadata = {
                **(chunk.metadata or {}),
                "knowledge_points": [kp for kp in kps],
                "extracted_by": extracted_by,
            }

            enriched_chunk = Chunk(
                id=chunk.id,
                text=chunk.text,
                metadata=final_metadata,
                source_ref=chunk.source_ref,
            )
            return (enriched_chunk, extracted_by, None)

        except Exception as e:
            logger.error(f"Failed to extract knowledge points from chunk {chunk.id}: {e}")
            minimal_metadata = {
                **(chunk.metadata or {}),
                "knowledge_points": [],
                "extracted_by": "error",
                "kp_error": str(e),
            }
            enriched_chunk = Chunk(
                id=chunk.id,
                text=chunk.text or "",
                metadata=minimal_metadata,
                source_ref=chunk.source_ref,
            )
            return (enriched_chunk, "error", str(e))

    def _transform_parallel(
        self,
        chunks: List[Chunk],
        trace: Optional[TraceContext] = None,
    ) -> List[Chunk]:
        max_workers = min(DEFAULT_MAX_WORKERS, len(chunks))
        results = [None] * len(chunks)
        llm_count = 0
        fallback_count = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(self._extract_single_chunk, chunk, idx, trace): idx
                for idx, chunk in enumerate(chunks)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    result_chunk, extracted_by, error = future.result()
                    results[idx] = result_chunk
                    if extracted_by == "llm":
                        llm_count += 1
                    elif extracted_by == "rule" and error is None:
                        fallback_count += 1
                except Exception as e:
                    logger.error(f"Unexpected error in parallel KP extraction: {e}")
                    results[idx] = chunks[idx]

        success_count = sum(1 for c in results if c is not None)
        if trace:
            trace.record_stage("knowledge_point_extractor", {
                "total_chunks": len(chunks),
                "success_count": success_count,
                "llm_count": llm_count,
                "fallback_count": fallback_count,
                "use_llm": self.use_llm,
                "parallel": True,
            })

        logger.info(
            f"Extracted KPs from {success_count}/{len(chunks)} chunks "
            f"(LLM: {llm_count}, Rule: {fallback_count})"
        )
        return results

    def _transform_sequential(
        self,
        chunks: List[Chunk],
        trace: Optional[TraceContext] = None,
    ) -> List[Chunk]:
        results = []
        llm_count = 0
        fallback_count = 0

        for idx, chunk in enumerate(chunks):
            try:
                rule_kps = self._rule_based_extract(chunk.text, chunk.id, idx)

                if self.use_llm and self.llm:
                    llm_kps = self._llm_extract(chunk.text, chunk.id, idx, trace)
                    if llm_kps:
                        kps = llm_kps
                        extracted_by = "llm"
                        llm_count += 1
                    else:
                        kps = rule_kps
                        extracted_by = "rule"
                        fallback_count += 1
                else:
                    kps = rule_kps
                    extracted_by = "rule"

                final_metadata = {
                    **(chunk.metadata or {}),
                    "knowledge_points": kps,
                    "extracted_by": extracted_by,
                }
                enriched_chunk = Chunk(
                    id=chunk.id,
                    text=chunk.text,
                    metadata=final_metadata,
                    source_ref=chunk.source_ref,
                )
                results.append(enriched_chunk)
            except Exception as e:
                logger.error(f"Failed to extract KPs from chunk {chunk.id}: {e}")
                minimal_metadata = {
                    **(chunk.metadata or {}),
                    "knowledge_points": [],
                    "extracted_by": "error",
                }
                results.append(Chunk(
                    id=chunk.id,
                    text=chunk.text or "",
                    metadata=minimal_metadata,
                    source_ref=chunk.source_ref,
                ))

        if trace:
            trace.record_stage("knowledge_point_extractor", {
                "total_chunks": len(chunks),
                "success_count": len(results),
                "llm_count": llm_count,
                "fallback_count": fallback_count,
                "use_llm": self.use_llm,
                "parallel": False,
            })

        return results

    def _rule_based_extract(
        self,
        text: str,
        chunk_id: str,
        chunk_index: int,
    ) -> List[Dict[str, Any]]:
        if not text:
            return []

        kps: List[Dict[str, Any]] = []
        seq = 0

        # Extract from markdown headings
        for match in re.finditer(r"^#{1,6}\s+(.+)$", text, re.MULTILINE):
            heading = match.group(1).strip()
            if len(heading) > 5:
                kp_id = f"kp_{chunk_id[:16]}_{chunk_index}_{seq}"
                kps.append({
                    "id": kp_id,
                    "text": heading,
                    "category": "概念",
                    "importance": 3,
                })
                seq += 1

        # Extract from bold text
        for match in re.finditer(r"\*\*(.+?)\*\*", text):
            bold = match.group(1).strip()
            if len(bold) > 5 and len(bold) < 100:
                kp_id = f"kp_{chunk_id[:16]}_{chunk_index}_{seq}"
                kps.append({
                    "id": kp_id,
                    "text": bold,
                    "category": "概念",
                    "importance": 3,
                })
                seq += 1

        # Extract from definition patterns (X 是 Y, X: Y)
        for match in re.finditer(r"^(.{5,50})(?:是|：)\s*(.{10,200})$", text, re.MULTILINE):
            kp_id = f"kp_{chunk_id[:16]}_{chunk_index}_{seq}"
            kps.append({
                "id": kp_id,
                "text": f"{match.group(1).strip()}是{match.group(2).strip()}",
                "category": "定义",
                "importance": 4,
            })
            seq += 1

        # Extract from bullet points
        for match in re.finditer(r"^[\s]*[-*•]\s+(.{10,200})$", text, re.MULTILINE):
            kp_id = f"kp_{chunk_id[:16]}_{chunk_index}_{seq}"
            kps.append({
                "id": kp_id,
                "text": match.group(1).strip(),
                "category": "事实",
                "importance": 2,
            })
            seq += 1

        # Deduplicate by text
        seen = set()
        unique_kps = []
        for kp in kps:
            if kp["text"] not in seen:
                seen.add(kp["text"])
                unique_kps.append(kp)

        return unique_kps

    def _llm_extract(
        self,
        text: str,
        chunk_id: str,
        chunk_index: int,
        trace: Optional[TraceContext] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        if not self.llm:
            return None

        try:
            prompt = self._load_prompt()
            formatted_prompt = prompt.replace("{chunk_text}", text[:2000])

            messages = [Message(role="user", content=formatted_prompt)]
            response = self.llm.chat(messages)

            if not response:
                return None

            response_text = response
            if hasattr(response, "content"):
                response_text = response.content
            elif not isinstance(response, str):
                response_text = str(response)

            kps = self._parse_llm_response(response_text, chunk_id, chunk_index)

            if trace:
                trace.record_stage("llm_kp_extract", {
                    "success": True,
                    "kp_count": len(kps),
                })

            return kps if kps else None

        except Exception as e:
            logger.warning(f"LLM KP extraction failed: {e}")
            if trace:
                trace.record_stage("llm_kp_extract", {
                    "success": False,
                    "error": str(e),
                })
            return None

    def _load_prompt(self) -> str:
        if self._prompt_template is not None:
            return self._prompt_template

        prompt_path = Path(self._prompt_path)
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {self._prompt_path}")

        self._prompt_template = prompt_path.read_text(encoding="utf-8")
        return self._prompt_template

    def _parse_llm_response(
        self,
        response: str,
        chunk_id: str,
        chunk_index: int,
    ) -> List[Dict[str, Any]]:
        try:
            # Try to extract JSON array from response
            json_match = re.search(r"\[.*\]", response, re.DOTALL)
            if not json_match:
                return []

            raw_kps = json.loads(json_match.group())
            if not isinstance(raw_kps, list):
                return []

            kps = []
            for i, raw in enumerate(raw_kps):
                if not isinstance(raw, dict) or "text" not in raw:
                    continue
                kp_id = f"kp_{chunk_id[:16]}_{chunk_index}_{i}"
                kps.append({
                    "id": kp_id,
                    "text": raw["text"],
                    "category": raw.get("category", "general"),
                    "importance": int(raw.get("importance", 3)),
                })

            return kps

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse LLM KP response: {e}")
            return []
