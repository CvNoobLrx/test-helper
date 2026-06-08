"""SSE streaming utilities for the API."""

from __future__ import annotations

import json
from typing import Any, Generator


def sse_event(event: str, data: Any) -> str:
    """Format a single SSE event string."""
    if isinstance(data, (dict, list)):
        data = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n"


def sse_generator(event_stream: Generator[str, None, None]) -> Generator[str, None, None]:
    """Yield SSE events from a generator."""
    yield from event_stream
