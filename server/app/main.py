import asyncio
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.settings import Settings


class Offer(BaseModel):
    sdp: str = Field(min_length=1, max_length=100_000)
    type: Literal['offer']
    pc_id: str | None = None
    restart_pc: bool = False


class Candidate(BaseModel):
    candidate: str = Field(max_length=4096)
    sdp_mid: str
    sdp_mline_index: int = Field(ge=0)


class Patch(BaseModel):
    pc_id: str
    candidates: list[Candidate] = Field(max_length=100)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    runtime = None
    runtime_lock = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(app):
        yield
        if runtime is not None:
            await runtime.close()

    app = FastAPI(title='Voice Assistant', lifespan=lifespan)

    @app.get('/api/health')
    async def health():
        return {'status': 'ok'}

    @app.get('/api/config')
    async def config():
        return settings.public_config()

    @app.get('/api/ice-servers')
    async def ice_servers():
        # TURN credentials are intentionally supplied to the browser, unlike AI keys.
        return [server.model_dump(exclude_none=True) for server in settings.ice_servers]

    @app.post('/api/offer')
    async def offer(body: Offer):
        nonlocal runtime
        status = settings.public_config()
        if not status['ready']:
            raise HTTPException(503, detail={'message': '请先完成后端语音服务配置', **status})
        async with runtime_lock:
            if runtime is None:
                from app.runtime import VoiceRuntime
                runtime = VoiceRuntime(settings)
        return await runtime.offer(body.model_dump())

    @app.patch('/api/offer')
    async def patch(body: Patch):
        if runtime is None:
            raise HTTPException(404, detail='通话不存在')
        await runtime.patch(body.model_dump())
        return {'status': 'ok'}

    return app


app = create_app()
