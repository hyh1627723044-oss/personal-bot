"""Per-call WebSocket bridge. Providers own VAD and conversation context.

Qwen Audio 3 uses 16 kHz input / `pcm`; StepAudio uses 24 kHz / `pcm16`.
Both output 24 kHz PCM16. No credentials or audio are sent to browser JS.
"""

import asyncio
import base64
import json
from collections import deque
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    InputAudioRawFrame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMMessagesAppendFrame,
    StartFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    TTSTextFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameProcessor
from websockets.asyncio.client import connect

from app.settings import Settings


class RealtimeService(FrameProcessor):
    def __init__(self, config: Settings):
        super().__init__()
        self.config = config
        self.input_sample_rate = 16000 if config.realtime_provider == 'qwen' else 24000
        self._ws = None
        self._receiver = None
        self._closing = False
        self._response_active = False
        self._response_pending = False
        self._cancel_on_create = False
        self._suppressed = False
        self._audio_started = False
        self._settled = asyncio.Event()
        self._settled.set()
        self._cancel_ids = deque(maxlen=32)

    def connection_url(self):
        parts = urlsplit(self.config.realtime_base_url)
        query = [(k, v) for k, v in parse_qsl(parts.query) if k != 'model']
        query.append(('model', self.config.realtime_model))
        return urlunsplit(parts._replace(query=urlencode(query)))

    def session_options(self):
        qwen = self.config.realtime_provider == 'qwen'
        return {
            'modalities': ['text', 'audio'],
            'instructions': self.config.system_prompt,
            'voice': self.config.realtime_voice,
            'input_audio_format': 'pcm' if qwen else 'pcm16',
            'output_audio_format': 'pcm' if qwen else 'pcm16',
            'turn_detection': {'type': 'server_vad', 'silence_duration_ms': 800},
        }

    async def _send(self, kind, **payload):
        event_id = uuid4().hex
        await self._ws.send(json.dumps({'type': kind, 'event_id': event_id, **payload}))
        return event_id

    async def _connect(self):
        # Do not let an unavailable provider leave a WebRTC session half-ready.
        async with asyncio.timeout(15):
            self._ws = await connect(
                self.connection_url(),
                additional_headers={
                    'Authorization': f'Bearer {self.config.realtime_api_key.get_secret_value()}',
                },
                open_timeout=10, close_timeout=2, max_size=4 * 1024 * 1024,
            )
            await self._send('session.update', session=self.session_options())
            while True:
                event = json.loads(await self._ws.recv())
                if event['type'] == 'session.updated':
                    break
                if event['type'] == 'error':
                    raise RuntimeError('Realtime session rejected')

    async def _close(self):
        self._closing = True
        if self._receiver:
            self._receiver.cancel()
            await asyncio.gather(self._receiver, return_exceptions=True)
            self._receiver = None
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def cleanup(self):
        await self._close()
        await super().cleanup()

    async def _finish_response(self):
        if self._audio_started:
            await self.push_frame(TTSStoppedFrame())
            self._audio_started = False
        if self._response_active:
            await self.push_frame(LLMFullResponseEndFrame())
            self._response_active = False

    async def _interrupt(self):
        self._suppressed = True
        if self._response_pending:
            self._cancel_on_create = True
        if self._response_active:
            self._cancel_ids.append(await self._send('response.cancel'))
        await self._finish_response()

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        try:
            if isinstance(frame, StartFrame):
                await self._connect()
                await self.push_frame(frame, direction)
                self._receiver = self.create_task(self._receive())
            elif isinstance(frame, (CancelFrame, EndFrame)):
                await self._close()
                await self.push_frame(frame, direction)
            elif isinstance(frame, InputAudioRawFrame):
                if frame.sample_rate != self.input_sample_rate or frame.num_channels != 1:
                    raise ValueError('Unexpected input audio format')
                await self._send('input_audio_buffer.append',
                                 audio=base64.b64encode(frame.audio).decode())
            elif isinstance(frame, InterruptionFrame):
                await self._interrupt()
                await self.push_frame(frame, direction)
            elif isinstance(frame, LLMMessagesAppendFrame):
                # RTVI send-text arrives here in the same provider session as audio.
                await self._interrupt()
                await asyncio.wait_for(self._settled.wait(), 5)
                for message in frame.messages:
                    text = message.get('content')
                    if message.get('role') == 'user' and isinstance(text, str) and text.strip():
                        if len(text) > 8000:
                            raise ValueError('Text exceeds limit')
                        await self._send('conversation.item.create', item={
                            'type': 'message', 'role': 'user',
                            'content': [{'type': 'input_text', 'text': text}],
                        })
                if frame.run_llm:
                    self._response_pending = True
                    self._suppressed = False
                    self._settled.clear()
                    await self._send('response.create')
            else:
                await self.push_frame(frame, direction)
        except Exception:  # noqa: BLE001 -- never expose provider payloads/credentials
            # Provider exceptions may include request headers or user content.
            await self.push_error('Realtime 连接或请求失败，请检查后端模型、地址和密钥配置。')

    async def _receive(self):
        try:
            async for raw in self._ws:
                await self._event(json.loads(raw))
            if not self._closing:
                await self.push_error('Realtime 服务连接已关闭，请重新开始通话。')
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 -- report a sanitized transport failure
            if not self._closing:
                await self.push_error('Realtime 服务响应异常，请重新开始通话。')

    async def _event(self, event):
        kind = event.get('type')
        if kind == 'error':
            # Cancellation can race a naturally completed response.
            event_id = event.get('error', {}).get('event_id')
            if event_id in self._cancel_ids:
                self._cancel_ids.remove(event_id)
                self._settled.set()
                return
            raise RuntimeError('Realtime provider error')
        if kind == 'input_audio_buffer.speech_started':
            await self._interrupt()
            await self.broadcast_interruption()
            await self.broadcast_frame(UserStartedSpeakingFrame)
        elif kind == 'input_audio_buffer.speech_stopped':
            await self.broadcast_frame(UserStoppedSpeakingFrame)
        elif kind == 'conversation.item.input_audio_transcription.completed':
            await self.push_frame(TranscriptionFrame(
                event.get('transcript', ''), 'user', datetime.now(UTC).isoformat(),
            ))
        elif kind == 'response.created':
            self._response_pending = False
            self._response_active = True
            self._settled.clear()
            if self._cancel_on_create:
                self._cancel_on_create = False
                await self._interrupt()
                return
            self._suppressed = False
            await self.push_frame(LLMFullResponseStartFrame())
        elif kind in ('response.done', 'response.cancelled'):
            await self._finish_response()
            self._response_pending = False
            self._settled.set()
            if event.get('response', {}).get('status') == 'failed':
                raise RuntimeError('Realtime response failed')
        elif kind == 'response.audio.delta' and self._response_active and not self._suppressed:
            if not self._audio_started:
                await self.push_frame(TTSStartedFrame())
                self._audio_started = True
            await self.push_frame(TTSAudioRawFrame(
                base64.b64decode(event['delta'], validate=True), 24000, 1,
            ))
        elif kind in ('response.audio_transcript.delta', 'response.text.delta'):
            if not self._suppressed and event.get('delta'):
                text = event['delta']
                # The current RTVI client consumes bot-output. Avoid duplicate legacy
                # bot-llm-text events and their unnecessary sentence-tokenizer dependency.
                frame = TTSTextFrame(text, aggregated_by='sentence')
                frame.includes_inter_frame_spaces = True
                await self.push_frame(frame)
