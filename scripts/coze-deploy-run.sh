#!/usr/bin/env bash
set -euo pipefail

# 基于脚本位置定位项目根目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="${WORKSPACE_DIR}/projects/MODULAR-RAG-MCP-SERVER"

cd "${PROJECT_DIR}"

# 显式声明关键环境变量
export PORT=5000
export HOST=0.0.0.0
export PYTHONPATH="${PROJECT_DIR}:${PYTHONPATH:-}"
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://maas-coding-api.cn-huabei-1.xf-yun.com/v2}"
export OPENAI_MODEL="${OPENAI_MODEL:-astron-code-latest}"

echo "[Deploy Run] Starting Final Review Helper on ${HOST}:${PORT}"
exec python scripts/start_web.py --host "${HOST}" --port "${PORT}"
