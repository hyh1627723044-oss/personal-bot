"""Exercise the production WebRTC/Pipecat path; replace only paid services."""
import asyncio
import copy
import json

from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from pipecat.frames.frames import LLMContextFrame
from pipecat.processors.frame_processor import FrameProcessor

from app.runtime import VoiceRuntime
from app.settings import Settings


async def test_typed_turns_share_the_active_voice_pipeline(monkeypatch):
    contexts = asyncio.Queue()

    class Passthrough(FrameProcessor):
        async def process_frame(self, frame, direction):
            await super().process_frame(frame, direction)
            await self.push_frame(frame, direction)

    class CaptureModel(FrameProcessor):
        async def process_frame(self, frame, direction):
            await super().process_frame(frame, direction)
            if isinstance(frame, LLMContextFrame):
                await contexts.put(copy.deepcopy(frame.context.get_messages()))
            else:
                await self.push_frame(frame, direction)

    monkeypatch.setattr('app.bot.create_services', lambda config: (
        Passthrough(), CaptureModel(), Passthrough(),
    ))
    runtime = VoiceRuntime(Settings(_env_file=None))
    peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
    channel = peer.createDataChannel('rtvi')
    ready = asyncio.Event()

    @channel.on('message')
    def message(raw):
        if json.loads(raw).get('type') == 'bot-ready':
            ready.set()

    def send(kind, data):
        channel.send(json.dumps({'label': 'rtvi-ai', 'id': kind, 'type': kind, 'data': data}))

    try:
        async with asyncio.timeout(30):
            peer.addTransceiver('audio', direction='sendrecv')
            await peer.setLocalDescription(await peer.createOffer())
            answer = await runtime.offer({'sdp': peer.localDescription.sdp, 'type': 'offer'})
            await peer.setRemoteDescription(RTCSessionDescription(sdp=answer['sdp'], type='answer'))
            while channel.readyState != 'open':
                await asyncio.sleep(.02)
            send('client-ready', {'version': '2.1.0', 'about': {'library': 'local-test'}})
            await ready.wait()
            for text in ('我叫小明', '接着刚才的话聊'):
                send('send-text', {'content': text, 'options': {
                    'run_immediately': True, 'audio_response': True,
                }})
                messages = await contexts.get()
                assert messages[-1] == {'role': 'user', 'content': text}
            assert [item['content'] for item in messages if item['role'] == 'user'] == [
                '我叫小明', '接着刚才的话聊',
            ]
            assert runtime.active_count == 1
    finally:
        async def close_all():
            await peer.close()
            await runtime.close()
        await asyncio.wait_for(close_all(), 12)
    assert runtime.active_count == 0
