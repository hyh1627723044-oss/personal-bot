"""Text model boundary. Custom agents can implement ChatBackend or expose OpenAI HTTP."""

import json
from collections.abc import AsyncIterator
from typing import Protocol

import httpx

from app.settings import Settings


class ModelServiceError(Exception):
    """A user-safe error; never include upstream payloads or credentials."""


class ChatBackend(Protocol):
    def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]: ...


class OpenAICompatibleBackend:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        base_url = self.settings.llm_base_url or 'https://api.openai.com/v1'
        headers = {
            'Authorization': f'Bearer {self.settings.llm_api_key.get_secret_value()}',
            'Accept': 'text/event-stream',
        }
        body = {'model': self.settings.llm_model, 'messages': messages, 'stream': True}
        completed = False
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10)) as client:
                async with client.stream('POST', f'{base_url.rstrip("/")}/chat/completions',
                                         headers=headers, json=body) as response:
                    if response.status_code in (401, 403):
                        raise ModelServiceError('模型服务鉴权失败，请检查 LLM_API_KEY 和接口权限。')
                    if response.status_code == 429:
                        raise ModelServiceError('模型服务额度不足或请求过于频繁，请稍后重试。')
                    if response.status_code >= 400:
                        raise ModelServiceError(
                            f'模型服务返回 HTTP {response.status_code}，请检查 URL、模型名或 Agent 服务。'
                        )
                    if 'text/event-stream' not in response.headers.get('content-type', ''):
                        raise ModelServiceError('接口未返回 SSE 流，请确认支持 OpenAI 流式 Chat Completions。')
                    async for line in response.aiter_lines():
                        if not line.startswith('data:'):
                            continue
                        data = line[5:].strip()
                        if not data:
                            continue
                        if data == '[DONE]':
                            completed = True
                            break
                        try:
                            chunk = json.loads(data)
                            if not isinstance(chunk, dict) or chunk.get('error'):
                                raise ModelServiceError('模型或 Agent 服务返回了错误响应。')
                            choices = chunk.get('choices', [])
                            if not choices:
                                continue  # Usage-only chunks are legal.
                            choice = choices[0]
                            if choice.get('finish_reason') is not None:
                                completed = True
                            content = (choice.get('delta') or {}).get('content')
                            if isinstance(content, str) and content:
                                yield content
                        except (ValueError, TypeError, AttributeError, KeyError, IndexError):
                            raise ModelServiceError('模型服务返回格式不兼容，请检查 Agent 的流式协议。') from None
        except httpx.TimeoutException:
            raise ModelServiceError('模型服务响应超时，请稍后重试。') from None
        except httpx.HTTPError:
            raise ModelServiceError('无法连接模型服务，请检查 LLM_BASE_URL 和网络。') from None
        if not completed:
            raise ModelServiceError('模型连接提前结束，回复可能不完整，请重试。')


def create_chat_backend(settings: Settings) -> ChatBackend:
    # Replace this factory to call an in-process agent with the same stream contract.
    return OpenAICompatibleBackend(settings)
