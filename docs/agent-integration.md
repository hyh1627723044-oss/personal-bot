# 将 Agent 作为 LLM 接入

## 推荐：独立的 OpenAI 兼容服务

配置 `LLM_PROVIDER=openai-compatible`、`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`。例如 Agent 服务监听本机 8001，且端点为 `/v1/chat/completions`，则 BASE_URL 填 `http://127.0.0.1:8001/v1`。

此路径用于文字聊天和 Pipecat 语音 LLM 环节，两个界面都不需要知道 Agent 内部如何规划、调用工具或管理记忆。

请求示例（接口服务须支持）：

```http
POST /v1/chat/completions
Authorization: Bearer <LLM_API_KEY>
Content-Type: application/json
```

```json
{
  "model": "personal-agent",
  "stream": true,
  "messages": [
    {"role": "system", "content": "你是一位友好的个人助手。"},
    {"role": "user", "content": "帮我整理今天的待办。"}
  ]
}
```

服务返回 `Content-Type: text/event-stream`，每条事件以空行结束：

```text
data: {"choices":[{"index":0,"delta":{"role":"assistant","content":"好的，"},"finish_reason":null}]}

data: {"choices":[{"index":0,"delta":{"content":"请把待办发给我。"},"finish_reason":null}]}

data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]

```

兼容标准的其他字段可以保留；核心字段是 `choices[0].delta.content`。内部工具调用应由 Agent 自己执行，把面向用户的结果放入 content。本版本不会在浏览器中执行 tool_calls，也不会把推理或内部工具事件当作正文显示。

Agent 服务应支持客户端取消：客户端断开流后，取消正在执行的模型/工具任务。不要假设所有请求属于同一个人；后续增加长期记忆时，要显式引入用户身份和会话标识。当前文字/语音会话使用独立上下文，没有持久会话 ID。

## 可选：修改后端适配器

文字聊天的边界位于 `server/app/llm_backend.py`：

```python
class ChatBackend(Protocol):
    def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]: ...
```

实现一个接收完整对话、逐段 yield 字符串的适配器，然后让 `create_chat_backend(settings)` 返回它。可调用自定义 HTTP 服务，也可调用进程内 Agent。适配器应在取消时关闭资源；对外错误使用 `ModelServiceError`，不要把密钥或内部响应正文拼进错误消息。

语音侧由 `server/app/providers.py` 构造 Pipecat LLM 服务。若 Agent 不提供 OpenAI 接口，需要在此接入相应的 Pipecat 服务或自定义 FrameProcessor；只改文字工厂不会自动替换语音 LLM。统一提供兼容接口可减少这两处适配工作。

## 网页到本项目后端

网页调用 `POST /api/chat`，只发送 user/assistant 消息；系统提示词由后端加入。后端响应的 SSE 是本应用自己的三个事件：

- `delta`：`{"text":"新增文字"}`。
- `done`：`{}`，本次回复完成。
- `error`：`{"message":"可向用户显示的错误"}`。

此接口与上游 OpenAI 协议隔离。更换模型或 Agent 时，网页解析代码无需改变。
