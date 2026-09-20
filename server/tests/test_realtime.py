"""Use a local provider WebSocket and real WebRTC/RTVI, without paid credentials."""
import asyncio
import base64
import json
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest
from aiortc import AudioStreamTrack, RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from websockets.asyncio.server import serve

from app.realtime import RealtimeService
from app.runtime import VoiceRuntime
from app.settings import Settings


def config(provider='qwen', **kwargs):
    return Settings(_env_file=None, voice_engine='realtime', realtime_provider=provider,
                    realtime_api_key='test-secret', realtime_model='test-model',
                    realtime_voice='test-voice',
                    realtime_base_url=kwargs.pop('realtime_base_url', 'wss://example.com/realtime'),
                    **kwargs)


def test_realtime_readiness_is_independent_of_cascade_and_text():
    status = config().public_config()
    assert status['ready'] and not status['text_ready']
    assert 'LLM_API_KEY' in status['text_missing']
    assert status['missing'] == []
    assert 'test-secret' not in json.dumps(status)
    invalid = config(realtime_base_url='https://example.com').public_config()
    assert not invalid['ready']
    assert any('REALTIME_BASE_URL' in error for error in invalid['issues'])


async def test_interruption_cancels_and_discards_late_audio():
    service = RealtimeService(config())
    service._ws = AsyncMock()
    service.push_frame = AsyncMock()
    await service._event({'type': 'response.created'})
    await service._interrupt()
    sent = json.loads(service._ws.send.call_args.args[0])
    assert sent['type'] == 'response.cancel'
    service.push_frame.reset_mock()
    await service._event({'type': 'response.audio.delta', 'delta': 'AAAA'})
    service.push_frame.assert_not_called()
    await service._event({'type': 'response.done'})
    assert service._settled.is_set()


async def test_interruption_before_response_created_cancels_when_it_arrives():
    service = RealtimeService(config())
    service._ws = AsyncMock()
    service.push_frame = AsyncMock()
    service._response_pending = True
    await service._interrupt()
    service._ws.send.assert_not_called()
    await service._event({'type': 'response.created'})
    assert json.loads(service._ws.send.call_args.args[0])['type'] == 'response.cancel'
    assert service._suppressed


@pytest.mark.parametrize('provider,rate,fmt', [('qwen', 16000, 'pcm'), ('stepfun', 24000, 'pcm16')])
async def test_realtime_voice_and_typed_turns(provider, rate, fmt):
    requests = asyncio.Queue()
    audio_received = asyncio.Event()
    provider_closed = asyncio.Event()
    transcripts = asyncio.Queue()
    bot_text = asyncio.Event()

    async def vendor(ws):
        try:
            assert ws.request.headers['Authorization'] == 'Bearer test-secret'
            assert parse_qs(urlsplit(ws.request.path).query)['model'] == ['test-model']
            await ws.send(json.dumps({'type': 'session.created'}))
            session = json.loads(await ws.recv())
            await requests.put(session)
            await ws.send(json.dumps({'type': 'session.updated'}))
            async for raw in ws:
                event = json.loads(raw)
                if event['type'] == 'input_audio_buffer.append':
                    audio = base64.b64decode(event['audio'])
                    # WebRTC input transport emits 10 ms mono PCM chunks.
                    assert len(audio) % 2 == 0 and len(audio) > 0
                    audio_received.set()
                elif event['type'] == 'conversation.item.create':
                    await requests.put(event)
                elif event['type'] == 'response.create':
                    for reply in [
                        {'type': 'response.created', 'response': {'id': 'r1'}},
                        {'type': 'conversation.item.input_audio_transcription.completed',
                         'transcript': '语音测试'},
                        {'type': 'response.audio_transcript.delta', 'delta': '收到'},
                        {'type': 'response.audio.delta',
                         'delta': base64.b64encode(bytes(4800)).decode()},
                        {'type': 'response.done', 'response': {'status': 'completed'}},
                    ]:
                        await ws.send(json.dumps(reply))
        finally:
            provider_closed.set()

    async with serve(vendor, '127.0.0.1', 0) as server:
        port = server.sockets[0].getsockname()[1]
        runtime = VoiceRuntime(config(provider, realtime_base_url=f'ws://127.0.0.1:{port}'))
        peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        peer.addTrack(AudioStreamTrack())
        channel = peer.createDataChannel('rtvi')
        ready = asyncio.Event()

        @channel.on('message')
        def message(raw):
            event = json.loads(raw)
            if event['type'] == 'bot-ready':
                ready.set()
            elif event['type'] == 'user-transcription':
                transcripts.put_nowait(event['data']['text'])
            elif event['type'] == 'bot-output' and event['data']['text'] == '收到':
                bot_text.set()

        def send(kind, data):
            channel.send(json.dumps({'label': 'rtvi-ai', 'id': kind, 'type': kind, 'data': data}))

        try:
            async with asyncio.timeout(30):
                await peer.setLocalDescription(await peer.createOffer())
                answer = await runtime.offer({'sdp': peer.localDescription.sdp, 'type': 'offer'})
                await peer.setRemoteDescription(RTCSessionDescription(sdp=answer['sdp'], type='answer'))
                while channel.readyState != 'open':
                    await asyncio.sleep(.02)
                send('client-ready', {'version': '2.1.0', 'about': {'library': 'test'}})
                await ready.wait()
                session = await requests.get()
                assert session['session']['input_audio_format'] == fmt
                assert session['session']['turn_detection']['type'] == 'server_vad'
                await audio_received.wait()
                for text in ('我叫小明', '我叫什么'):
                    bot_text.clear()
                    send('send-text', {'content': text, 'options': {
                        'run_immediately': True, 'audio_response': True,
                    }})
                    item = await requests.get()
                    assert item['item']['content'] == [{'type': 'input_text', 'text': text}]
                    assert await transcripts.get() == '语音测试'
                    await bot_text.wait()
                assert runtime.active_count == 1
        finally:
            await asyncio.wait_for(runtime.close(), 12)
            await asyncio.wait_for(peer.close(), 5)
        await asyncio.wait_for(provider_closed.wait(), 3)
        assert runtime.active_count == 0
