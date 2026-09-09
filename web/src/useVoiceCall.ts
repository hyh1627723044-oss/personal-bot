import { useCallback, useEffect, useRef, useState } from 'react';
import { PipecatClient, RTVIEvent } from '@pipecat-ai/client-js';
import { useRTVIClientEvent } from '@pipecat-ai/client-react';
import { createClient, releaseClient, stopLocalTracks } from './client';

type Phase = 'idle' | 'connecting' | 'active' | 'stopping';
type Attempt = { client: PipecatClient; abort: AbortController };
type Options = { iceServers: RTCIceServer[] };

function abortable<T>(promise: Promise<T>, signal: AbortSignal): Promise<T> {
  return new Promise((resolve, reject) => {
    const aborted = () => reject(signal.reason ?? new DOMException('已取消', 'AbortError'));
    signal.addEventListener('abort', aborted, { once: true });
    promise.then(resolve, reject).finally(() => signal.removeEventListener('abort', aborted));
    if (signal.aborted) aborted();
  });
}

export function useVoiceCall(onClientCreated: (client: PipecatClient) => void) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [error, setError] = useState('');
  const [muted, setMuted] = useState(false);
  const [speaking, setSpeaking] = useState<'user' | 'bot' | null>(null);
  const [seconds, setSeconds] = useState(0);
  const current = useRef<Attempt | null>(null);
  const mounted = useRef(true);

  const finish = useCallback(async (message = '') => {
    const attempt = current.current;
    if (!attempt) return;
    current.current = null;
    attempt.abort.abort();
    setPhase('stopping'); setSpeaking(null); setMuted(false);
    if (message) setError(message);
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      await Promise.race([
        releaseClient(attempt.client),
        new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('断开超时')), 8000); }),
      ]);
    } catch {
      stopLocalTracks(attempt.client);
      if (mounted.current) setError(message || '连接已终止；如麦克风指示仍亮，请关闭页面。');
    } finally {
      clearTimeout(timer);
      if (mounted.current) setPhase('idle');
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    const release = () => {
      const attempt = current.current;
      current.current = null;
      attempt?.abort.abort();
      if (attempt) void releaseClient(attempt.client).catch(() => {});
    };
    window.addEventListener('pagehide', release);
    return () => { mounted.current = false; window.removeEventListener('pagehide', release); release(); };
  }, []);

  useEffect(() => {
    if (phase !== 'active') return;
    const started = Date.now();
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [phase]);

  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, useCallback(() => setSpeaking('bot'), []));
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, useCallback(() => setSpeaking(null), []));
  useRTVIClientEvent(RTVIEvent.UserStartedSpeaking, useCallback(() => setSpeaking('user'), []));
  useRTVIClientEvent(RTVIEvent.UserStoppedSpeaking, useCallback(() => setSpeaking(null), []));
  useRTVIClientEvent(RTVIEvent.Error, useCallback(() => {
    void finish('语音服务发生错误，请检查服务配置和供应商账户后重试。');
  }, [finish]));
  useRTVIClientEvent(RTVIEvent.Disconnected, useCallback(() => {
    if (current.current) void finish('通话已断开。可能是网络中断、服务异常或达到会话时限。');
  }, [finish]));

  const start = async (loadOptions: (signal: AbortSignal) => Promise<Options | null>) => {
    if (current.current || phase === 'stopping') return;
    const attempt: Attempt = { client: createClient(), abort: new AbortController() };
    current.current = attempt;
    setPhase('connecting'); setError(''); setSeconds(0); setMuted(false);
    onClientCreated(attempt.client);
    const { signal } = attempt.abort;
    const timer = setTimeout(() => {
      if (current.current === attempt) void finish('连接超时，请检查麦克风权限、网络和后端服务后重试。');
    }, 45000);
    // Permission prompts cannot be forcibly dismissed. If resolved after cancellation,
    // clean up that retired client without affecting a later call.
    const runStep = async <T,>(promise: Promise<T>) => {
      void promise.then(() => {
        if (signal.aborted) void releaseClient(attempt.client).catch(() => {});
      }, () => {});
      return abortable(promise, signal);
    };
    try {
      const options = await abortable(loadOptions(signal), signal);
      if (!options) { await finish(); return; }
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
        throw new Error('麦克风需要在 localhost 或 HTTPS 页面中使用。');
      }
      await runStep(attempt.client.initDevices());
      signal.throwIfAborted();
      await runStep(attempt.client.connect({
        webrtcRequestParams: { endpoint: '/api/offer', timeout: 30000 },
        iceConfig: { iceServers: options.iceServers },
      }));
      if (current.current === attempt && !signal.aborted) setPhase('active');
    } catch (cause) {
      if (!signal.aborted && current.current === attempt) {
        const denied = cause instanceof Error && /permission|denied|NotAllowed/i.test(cause.name + cause.message);
        const message = denied ? '请允许此网站使用麦克风后重试。'
          : cause instanceof Error ? cause.message : '连接失败，请检查服务配置后重试。';
        await finish(message);
      }
    } finally { clearTimeout(timer); }
  };

  const toggleMute = () => {
    if (!current.current || phase !== 'active') return;
    current.current.client.enableMic(muted);
    setMuted(!muted);
    if (!muted) setSpeaking(null);
  };

  return { phase, error, muted, speaking, seconds, start, hangup: finish, toggleMute };
}
