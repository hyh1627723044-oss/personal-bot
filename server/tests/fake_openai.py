"""Local test fixture only. Never selected by the production app."""

import asyncio
import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()
app.state.requests = []
app.state.active = 0
app.state.cancelled = 0


@app.post('/v1/chat/completions')
async def completions(request: Request):
    body = await request.json()
    app.state.requests.append({'body': body, 'auth': request.headers.get('authorization')})
    prompt = body['messages'][-1]['content']
    if prompt == '鉴权失败':
        return JSONResponse({'error': 'secret-upstream-detail'}, status_code=401)
    if prompt == '非流式':
        return JSONResponse({'choices': []})

    async def tokens():
        app.state.active += 1
        try:
            if prompt == '慢速':
                chunks = ['本地测试慢速回复。'] * 200
            else:
                chunks = ['本地测试回复：', prompt, f'（上下文 {len(body["messages"])} 条）']
            for text in chunks:
                await asyncio.sleep(.15 if prompt == '慢速' else .08)
                yield 'data: ' + json.dumps({'choices': [{'delta': {'content': text}}]}, ensure_ascii=False) + '\n\n'
            if prompt != '截断':
                yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
                yield 'data: [DONE]\n\n'
        except asyncio.CancelledError:
            app.state.cancelled += 1
            raise
        finally:
            app.state.active -= 1

    return StreamingResponse(tokens(), media_type='text/event-stream')
