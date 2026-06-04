"""Build and launch the single-port web application."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.settings import resolve_path


def build_frontend() -> None:
    frontend_dir = resolve_path("frontend")
    npm_executable = "npm.cmd" if sys.platform.startswith("win") else "npm"
    npm_path = shutil.which(npm_executable) or shutil.which("npm")
    if not npm_path:
        raise SystemExit(
            "npm not found. Please install Node.js, or run `cd frontend && npm run build` "
            "before starting without `--build-frontend`."
        )
    command = [npm_path, "run", "build"]
    subprocess.run(command, cwd=frontend_dir, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the final review helper web app")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    parser.add_argument(
        "--build-frontend",
        action="store_true",
        help="Run npm build before starting the server",
    )
    args = parser.parse_args()

    if args.build_frontend:
        build_frontend()

    index_html: Path = resolve_path("frontend/dist/index.html")
    if not index_html.exists():
        raise SystemExit(
            "frontend/dist/index.html not found. Run `cd frontend && npm run build` "
            "or start this script with `--build-frontend`."
        )

    uvicorn.run(
        "src.api.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
