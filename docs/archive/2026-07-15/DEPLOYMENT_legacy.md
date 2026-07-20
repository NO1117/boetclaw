# 部署说明

后端建议使用 Python 3.11-3.13。Python 3.14 目前会触发 LangChain/Pydantic 兼容性问题。

## 本地一键安装

Windows：

```powershell
.\scripts\install.ps1
```

Linux/macOS：

```bash
chmod +x scripts/install.sh
./scripts/install.sh
```

脚本会创建 `backend/.venv`、安装 Python/npm 依赖，并在缺失时从 `.env.example` 初始化 `backend/.env`。

## 本地开发启动

```bash
cd backend
# Windows
.\.venv\Scripts\python.exe run.py

# Linux/macOS
.venv/bin/python run.py
```

```bash
cd frontend
npm run dev
```

访问：

- 后端 API：http://localhost:8000/docs
- 前端：http://localhost:5173

## Docker Compose

```bash
cp backend/.env.example backend/.env
docker compose up --build
```

访问：

- 前端：http://localhost:5173
- 后端：http://localhost:8000/docs
- 单容器内置前端：http://localhost:8000/ui/

## 可选 Ollama

```bash
docker compose --profile ollama up --build
```

然后在 `backend/.env` 中配置：

```env
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5
OLLAMA_BASE_URL=http://ollama:11434
```

## OpenAI-compatible 本地模型

如果本地模型服务提供 OpenAI 兼容接口（例如 vLLM、LM Studio、LocalAI、Ollama `/v1`），可使用 `openai` provider 并配置 `OPENAI_BASE_URL`：

```env
LLM_PROVIDER=openai
LLM_MODEL=qwen3.6-35b-a3b
OPENAI_API_KEY=not-needed
OPENAI_BASE_URL=http://localhost:8001/v1
```

当只配置 `OPENAI_BASE_URL` 而未配置真实 Key 时，系统会自动使用 `not-needed` 作为兼容服务的占位 key。

## 生产建议

- 设置 `API_TOKEN` 或在反向代理层增加认证。
- 将 `backend/workspace` 挂载到持久卷。
- 使用 HTTPS 暴露前端和 webhook。
- 保持 `TOOL_GUARD_ENABLED=true`。
- 仅通过 `ENABLED_PLUGINS` 启用审查过的插件。
