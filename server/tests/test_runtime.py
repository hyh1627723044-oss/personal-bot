import asyncio

import pytest
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from fastapi import HTTPException

from app.runtime import VoiceRuntime
from app.settings import Settings


async def wait_for_disconnect(connection, settings):
    # Replace only the paid AI pipeline, retaining real SDP/ICE/DTLS and lifecycle.
    await asyncio.Event().wait()


async def make_offer(peer):
    peer.addTransceiver('audio', direction='sendrecv')
    peer.createDataChannel('rtvi')
    await peer.setLocalDescription(await peer.createOffer())
    return {'sdp': peer.localDescription.sdp, 'type': 'offer'}


async def test_real_webrtc_negotiates_and_shutdown_releases_session():
    runtime = VoiceRuntime(Settings(_env_file=None, max_sessions=1), bot_runner=wait_for_disconnect)
    peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
    try:
        answer = await runtime.offer(await make_offer(peer))
        assert answer['type'] == 'answer'
        assert 'm=audio' in answer['sdp']
        await peer.setRemoteDescription(RTCSessionDescription(sdp=answer['sdp'], type='answer'))
        async with asyncio.timeout(15):
            while peer.connectionState != 'connected':
                await asyncio.sleep(.05)
        assert runtime.active_count == 1
        with pytest.raises(HTTPException) as caught:
            await runtime.offer({'sdp': 'unused', 'type': 'offer'})
        assert caught.value.status_code == 429
        await runtime.close()
        assert runtime.active_count == 0
    finally:
        await peer.close()
        await runtime.close()


async def test_bad_sdp_does_not_leak_a_session():
    runtime = VoiceRuntime(Settings(_env_file=None), bot_runner=wait_for_disconnect)
    try:
        with pytest.raises(HTTPException) as caught:
            await runtime.offer({'sdp': 'not-an-sdp', 'type': 'offer'})
        assert caught.value.status_code == 400
        assert runtime.active_count == 0
    finally:
        await runtime.close()


async def test_unknown_reconnect_is_rejected():
    runtime = VoiceRuntime(Settings(_env_file=None), bot_runner=wait_for_disconnect)
    with pytest.raises(HTTPException) as caught:
        await runtime.offer({'sdp': 'unused', 'type': 'offer', 'pc_id': 'missing'})
    assert caught.value.status_code == 404
