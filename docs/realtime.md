# 实时语音模型

网页仍是文字、语音两种模式。后端 `VOICE_ENGINE=cascade` 保留原来的 STT → LLM → TTS；改成 `realtime` 后，一通电话建立一个独立的供应商 WebSocket，由模型处理听、说、VAD 和上下文。通话内打字进入这条连接，文字模式仍走独立的 `LLM_*` OpenAI 兼容接口。

复制以下一组到 `server/.env`，填入自己的密钥和业务空间，然后重启后端。无需为 Realtime 通话填写 STT/TTS/LLM；如需使用独立文字模式，另外配置 `LLM_*`。

## 千问

```dotenv
VOICE_ENGINE=realtime
REALTIME_PROVIDER=qwen
REALTIME_API_KEY=
REALTIME_MODEL=qwen-audio-3.0-realtime-plus
REALTIME_BASE_URL=wss://YOUR_WORKSPACE_ID.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime
REALTIME_VOICE=longanqian
```

`YOUR_WORKSPACE_ID` 替换为百炼业务空间 ID，密钥、空间和地域必须匹配。也可配置 `qwen-audio-3.0-realtime-flash`；其他地域使用控制台对应的 WebSocket 地址。此适配器面向 Qwen Audio 3，不承诺任意 Qwen Omni 模型直接兼容。输入为 16 kHz PCM16 单声道，输出 24 kHz；会话使用 `pcm` 格式字段和 `server_vad`。

## 阶跃星辰

```dotenv
VOICE_ENGINE=realtime
REALTIME_PROVIDER=stepfun
REALTIME_API_KEY=
REALTIME_MODEL=stepaudio-3-realtime-preview
REALTIME_BASE_URL=wss://api.stepfun.ai/v1/realtime
REALTIME_VOICE=soft-spoken-gentleman
```

以上地址来自国际站 API 文档；如账户控制台提供中国站 `wss://api.stepfun.com/v1/realtime`，使用账户对应地址。输入输出均为 24 kHz PCM16 单声道，会话格式字段为 `pcm16`。Preview 是当前公开试用模型名，正式版本发布后在环境变量中替换。音色也可以替换为文档支持的 ID。

## 行为与边界

- 开麦后可说话、打字、接收声音与字幕；模型维护本次通话的共享上下文。挂断关闭模型连接，再拨号创建新上下文。
- 使用供应商 server VAD，语音开始时清空本地待播放音频并取消正在生成的回复；打字也会打断当前回答。当前没有按实际播放位置截断供应商历史，打断后模型可能记得尚未播放完的内容。
- 暂未启用 Qwen smart_turn、工具调用、联网搜索或跨模式记忆。默认声学 VAD 不等同于模型完整的语义双工能力。
- 配置状态仅检查配置完整性；连接时等待供应商确认会话，拒绝、超时和断线会终止当前通话。不自动重连，以免悄悄丢失上下文。
- 密钥留在后端。每位用户独立连接，受 `MAX_SESSIONS`、会话时长、供应商配额和机器资源限制。
- 本地假 WebSocket 测试验证协议和 WebRTC/RTVI 链路；没有真实密钥时，无法验证账户模型权限、实际音质与延迟。

协议核对日期：2026-09-20。模型名和端点均可配置：

- [Qwen Audio 官方指南](https://help.aliyun.com/zh/model-studio/qwen-audio-realtime-user-guides)
- [StepAudio 3 模型说明](https://platform.stepfun.ai/docs/en/guides/models/stepaudio-3-realtime)
- [StepFun Realtime API](https://platform.stepfun.ai/docs/en/api-reference/realtime/chat)
