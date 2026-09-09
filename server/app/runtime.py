"""WebRTC signaling and bounded, cancellable per-call ownership."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from aiortc.sdp import candidate_from_sdp
from fastapi import HTTPException
from pipecat.transports.smallwebrtc.connection import IceServer, SmallWebRTCConnection

from app.bot import run_bot
from app.settings import Settings

logger = logging.getLogger(__name__)


@dataclass
class Session:
    connection: SmallWebRTCConnection
    task: asyncio.Task | None = None


class VoiceRuntime:
    def __init__(self, settings: Settings, *, bot_runner: Callable[..., Awaitable] = run_bot):
        self.settings = settings
        self.bot_runner = bot_runner
        self.sessions: dict[str, Session] = {}
        self.lock = asyncio.Lock()

    @property
    def active_count(self):
        return len(self.sessions)

    async def offer(self, body: dict) -> dict:
        async with self.lock:
            pc_id = body.get('pc_id')
            if pc_id:
                session = self.sessions.get(pc_id)
                if session is None:
                    raise HTTPException(404, detail='通话已结束，请重新连接')
                try:
                    await asyncio.wait_for(session.connection.renegotiate(
                        sdp=body['sdp'], type=body['type'],
                        restart_pc=body.get('restart_pc', False),
                    ), timeout=30)
                    return session.connection.get_answer()
                except Exception:
                    if session.task:
                        session.task.cancel()
                    raise HTTPException(400, detail='重新连接失败，请重新发起通话') from None
            if self.active_count >= self.settings.max_sessions:
                raise HTTPException(429, detail='当前通话数量已达上限，请先结束其他通话')
            if not body['sdp'].startswith('v=0') or 'm=audio' not in body['sdp']:
                raise HTTPException(400, detail='无效的音频通话请求')
            connection = SmallWebRTCConnection(ice_servers=[
                IceServer(**item.model_dump(exclude_none=True))
                for item in self.settings.ice_servers
            ])
            try:
                await asyncio.wait_for(connection.initialize(
                    sdp=body['sdp'], type=body['type'],
                ), timeout=30)
                answer = connection.get_answer()
                if not answer:
                    raise ValueError('Missing SDP answer')
            except BaseException as error:
                await connection.disconnect()
                if isinstance(error, asyncio.CancelledError):
                    raise
                raise HTTPException(400, detail='无法建立音频连接，请检查网络后重试') from None

            session = Session(connection)
            self.sessions[connection.pc_id] = session

            @connection.event_handler('closed')
            async def closed(connection):
                if (connection.pc_id in self.sessions and session.task
                        and session.task is not asyncio.current_task()):
                    session.task.cancel()

            session.task = asyncio.create_task(self._run_session(session))
            return answer

    async def _run_session(self, session: Session):
        try:
            async with asyncio.timeout(self.settings.session_timeout_seconds):
                await self.bot_runner(session.connection, self.settings)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Avoid logging provider payloads, transcripts or credentials.
            logger.warning('Voice session stopped (%s)', type(error).__name__)
        finally:
            self.sessions.pop(session.connection.pc_id, None)
            await session.connection.disconnect()

    async def patch(self, body: dict):
        session = self.sessions.get(body['pc_id'])
        if session is None:
            raise HTTPException(404, detail='通话不存在')
        try:
            for item in body['candidates']:
                candidate = candidate_from_sdp(item['candidate']) if item['candidate'] else None
                if candidate is not None:
                    candidate.sdpMid = item['sdp_mid']
                    candidate.sdpMLineIndex = item['sdp_mline_index']
                await session.connection.add_ice_candidate(candidate)
        except Exception:
            raise HTTPException(400, detail='无效的网络候选地址') from None

    async def close(self):
        async with self.lock:
            sessions = list(self.sessions.values())
            for session in sessions:
                if session.task:
                    session.task.cancel()
            await asyncio.gather(
                *(session.task for session in sessions if session.task), return_exceptions=True,
            )
            # Also handles a task cancelled before its coroutine entered its finally block.
            await asyncio.gather(
                *(session.connection.disconnect() for session in sessions), return_exceptions=True,
            )
            self.sessions.clear()
