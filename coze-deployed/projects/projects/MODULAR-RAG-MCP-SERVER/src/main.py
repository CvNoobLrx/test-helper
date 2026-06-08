"""Coze entrypoint adapter for the FastAPI application."""

from __future__ import annotations

import os

import uvicorn

from src.api.app import create_app

app = create_app()


def main() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    uvicorn.run("src.main:app", host=host, port=port)


if __name__ == "__main__":
    main()
