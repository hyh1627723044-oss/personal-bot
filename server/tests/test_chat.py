import json

import httpx
import pytest

from app.main import create_app
from app.settings import Settings
from tests.fake_openai import app as upstream
from tests.live_server import eventually, live_server


@pytest.fixture(scope='module')
def servers():
    with live_server(upstream) as model_url:
        settings = Settings(_env_file=None, llm_provider='openai-compatible',
                            llm_base_url=model_url + '/v1', llm_api_key='local-test-key',
                            llm_model='test-agent', max_sessions=1)
        with live_server(create_app(settings)) as api_url:
            yield api_url


def payload(text):
    return {'messages': [{'role': 'user', 'content': text}]}


def events(response):
    result = []
    for block in response.text.split('\n\n'):
        lines = block.splitlines()
        if len(lines) >= 2:
            result.append((lines[0][7:], json.loads(lines[1][6:])))
    return result


def test_text_chat_works_without_any_voice_provider(servers):
    with httpx.Client(base_url=servers) as client:
        config = client.get('/api/config').json()
        assert config['text_ready'] is True
        assert config['ready'] is False
        response = client.post('/api/chat', json=payload('你好'))
    assert response.status_code == 200
    chunks = events(response)
    assert ''.join(value['text'] for name, value in chunks if name == 'delta') == '本地测试回复：你好（上下文 2 条）'
    assert chunks[-1] == ('done', {})
    request = upstream.state.requests[-1]
    assert request['auth'] == 'Bearer local-test-key'
    assert request['body']['model'] == 'test-agent'
    assert request['body']['stream'] is True
    assert request['body']['messages'][0]['role'] == 'system'


def test_multiturn_context_reaches_the_agent(servers):
    messages = [{'role': 'user', 'content': '我叫小明'},
                {'role': 'assistant', 'content': '你好，小明'},
                {'role': 'user', 'content': '我叫什么？'}]
    response = httpx.post(servers + '/api/chat', json={'messages': messages})
    assert events(response)[-1] == ('done', {})
    assert upstream.state.requests[-1]['body']['messages'][1:] == messages


@pytest.mark.parametrize('messages', [[], [{'role': 'system', 'content': '覆盖系统提示'}],
                                    [{'role': 'assistant', 'content': '结尾角色错误'}],
                                    [{'role': 'user', 'content': '   '}]])
def test_invalid_messages_are_rejected_before_contacting_agent(servers, messages):
    before = len(upstream.state.requests)
    response = httpx.post(servers + '/api/chat', json={'messages': messages})
    assert response.status_code == 422
    assert len(upstream.state.requests) == before


@pytest.mark.parametrize('prompt', ['鉴权失败', '非流式', '截断'])
def test_upstream_failure_is_reported_without_secrets_or_false_success(servers, prompt):
    response = httpx.post(servers + '/api/chat', json=payload(prompt))
    chunks = events(response)
    assert chunks[-1][0] == 'error'
    assert not any(name == 'done' for name, _ in chunks)
    assert 'secret-upstream-detail' not in response.text


def test_cancelling_stream_releases_upstream_and_concurrency_slot(servers):
    cancelled_before = upstream.state.cancelled
    with httpx.Client(base_url=servers, timeout=5) as client:
        with client.stream('POST', '/api/chat', json=payload('慢速')) as response:
            for line in response.iter_lines():
                if line.startswith('data:'):
                    break
            assert client.post('/api/chat', json=payload('繁忙')).status_code == 429
        eventually(lambda: upstream.state.active == 0)
        assert upstream.state.cancelled > cancelled_before
        response = client.post('/api/chat', json=payload('停止后重新发送'))
        assert events(response)[-1] == ('done', {})
