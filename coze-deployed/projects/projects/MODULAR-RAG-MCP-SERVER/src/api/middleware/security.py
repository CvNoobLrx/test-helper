"""Lightweight API authentication and rate limiting middleware."""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _configured_keys() -> set[str]:
    raw = os.getenv("FINAL_REVIEW_API_KEYS") or os.getenv("API_KEYS") or ""
    return {item.strip() for item in raw.split(",") if item.strip()}


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Optional Bearer-token auth controlled by environment variables.

    Auth is enabled when either ``FINAL_REVIEW_AUTH_ENABLED=1`` or
    ``FINAL_REVIEW_API_KEYS`` contains at least one comma-separated key.
    """

    PUBLIC_PREFIXES = (
        "/",
        "/assets",
        "/api/health",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/favicon.ico",
    )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        keys = _configured_keys()
        enabled = _truthy(os.getenv("FINAL_REVIEW_AUTH_ENABLED")) or bool(keys)
        if not enabled or self._is_public(request.url.path):
            return await call_next(request)

        token = self._token_from_request(request)
        if not token or token not in keys:
            return JSONResponse(
                {"error": "Unauthorized", "message": "Missing or invalid API key"},
                status_code=401,
            )
        return await call_next(request)

    @classmethod
    def _is_public(cls, path: str) -> bool:
        if path == "/":
            return True
        return any(path.startswith(prefix) for prefix in cls.PUBLIC_PREFIXES if prefix != "/")

    @staticmethod
    def _token_from_request(request: Request) -> str:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return request.headers.get("x-api-key", "").strip()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-process sliding-window rate limiter.

    Set ``FINAL_REVIEW_RATE_LIMIT_PER_MINUTE`` to a positive integer to enable.
    The limit is per API key when present, otherwise per client IP.
    """

    def __init__(self, app, limit_per_minute: int | None = None) -> None:
        super().__init__(app)
        configured = os.getenv("FINAL_REVIEW_RATE_LIMIT_PER_MINUTE", "")
        self.limit = limit_per_minute if limit_per_minute is not None else int(configured or "0")
        self.window_seconds = 60.0
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if self.limit <= 0 or request.url.path.startswith("/assets"):
            return await call_next(request)

        identity = self._identity(request)
        now = time.monotonic()
        bucket = self._hits[identity]
        while bucket and now - bucket[0] > self.window_seconds:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return JSONResponse(
                {
                    "error": "Rate limit exceeded",
                    "message": f"Limit is {self.limit} requests per minute",
                },
                status_code=429,
            )
        bucket.append(now)
        return await call_next(request)

    @staticmethod
    def _identity(request: Request) -> str:
        auth = request.headers.get("authorization", "")
        if auth:
            return auth
        if request.client:
            return request.client.host
        return "unknown"
