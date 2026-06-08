#!/usr/bin/env bash
set -euo pipefail

# 基于脚本位置定位项目根目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="${WORKSPACE_DIR}/projects/MODULAR-RAG-MCP-SERVER"

cd "${PROJECT_DIR}"

echo "[Deploy Build] Installing Python dependencies..."
python -m pip install --upgrade pip 2>/dev/null || true
python -m pip install --no-cache-dir -r requirements.txt

echo "[Deploy Build] Building frontend..."
if [ -f "frontend/package.json" ]; then
    (
        cd frontend
        if [ -f "package-lock.json" ]; then
            npm ci
        else
            npm install
        fi
        npm run build
    )
fi

echo "[Deploy Build] Done."
