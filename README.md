# 期末复习助手

面向电子课本 PDF、课件 PPT 和复习资料的本地 RAG 助手。系统支持资料上传、知识库检索、问答、知识点抽取、测验生成和间隔复习。

## 功能

- PDF / PPT / 图片资料摄取
- ONNX Runtime 本地 embedding，默认 `intfloat/multilingual-e5-small`
- OpenAI-compatible Chat / Vision API
- Chroma 向量库 + BM25 稀疏索引
- LLM rerank：复用 Chat API 对检索候选片段进行轻量重排
- Web 前端：资料库、知识问答、复习计划、运行状态
- FastAPI 后端：`/docs` 提供接口调试页面

## 目录

```text
config/          配置和提示词
frontend/        React 前端
scripts/         启动脚本
src/api/         FastAPI 接口
src/core/        配置、类型、查询引擎
src/ingestion/   文档摄取、分块、embedding、存储
src/libs/        LLM、embedding、loader、vector store 等可插拔实现
```

## 单端口启动（推荐部署）

前端构建后由 FastAPI 直接托管，浏览器只需要打开一个地址：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
cd frontend
npm install
cd ..
python scripts/start_web.py --build-frontend --host 0.0.0.0 --port 8000
```

访问：

- Web 页面：`http://127.0.0.1:8000`
- API 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/health`

说明：后端仍然需要监听一个端口，但前端和 API 共用这个端口，不再需要单独打开 Vite 的 `5173`。

## 开发模式：后端启动

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python scripts/start_api.py --host 0.0.0.0 --port 8000
```

访问：

- API 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/health`

## 开发模式：前端启动

```powershell
cd frontend
npm install
npm run dev
```

生产构建：

```powershell
cd frontend
npm install
npm run build
```

## 必要配置

主配置文件：

```text
config/settings.yaml
```

当前默认：

- `llm.provider = openai`
- `embedding.provider = onnx`
- `embedding.model = intfloat/multilingual-e5-small`
- `rerank.provider = llm`

不要把 API Key 写进仓库。部署服务器上设置环境变量：

```powershell
$env:OPENAI_API_KEY="your-api-key"
```

Linux：

```bash
export OPENAI_API_KEY="your-api-key"
```

## 下载 embedding 模型

首次运行 embedding 时会自动下载 ONNX 文件。也可以提前执行：

```powershell
python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='intfloat/multilingual-e5-small', allow_patterns=['onnx/model.onnx','onnx/config.json','onnx/tokenizer.json','onnx/tokenizer_config.json','onnx/special_tokens_map.json','onnx/sentencepiece.bpe.model','config.json','tokenizer.json','tokenizer_config.json','special_tokens_map.json','sentencepiece.bpe.model'])"
```

部署到无法访问 Hugging Face 的服务器时，可以把本机 Hugging Face 缓存复制到服务器相同用户的缓存目录，或把模型目录放到服务器本地后把 `embedding.model` 改成本地路径。

## 典型流程

1. 启动后端。
2. 启动前端。
3. 在“复习资料”中上传 PDF/PPT。
4. 等待摄取完成。
5. 在“知识问答”中提问。
6. 在“复习计划”中查看知识点、生成 quiz、记录掌握情况。

## 部署注意

- `data/`、`logs/`、`.venv/`、`frontend/node_modules/` 不提交到 Git。
- `config/settings.yaml` 不包含明文 Key。
- 若端口对外开放，请在反向代理或平台侧配置 HTTPS、鉴权和跨域策略。
- 生产环境可使用 `scripts/start_web.py` 单端口托管前端和 API；也可以把前端 `dist/` 交给 Nginx 或平台静态站点服务，后端单独运行 FastAPI。
