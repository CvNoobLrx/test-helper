"""Process-local runtime status used by warmup and monitoring endpoints."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class RuntimeState:
    warmed: bool = False
    warmup_started_at: str = ""
    warmup_finished_at: str = ""
    warmup_elapsed_ms: float = 0.0
    components: dict[str, Any] = field(default_factory=dict)
    last_benchmark: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "warmed": self.warmed,
            "warmup_started_at": self.warmup_started_at,
            "warmup_finished_at": self.warmup_finished_at,
            "warmup_elapsed_ms": self.warmup_elapsed_ms,
            "components": self.components,
            "last_benchmark": self.last_benchmark,
        }


runtime_state = RuntimeState()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
