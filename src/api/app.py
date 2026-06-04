"""FastAPI application factory for Final Review Helper."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.middleware.security import APIKeyAuthMiddleware, RateLimitMiddleware
from src.core.settings import resolve_path


def create_app() -> FastAPI:
    app = FastAPI(
        title="期末复习助手 API",
        version="0.1.0",
        description="HTTP API for textbook/PPT ingestion, retrieval, quiz, and review planning.",
    )
    app.add_middleware(APIKeyAuthMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from src.api.routers import (
        health,
        collections,
        documents,
        query,
        learning,
        monitoring,
        openai_compat,
        runtime,
    )

    app.include_router(health.router, tags=["health"])
    app.include_router(collections.router, prefix="/api/collections", tags=["collections"])
    app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
    app.include_router(query.router, prefix="/api/query", tags=["query"])
    app.include_router(learning.router, prefix="/api/learning", tags=["learning"])
    app.include_router(monitoring.router, prefix="/api/monitoring", tags=["monitoring"])
    app.include_router(runtime.router, prefix="/api/runtime", tags=["runtime"])
    app.include_router(openai_compat.router, prefix="/v1", tags=["openai-compatible"])

    @app.on_event("startup")
    async def optional_runtime_warmup():
        import os

        if str(os.getenv("FINAL_REVIEW_AUTO_WARMUP", "")).strip().lower() not in {"1", "true", "yes", "on"}:
            return
        try:
            from src.api.routers.runtime import WarmupRequest, warmup

            await warmup(WarmupRequest(collection=os.getenv("FINAL_REVIEW_WARMUP_COLLECTION", "default")))
        except Exception:
            # Warmup should never prevent the API from starting.
            pass

    frontend_dist = resolve_path("frontend/dist")
    index_html = frontend_dist / "index.html"
    assets_dir = frontend_dist / "assets"

    if index_html.exists():
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            requested = frontend_dist / full_path
            if full_path and requested.exists() and requested.is_file():
                return FileResponse(requested)
            return FileResponse(index_html)

    return app
