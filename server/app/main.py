import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.settings import Settings
from app.chat import create_chat_router


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
        try:
            yield
        finally:
            if runtime is not None:
                await runtime.close()

    app = FastAPI(title='Voice Assistant', lifespan=lifespan)
    app.include_router(create_chat_router(settings))

    @app.get('/api/health')
    async def health():
        return {'status': 'ok'}

    @app.get('/api/config')
    async def config():
        return settings.public_config()

    @app.middleware('http')
    async def prevent_cached_config(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith('/api/'):
            response.headers.setdefault('Cache-Control', 'no-store')
        return response

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
                try:
                    from app.runtime import VoiceRuntime
                    runtime = VoiceRuntime(settings)
                except ImportError:
                    raise HTTPException(503, detail='语音组件缺失，请在后端目录执行 uv sync') from None
        return await runtime.offer(body.model_dump())

    @app.patch('/api/offer')
    async def patch(body: Patch):
        if runtime is None:
            raise HTTPException(404, detail='通话不存在')
        await runtime.patch(body.model_dump())
        return {'status': 'ok'}

    @app.api_route('/api/{path:path}', methods=['GET', 'POST', 'PATCH', 'DELETE', 'PUT'])
    async def unknown_api(path: str):
        raise HTTPException(404, detail='接口不存在')

    web_dist = Path(__file__).resolve().parents[2] / 'web' / 'dist'
    if web_dist.is_dir():
        app.mount('/', StaticFiles(directory=web_dist, html=True), name='web')

    return app


app = create_app()
