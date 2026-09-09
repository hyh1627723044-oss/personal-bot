"""One independent STT → LLM → TTS pipeline per call."""

import asyncio

from app.providers import create_services
from app.settings import Settings


async def run_bot(connection, config: Settings):
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.worker import PipelineParams, PipelineWorker
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.processors.aggregators.llm_response_universal import (
        LLMContextAggregatorPair,
        LLMUserAggregatorParams,
    )
    from pipecat.transports.base_transport import TransportParams
    from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
    from pipecat.workers.runner import WorkerRunner

    stt, llm, tts = create_services(config)
    transport = SmallWebRTCTransport(
        webrtc_connection=connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    )
    context = LLMContext([{'role': 'system', 'content': config.system_prompt}])
    user, assistant = LLMContextAggregatorPair(
        context, user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )
    worker = PipelineWorker(
        Pipeline([transport.input(), stt, user, llm, tts, transport.output(), assistant]),
        params=PipelineParams(audio_in_sample_rate=16000, audio_out_sample_rate=24000),
        enable_rtvi=True,
        idle_timeout_secs=120,
    )

    @transport.event_handler('on_client_disconnected')
    async def disconnected(transport, client):
        await worker.cancel()

    @worker.event_handler('on_pipeline_error')
    async def pipeline_error(worker, frame):
        # RTVI reports the error to the browser; stop spending on a broken call.
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    run_task = asyncio.create_task(runner.run())
    try:
        # Keep cancellation out of the runner's setup phase so it reaches cleanup.
        await asyncio.shield(run_task)
    finally:
        if not run_task.done():
            await runner.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(run_task), timeout=10)
            except (TimeoutError, asyncio.CancelledError):
                run_task.cancel()
                await asyncio.gather(run_task, return_exceptions=True)
