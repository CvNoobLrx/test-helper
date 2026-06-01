"""FastAPI application factory for Final Review Helper."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def create_app() -> FastAPI:
    app = FastAPI(
        title="期末复习助手 API",
        version="0.1.0",
        description="HTTP API for textbook/PPT ingestion, retrieval, quiz, and review planning.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from src.api.routers import health, collections, documents, query, learning, monitoring

    app.include_router(health.router, tags=["health"])
    app.include_router(collections.router, prefix="/api/collections", tags=["collections"])
    app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
    app.include_router(query.router, prefix="/api/query", tags=["query"])
    app.include_router(learning.router, prefix="/api/learning", tags=["learning"])
    app.include_router(monitoring.router, prefix="/api/monitoring", tags=["monitoring"])

    return app
