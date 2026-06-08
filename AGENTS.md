## 项目概述
期末复习助手（Final Review Helper）—— 面向电子课本 PDF、课件 PPT 和复习资料的本地 RAG 助手。支持资料上传、知识库检索、问答、知识点抽取、测验生成和间隔复习。

## 技术栈
- **后端**: Python 3.12, FastAPI, Uvicorn
- **前端**: React 19, TypeScript, Vite 8, Tailwind CSS 4, Zustand, React Router
- **Embedding**: ONNX Runtime (intfloat/multilingual-e5-small)
- **向量库**: ChromaDB + BM25 稀疏索引
- **LLM**: OpenAI-compatible API（默认讯飞星火 astron-code-latest）
- **Rerank**: LLM rerank

## 目录结构
```
MODULAR-RAG-MCP-SERVER/
├── config/             配置文件和提示词
├── frontend/           React 前端 (Vite + TypeScript)
│   └── src/            页面、组件、状态管理、API 客户端
├── scripts/            启动脚本
│   ├── setup.sh        依赖安装 + 前端构建 + embedding 预热
│   ├── http_run.sh     单端口启动（构建前端 + FastAPI）
│   ├── start_web.py    Python 入口：构建前端并启动 uvicorn
│   ├── start_api.py    仅 API 模式
│   └── start_dashboard.py
├── src/
│   ├── api/            FastAPI 路由、中间件、Schema
│   ├── core/           配置、类型、查询引擎
│   ├── ingestion/      文档摄取、分块、embedding、存储
│   └── libs/           LLM、embedding、loader、vector store 等可插拔实现
├── pyproject.toml
└── requirements.txt
```

## 关键入口 / 核心模块
- **单端口启动**: `python scripts/start_web.py --build-frontend --host 0.0.0.0 --port 5000`
- **FastAPI App 工厂**: `src/api/app.py` → `create_app()`
- **配置加载**: `src/core/settings.py` → `load_settings()`
- **前端入口**: `frontend/src/main.tsx`
- **API 路由**: health, collections, documents, query, learning, monitoring, runtime, openai-compat

## 运行与预览
- 单端口模式：前端构建后由 FastAPI 托管，统一暴露 5000 端口
- 构建脚本：`scripts/setup.sh`（安装 Python 依赖 + npm install + npm run build + embedding 预热）
- 运行脚本：`scripts/http_run.sh -p 5000`
- 需要 Node.js 24 构建 frontend
- 需要 Python 3.12 运行后端

## 用户偏好与长期约束
- Node.js 项目只使用 pnpm，但本项目前端构建使用 npm（由 setup.sh 自动处理）
- API Key 通过环境变量注入，不写入代码仓库
- 前端默认 Vite 端口 5173（开发模式），生产模式由 FastAPI 统一托管

## 常见问题和预防
- `frontend/dist/index.html` 不存在时启动会失败，需先构建前端或传入 `--build-frontend`
- embedding 模型首次运行需下载，可能耗时较长
- `numpy>=2` 与 onnxruntime 不兼容，pyproject.toml 已锁定 `numpy<2`
