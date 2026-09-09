# 轻声 · 网页语音助手

独立的 Pipecat 网页语音 MVP。React + TypeScript 前端，FastAPI + Pipecat 后端，SmallWebRTC 传输音频，STT → LLM → TTS 处理对话。供应商配置默认留空，可先启动网页和后端。

## 启动

需要标准 CPython 3.11–3.13（建议 3.12）、uv、Node.js 22.12+。

终端一，启动后端：

```powershell
cd C:\study\flask\code3\voice-assistant\server
Copy-Item .env.example .env
uv sync --frozen
uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 7860
```

只需首次复制 `.env`；之后编辑该文件，重启后端即可。锁文件使用阿里云 PyPI 镜像。

终端二，启动前端：

```powershell
cd C:\study\flask\code3\voice-assistant\web
npm ci
npm run dev
```

打开 http://localhost:5174 。前端 `/api` 自动代理至后端 7860。后端 API 文档位于 http://127.0.0.1:7860/docs 。

当前机器的系统 `python` 为 MSYS2 Python。如 uv 无法获取标准 Python，可使用现有 CPython 的完整路径运行 `uv sync --python <python.exe路径>`。缓存目录权限不足时设置 `UV_CACHE_DIR`、`UV_PYTHON_INSTALL_DIR`、`npm_config_cache` 到可写目录。

## 配置供应商

编辑 `server/.env`，不要把密钥写到前端。三个环节可分别选择不同供应商。

| 环节 | PROVIDER | 必填配置 | 可选配置 |
| --- | --- | --- | --- |
| 语音识别 | `openai` | `STT_API_KEY`、`STT_MODEL` | `STT_BASE_URL` |
| 语音识别 | `deepgram` | `STT_API_KEY`、`STT_MODEL` | `STT_BASE_URL` |
| 对话模型 | `openai` | `LLM_API_KEY`、`LLM_MODEL` | `LLM_BASE_URL` |
| 对话模型 | `openai-compatible` | `LLM_API_KEY`、`LLM_MODEL`、`LLM_BASE_URL` | — |
| 语音合成 | `openai` | `TTS_API_KEY`、`TTS_MODEL`、`TTS_VOICE` | `TTS_BASE_URL` |
| 语音合成 | `cartesia` | `TTS_API_KEY`、`TTS_MODEL`、`TTS_VOICE` | — |

模型和音色按所选供应商的控制台填写，确认模型支持目标语言。`LANGUAGE` 支持 `zh`、`en`；换英语时同时修改 `SYSTEM_PROMPT`。OpenAI 识别适配器使用普通音频转写接口；本项目没有接实时语音对话模型。兼容接口仍需支持 Chat Completions 流式响应。

Pipecat 支持的供应商比本项目内置的更多。新增供应商时，在 `server/app/providers.py` 添加服务构造分支，在 `settings.py` 的 `PROVIDERS` 注册名称，并添加对应 Python extra/参数。不要仅填写一个未实现的供应商名。

配置页显示的是本地配置完整性，**不代表供应商密钥已验证可用**。未配置时，通话请求返回 503，页面提示待填写项；不会生成模拟回复。首次通话需要加载语音检测组件，启动可能较慢。

## 已搭建功能

- 开始通话、静音、挂断，浏览器播放助手音频。
- 说话状态、本次通话字幕、服务配置检查和连接错误提示。
- Silero VAD 与 Pipecat 会话聚合器负责说话检测、轮次和打断。
- 每次通话独立上下文，结束后释放；不保存历史、不接长期记忆。
- 会话数量限制、120 秒空闲结束、可配置最长时长，关服清理连接。
- 配置/API/字幕测试文件已保留；按用户要求，最后补齐运行时后未继续运行测试，真实供应商通话尚未验证。

## 目录

```text
server/app/settings.py   配置、供应商列表、公开状态
server/app/main.py       HTTP API 和服务生命周期
server/app/runtime.py    SDP / ICE 信令与会话资源管理
server/app/providers.py  供应商适配
server/app/bot.py        每次通话的 Pipecat 流水线
web/src/App.tsx          通话页面
web/src/main.tsx         Pipecat 客户端与音频播放
```

## 部署边界

默认面向本机个人开发。公网部署时，使用 HTTPS 同源反向代理：网页静态文件来自 `web/dist`，`/api` 转发到后端。后端仅单进程运行（WebRTC 会话在内存中），不要直接增加 uvicorn worker 数。WebRTC 媒体还需要网络可达的 UDP/STUN/TURN，并通过 `ICE_SERVERS` 同时配置客户端和服务端。

公网开放前补充访问控制；当前 API 没有登录认证。TURN 凭据会按协议下发浏览器，生产环境建议短期凭据。API 不返回 AI 密钥；本应用不持久化字幕，但音频/文字仍会发送给所选供应商处理，其日志和留存由供应商管理。

参考：[Pipecat 网页客户端](https://docs.pipecat.ai/client/guides/building-a-voice-ui)、[SmallWebRTC](https://docs.pipecat.ai/api-reference/server/services/transport/small-webrtc)。
