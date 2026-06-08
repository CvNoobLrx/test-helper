"""Launch script for the FastAPI API server."""

import argparse
import os
import sys

os.environ.setdefault("PYTHONNOUSERSITE", "1")
try:
    import site

    user_site = site.getusersitepackages()
    if isinstance(user_site, str):
        user_sites = {user_site}
    else:
        user_sites = set(user_site)
    sys.path[:] = [path for path in sys.path if path not in user_sites]
except Exception:
    pass

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Start the Modular RAG API server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    uvicorn.run(
        "src.api.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
