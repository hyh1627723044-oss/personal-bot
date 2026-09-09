# 轻声 · 个人助手

React + TypeScript 网页端，FastAPI 后端。默认进入文字聊天，通过 OpenAI 兼容接口流式生成回复；只需配置 LLM，不依赖 ASR/TTS。语音模块使用 Pipecat + SmallWebRTC，流水线为 STT → LLM → TTS，可以之后再配置。

URL、Key、模型名及语音配置均未预填真实值。未配置模型时可以打开页面，发送时提示配置，不会伪造回复。

## 启动

需要标准 CPython 3.11–3.13（建议 3.12）、uv、Node.js 22.12+。

在项目根目录打开两个终端。终端一，启动后端：

```powershell
cd server
Copy-Item .env.example .env
uv sync --frozen
uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 7860
```

只需首次复制 `.env`；之后编辑该文件，重启后端即可。锁文件使用阿里云 PyPI 镜像。

终端二，启动前端：

```powershell
cd web
npm ci
npm run dev
```

打开 http://localhost:5174 。前端 `/api` 自动代理至后端 7860。后端 API 文档位于 http://127.0.0.1:7860/docs 。

当前机器的系统 `python` 为 MSYS2 Python。如 uv 无法获取标准 Python，可使用现有 CPython 的完整路径运行 `uv sync --python <python.exe路径>`。缓存目录权限不足时设置 `UV_CACHE_DIR`、`UV_PYTHON_INSTALL_DIR`、`npm_config_cache` 到可写目录。

## 配置供应商

编辑 `server/.env`，不要把密钥写到前端。三个环节可分别选择不同供应商。

**先开通文字聊天**：模板已选择 `LLM_PROVIDER=openai-compatible`，填写下列三个值并重启后端，其他语音字段可全部留空：

```dotenv
LLM_PROVIDER=openai-compatible
LLM_BASE_URL=https://your-service.example/v1
LLM_API_KEY=your-key
LLM_MODEL=your-model-name
```

`LLM_BASE_URL` 填服务根路径，不要带 `/chat/completions`，后端会补上。模型名须与服务提供的模型或 Agent 路由一致。本地不验证 Key 的 Agent 服务可以使用约定的非空占位值。无需修改网页源码。

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

配置页显示的是本地配置完整性，**不代表供应商密钥已验证可用**。`/api/config` 的 `text_ready` 仅检查 LLM，`ready` 检查完整语音配置。未配置相应服务时，聊天或通话接口返回 503。首次通话需要加载语音检测组件，启动可能较慢。

## 自建 Agent

推荐让 Agent 提供 OpenAI 兼容的 `POST /v1/chat/completions` 流式接口，然后替换 `LLM_BASE_URL`、`LLM_API_KEY` 和 `LLM_MODEL`；文字和语音对话都能复用此服务。

若 Agent 直接嵌入本项目或使用自定义协议，文字聊天通过 `server/app/llm_backend.py` 的 `ChatBackend.stream(messages)` 和 `create_chat_backend()` 接入；语音侧对应 `server/app/providers.py` 的 LLM 服务构造。网页不依赖 Agent 的内部实现。

完整接口约定见 [Agent 接入说明](docs/agent-integration.md)。

## 已搭建功能

- 文字聊天、流式回复、停止生成、重新生成、新对话。
- 文字聊天无需麦克风和 ASR/TTS；浏览器保留当前页面会话，发送最近最多 40 条有效消息作为上下文，不写数据库或 localStorage。
- 文字聊天与语音通话的上下文分别管理，切换页面模式保留当前页面内容，刷新清空。
- 开始通话、静音、挂断，浏览器播放助手音频。
- 连接过程中可取消，45 秒连接超时；处理麦克风权限在取消后才返回的情况。
- 说话状态、本次通话字幕、服务配置检查和连接错误提示。
- Silero VAD 与 Pipecat 会话聚合器负责说话检测、轮次和打断。
- 每次通话独立上下文，结束后释放；不保存历史、不接长期记忆。
- 会话数量限制、120 秒空闲结束、可配置最长时长，关服清理连接。
- 已有测试文件保留；按用户要求，后续收尾及文字聊天实现未运行测试、未做真实模型/语音联调。

## 目录

```text
server/app/settings.py   配置、供应商列表、公开状态
server/app/main.py       HTTP API 和服务生命周期
server/app/chat.py       文字聊天 SSE 接口、消息校验与取消清理
server/app/llm_backend.py OpenAI 兼容流式适配和 Agent 替换入口
server/app/runtime.py    SDP / ICE 信令与会话资源管理
server/app/providers.py  供应商适配
server/app/bot.py        每次通话的 Pipecat 流水线
web/src/App.tsx          通话页面
web/src/TextChat.tsx     文字聊天页面
web/src/chatApi.ts       聊天流式请求和 SSE 解析
web/src/useVoiceCall.ts  通话状态、取消和异常处理
web/src/client.ts        Pipecat 客户端创建和麦克风释放
web/src/main.tsx         Pipecat 客户端与音频播放
```

## 部署边界

构建网页后，后端可直接托管同一个应用：

```powershell
# 从项目根目录开始
cd web
npm run build
cd ../server
uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 7860
```

访问 http://localhost:7860 。后端启动时检测 `web/dist`；修改网页后需重新构建。开发时仍推荐 Vite 的 5174 端口，以免看到旧的构建产物。

默认面向本机个人开发。公网部署时，使用 HTTPS 同源反向代理：网页静态文件来自 `web/dist`，`/api` 转发到后端。后端仅单进程运行（WebRTC 会话在内存中），不要直接增加 uvicorn worker 数。WebRTC 媒体还需要网络可达的 UDP/STUN/TURN，并通过 `ICE_SERVERS` 同时配置客户端和服务端。

文字聊天使用 SSE：反向代理应关闭 `/api/chat` 响应缓冲，读取超时设为大于 180 秒。点击停止会中断浏览器请求并关闭上游 HTTP 流；自建 Agent 也应响应客户端断开，取消内部仍在运行的任务。

公网开放前补充访问控制；当前 API 没有登录认证。TURN 凭据会按协议下发浏览器，生产环境建议短期凭据。API 不返回 AI 密钥；本应用不持久化字幕，但音频/文字仍会发送给所选供应商处理，其日志和留存由供应商管理。

参考：[Pipecat 网页客户端](https://docs.pipecat.ai/client/guides/building-a-voice-ui)、[SmallWebRTC](https://docs.pipecat.ai/api-reference/server/services/transport/small-webrtc)。
