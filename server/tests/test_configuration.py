from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


def test_empty_config_starts_but_cannot_make_call():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert client.get('/api/health').status_code == 200
        status = client.get('/api/config').json()
        assert status['ready'] is False
        assert {'STT_PROVIDER', 'LLM_PROVIDER', 'TTS_PROVIDER'} <= set(status['missing'])
        response = client.post('/api/offer', json={'sdp': 'unused', 'type': 'offer'})
        assert response.status_code == 503


def test_status_never_exposes_secrets_and_requires_model_and_voice():
    settings = Settings(_env_file=None, stt_provider='deepgram', stt_api_key='secret-stt',
                        llm_provider='openai', llm_api_key='secret-llm',
                        tts_provider='cartesia', tts_api_key='secret-tts')
    with TestClient(create_app(settings)) as client:
        response = client.get('/api/config')
        assert 'secret-' not in response.text
        assert {'LLM_MODEL', 'TTS_VOICE', 'STT_MODEL', 'TTS_MODEL'} <= set(response.json()['missing'])


def test_unknown_provider_is_not_ready():
    with TestClient(create_app(Settings(_env_file=None, stt_provider='unknown'))) as client:
        config = client.get('/api/config').json()
        assert config['ready'] is False
        assert any('STT_PROVIDER' in issue for issue in config['issues'])


def test_complete_config_is_ready_without_contacting_vendors():
    settings = Settings(_env_file=None, stt_provider='openai', stt_api_key='a',
                        stt_model='whisper-1', llm_provider='openai-compatible',
                        llm_api_key='b', llm_model='configured-model',
                        llm_base_url='https://example.com/v1', tts_provider='openai',
                        tts_api_key='c', tts_model='tts-1', tts_voice='alloy')
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/config').json()['ready'] is True


def test_compatible_llm_requires_base_url():
    settings = Settings(_env_file=None, llm_provider='openai-compatible')
    assert 'LLM_BASE_URL' in settings.public_config()['missing']
