"""Service adapters. Add new Pipecat providers here and in settings.PROVIDERS."""

from app.settings import Settings


def create_services(config: Settings):
    # Lazy imports keep the unconfigured web app fast to start.
    from pipecat.services.openai.llm import OpenAILLMService
    from pipecat.transcriptions.language import Language

    language = Language.ZH if config.language == 'zh' else Language.EN
    if config.stt_provider == 'openai':
        from pipecat.services.openai.stt import OpenAISTTService
        stt = OpenAISTTService(
            api_key=config.stt_api_key.get_secret_value(),
            base_url=config.stt_base_url or None,
            settings=OpenAISTTService.Settings(model=config.stt_model, language=language),
        )
    elif config.stt_provider == 'deepgram':
        from pipecat.services.deepgram.stt import DeepgramSTTService
        stt = DeepgramSTTService(
            api_key=config.stt_api_key.get_secret_value(),
            base_url=config.stt_base_url,
            settings=DeepgramSTTService.Settings(
                model=config.stt_model, language=language, interim_results=True,
            ),
        )
    else:
        raise ValueError('Unsupported STT provider')

    if config.llm_provider not in ('openai', 'openai-compatible'):
        raise ValueError('Unsupported LLM provider')
    llm = OpenAILLMService(
        api_key=config.llm_api_key.get_secret_value(),
        base_url=config.llm_base_url or None,
        settings=OpenAILLMService.Settings(model=config.llm_model),
    )

    if config.tts_provider == 'openai':
        from pipecat.services.openai.tts import OpenAITTSService
        tts = OpenAITTSService(
            api_key=config.tts_api_key.get_secret_value(),
            base_url=config.tts_base_url or None,
            settings=OpenAITTSService.Settings(model=config.tts_model, voice=config.tts_voice),
        )
    elif config.tts_provider == 'cartesia':
        from pipecat.services.cartesia.tts import CartesiaTTSService
        tts = CartesiaTTSService(
            api_key=config.tts_api_key.get_secret_value(),
            settings=CartesiaTTSService.Settings(
                model=config.tts_model, voice=config.tts_voice, language=language,
            ),
        )
    else:
        raise ValueError('Unsupported TTS provider')
    return stt, llm, tts
