from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROVIDERS = {
    'stt': ('openai', 'deepgram'),
    'llm': ('openai', 'openai-compatible'),
    'tts': ('openai', 'cartesia'),
}


class IceServerConfig(BaseModel):
    urls: str | list[str]
    username: str | None = None
    credential: str | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / '.env',
        env_file_encoding='utf-8', extra='ignore',
    )
    stt_provider: str = ''
    stt_api_key: SecretStr = SecretStr('')
    stt_model: str = ''
    stt_base_url: str = ''
    llm_provider: str = ''
    llm_api_key: SecretStr = SecretStr('')
    llm_model: str = ''
    llm_base_url: str = ''
    tts_provider: str = ''
    tts_api_key: SecretStr = SecretStr('')
    tts_model: str = ''
    tts_voice: str = ''
    tts_base_url: str = ''
    language: Literal['zh', 'en'] = 'zh'
    system_prompt: str = (
        '你是一位友好、耐心的个人语音助手。使用简体中文自然交流，'
        '每次回答尽量简洁，适合朗读，不使用 Markdown 格式。'
    )
    ice_servers: list[IceServerConfig] = []
    max_sessions: int = Field(default=2, ge=1, le=20)
    session_timeout_seconds: int = Field(default=1800, ge=30, le=7200)

    @field_validator('*', mode='before')
    @classmethod
    def strip_strings(cls, value):
        return value.strip() if isinstance(value, str) else value

    def public_config(self) -> dict:
        missing, issues, services = [], [], {}
        for stage, supported in PROVIDERS.items():
            provider = getattr(self, f'{stage}_provider')
            services[stage] = {'provider': provider or None, 'supported': list(supported)}
            for suffix in ('provider', 'api_key', 'model'):
                name = f'{stage}_{suffix}'
                value = getattr(self, name)
                if isinstance(value, SecretStr):
                    value = value.get_secret_value().strip()
                if not value:
                    missing.append(name.upper())
            if provider and provider not in supported:
                issues.append(f'{stage.upper()}_PROVIDER 不支持，请选择：{", ".join(supported)}')
        if not self.tts_voice:
            missing.append('TTS_VOICE')
        if self.llm_provider == 'openai-compatible' and not self.llm_base_url:
            missing.append('LLM_BASE_URL')
        if self.tts_provider == 'cartesia' and self.tts_base_url:
            issues.append('Cartesia 适配器使用默认端点，请清空 TTS_BASE_URL')
        for stage in PROVIDERS:
            url = getattr(self, f'{stage}_base_url')
            if url and not url.startswith(('http://', 'https://')):
                issues.append(f'{stage.upper()}_BASE_URL 必须是 HTTP(S) 地址')
        return {'ready': not missing and not issues, 'missing': missing,
                'issues': issues, 'services': services}
