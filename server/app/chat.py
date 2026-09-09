import asyncio
import json
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from app.llm_backend import ModelServiceError, create_chat_backend
from app.settings import Settings


class ChatMessage(BaseModel):
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=16000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def validate_conversation(self):
        if self.messages[-1].role != 'user':
            raise ValueError('最后一条消息必须来自用户')
        if sum(len(item.content) for item in self.messages) > 64000:
            raise ValueError('对话过长，请开始新对话')
        if any(not item.content.strip() for item in self.messages):
            raise ValueError('消息不能为空白')
        return self


def event(name: str, payload: dict) -> str:
    return f'event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n'


def create_chat_router(settings: Settings) -> APIRouter:
    router = APIRouter()
    backend = create_chat_backend(settings)
    slots = asyncio.Semaphore(settings.max_sessions)

    @router.post('/api/chat')
    async def chat(body: ChatRequest):
        status = settings.public_config()
        if not status['text_ready']:
            raise HTTPException(503, detail={
                'message': '请先配置对话模型，文字聊天不需要语音服务',
                'missing': status['text_missing'],
            })
        if slots.locked():
            raise HTTPException(429, detail='正在处理其他回复，请稍后重试')
        await slots.acquire()

        async def stream():
            try:
                messages = [{'role': 'system', 'content': settings.system_prompt}]
                messages.extend(message.model_dump() for message in body.messages)
                emitted = False
                async with asyncio.timeout(180):
                    async for text in backend.stream(messages):
                        emitted = True
                        yield event('delta', {'text': text})
                if not emitted:
                    yield event('error', {'message': '模型没有返回文字，请检查模型或 Agent 输出。'})
                else:
                    yield event('done', {})
            except ModelServiceError as error:
                yield event('error', {'message': str(error)})
            except TimeoutError:
                yield event('error', {'message': '本次回复已超时，请重试或缩短问题。'})
            except asyncio.CancelledError:
                raise
            except Exception:
                yield event('error', {'message': '回复生成失败，请检查后端服务。'})
            finally:
                slots.release()

        return StreamingResponse(stream(), media_type='text/event-stream', headers={
            'Cache-Control': 'no-cache, no-transform', 'X-Accel-Buffering': 'no',
        })

    return router
