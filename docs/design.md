# 网页语音助手 MVP

独立应用，React/TypeScript/Vite 前端，FastAPI/Pipecat 后端，通过 SmallWebRTC 双向传输音频和 RTVI 事件。流水线为 STT → 本次会话上下文 → LLM → TTS，不接长期记忆或实时语音模型。

2026-09-09 补充：文字聊天为默认入口，独立于 ASR/TTS 配置。浏览器通过 `/api/chat` 接收 SSE，后端通过 OpenAI 兼容流式接口连接 LLM 或 Agent。支持停止、重试、新对话；只保留当前页面上下文。Agent 可作为独立兼容服务，也可通过 ChatBackend 工厂在源码中适配。

供应商默认留空。通过后端 .env 配置 STT、LLM、TTS；内置 OpenAI、Deepgram STT，OpenAI 兼容 LLM，OpenAI、Cartesia TTS。适配层集中管理，增加其他 Pipecat 服务只需扩展注册表和工厂。状态接口仅返回配置项名称，不暴露密钥。

未配置可启动、查看页面；通话接口返回明确的 503，不伪造 AI 对话。已配置时建立真实 WebRTC，会话独立，支持语音端点检测、打断、静音、挂断与清理。连接失败提示错误并释放麦克风。默认仅本机开发；公网部署需 HTTPS、网络可达的 ICE 配置以及访问控制。

验收：配置校验、API 拒绝未配置通话、敏感数据不泄漏、资源释放行为的测试；前端类型检查和构建；本地页面检查。无供应商凭据时不宣称已验证真实语音识别和回复质量。
