import { useCallback, useEffect, useRef, useState } from 'react';
import type { PipecatClient } from '@pipecat-ai/client-js';
import { usePipecatConversation } from '@pipecat-ai/client-react';
import { ArrowUpRight, AudioLines, Check, ChevronDown, CircleHelp, Headphones, LoaderCircle, MessageSquare, Mic, MicOff, Phone, PhoneOff, RefreshCw, ShieldCheck, SlidersHorizontal, Sparkles, Waves, X } from 'lucide-react';
import { transcriptText } from './transcript';
import { useVoiceCall } from './useVoiceCall';
import TextChat from './TextChat';
import VoiceComposer from './VoiceComposer';

type Service = { provider: string | null; supported: string[]; configured: boolean };
type Config = { ready: boolean; voice_engine: 'cascade' | 'realtime'; text_ready: boolean; text_missing: string[]; text_issues: string[]; missing: string[]; issues: string[]; services: Record<string, Service> };

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const timeout = AbortSignal.timeout(10000);
  const response = await fetch(path, { signal: signal ? AbortSignal.any([signal, timeout]) : timeout });
  if (!response.ok) throw new Error('无法连接服务，请检查后端是否启动。');
  return response.json() as Promise<T>;
}

function Transcript() {
  const { messages } = usePipecatConversation();
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }, [messages]);
  const visible = messages.filter(message => message.role !== 'system');
  return <div className="transcript-body" role="log" aria-label="本次通话字幕" aria-live="polite">
    {!visible.length ? <div className="empty-transcript"><span><MessageSquare size={23} /></span><h3>对话，从一声你好开始</h3><p>通话开始后，你和助手的对话<br/>会实时显示在这里。</p></div> : visible.map((message, index) => <div className={`message ${message.role}`} key={index}>
      <div className="message-name">{message.role === 'user' ? '你' : '轻声'}</div>
      <p>{message.parts?.map((part, i) => <span key={i}>{transcriptText(part.text)}</span>)}</p>
    </div>)}
    <div ref={end}/>
  </div>;
}

export default function App({ onClientCreated }: { onClientCreated: (client: PipecatClient) => void }) {
  const [config, setConfig] = useState<Config | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [settings, showSettings] = useState(false);
  const [help, showHelp] = useState(false);
  const [mode, setMode] = useState<'text' | 'voice'>('text');
  const call = useVoiceCall(onClientCreated);
  const { muted, speaking, seconds, toggleMute, hangup } = call;
  const active = call.phase === 'active';
  const connecting = call.phase === 'connecting';
  const stopping = call.phase === 'stopping';
  const pending = connecting || stopping;
  const displayedError = error || (mode === 'voice' ? call.error : '');
  const modeReady = mode === 'text' ? config?.text_ready : config?.ready;
  const missingFields = (mode === 'text' ? config?.text_missing : config?.missing) ?? [];
  const configIssues = (mode === 'text' ? config?.text_issues : config?.issues) ?? [];
  const serviceRows = config?.voice_engine === 'realtime'
    ? [['llm', '对话模型（文字模式）'], ['realtime', '实时语音模型（通话）']]
    : [['llm', '对话模型'], ['stt', '语音识别（通话时需要）'], ['tts', '语音合成（通话时需要）']];
  const modalRef = useRef<HTMLElement>(null);
  const [switching, setSwitching] = useState(false);
  const switchLock = useRef(false);
  const selectMode = async (next: 'text' | 'voice') => {
    if (next === mode || switchLock.current) return;
    switchLock.current = true; setSwitching(true);
    try {
      if (next === 'text') await hangup();
      setMode(next);
    } finally { switchLock.current = false; setSwitching(false); }
  };

  const refresh = useCallback(async () => {
    setLoading(true);
    try { setConfig(await getJson<Config>('/api/config')); setError(''); }
    catch { setConfig(null); setError('无法连接后端。请启动语音服务后重试。'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!settings && !help) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { showSettings(false); showHelp(false); }
      if (event.key !== 'Tab') return;
      const buttons = modalRef.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)');
      if (!buttons?.length) return;
      const first = buttons[0], last = buttons[buttons.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', keydown);
    return () => { document.removeEventListener('keydown', keydown); previousFocus?.focus(); };
  }, [settings, help]);

  const start = async () => {
    setError('');
    await call.start(async signal => {
      const current = await getJson<Config>('/api/config', signal);
      setConfig(current);
      if (!current.ready) { showSettings(true); return null; }
      const iceServers = await getJson<RTCIceServer[]>('/api/ice-servers', signal);
      return { iceServers };
    });
  };
  const callStatus = stopping ? '正在结束通话…' : connecting ? '正在连接语音服务…' : active ? muted ? '麦克风已静音' : speaking === 'bot' ? '轻声正在回答' : speaking === 'user' ? '正在听你说' : '我在听，请说吧' : '准备好，聊一聊';
  const duration = `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`;

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="轻声首页"><span className="brand-symbol"><AudioLines size={24}/></span><span>轻声<small>YOUR VOICE COMPANION</small></span></a>
      <div className="nav-label">我的空间</div>
      <button disabled={switching || stopping} className={`nav-item ${mode === 'text' ? 'selected' : ''}`} onClick={() => { void selectMode('text'); }}><MessageSquare size={18}/>文字模式{mode === 'text' && <span className="nav-dot"/>}</button>
      <button disabled={switching || stopping} className={`nav-item ${mode === 'voice' ? 'selected' : ''}`} onClick={() => { void selectMode('voice'); }}><Headphones size={18}/>语音模式{(mode === 'voice' || active) && <span className="nav-dot"/>}</button>
      <button className="nav-item" onClick={() => showSettings(true)}><SlidersHorizontal size={18}/>服务配置</button>
      <div className="sidebar-bottom"><div className="privacy"><ShieldCheck size={18}/><div>只专注此刻的对话<p>本次对话不保存到历史记录</p></div></div><button className="nav-item" onClick={() => showHelp(true)}><CircleHelp size={18}/>使用帮助<ArrowUpRight size={15}/></button><div className="profile"><span>我</span><div>个人空间<small>语音助手 · MVP</small></div></div></div>
    </aside>
    <main>
      <header><div className="breadcrumb">个人空间<span>/</span><strong>{mode === 'text' ? '文字聊天' : '语音对话'}</strong></div><button className={`service-pill ${modeReady ? 'online' : ''}`} onClick={() => showSettings(true)}><i/>{loading ? '检查服务中' : modeReady ? '服务已配置' : '服务待配置'}<ChevronDown size={13}/></button></header>
      <div className="workspace">
        <div className="page-title"><div className="eyebrow">A LITTLE SPACE TO TALK</div><h1>说出来，轻松一点。</h1><p>想法、问题，或今天的小事。我在这里听你说。</p></div>
        <div className="mode-switch" aria-label="对话方式"><button disabled={switching || stopping} className={mode === 'text' ? 'selected' : ''} aria-pressed={mode === 'text'} onClick={() => { void selectMode('text'); }}><MessageSquare size={15}/>文字模式</button><button disabled={switching || stopping} className={mode === 'voice' ? 'selected' : ''} aria-pressed={mode === 'voice'} onClick={() => { void selectMode('voice'); }}><Headphones size={15}/>语音模式{active ? ' · 通话中' : ''}</button></div>
        {displayedError && <div className="error-banner" role="alert">{displayedError}<button onClick={() => { void refresh(); }} aria-label="重新检查连接"><RefreshCw size={16}/></button></div>}
        <div hidden={mode !== 'text'}><TextChat enabled={mode === 'text'} ready={Boolean(config?.text_ready)} onConfigure={() => showSettings(true)}/></div>
        <div hidden={mode !== 'voice'}>
        <div className="conversation-grid">
          <section className="call-card" aria-label="语音通话">
            <div className="card-top"><span><i className={active ? 'green-dot' : 'gray-dot'}/>{active ? '通话中' : '语音空间'}</span><span className="timer">{duration}</span></div>
            <div className={`orb-scene ${active && !muted ? 'is-active' : ''} ${speaking === 'bot' ? 'is-speaking' : ''}`}><div className="orbit orbit-one"/><div className="orbit orbit-two"/><div className="orb"><div className="orb-shine"/><AudioLines size={54} strokeWidth={1.4}/></div><span className="orb-spark"><Sparkles size={14}/></span></div>
            <h2 aria-live="polite">{callStatus}</h2><p className="call-description">{active ? '自然地说话，你可以随时打断我的回答。' : '点击下方按钮，开启一段自然的对话。'}</p>
            <div className="waveform" aria-hidden="true">{Array.from({ length: 35 }, (_, i) => <i key={i} style={{ height: `${4 + ((i * 7) % 13)}px`, animationDelay: `${i * .05}s` }} className={active && speaking ? 'moving' : ''}/>)}</div>
            <div className="call-controls"><button className={`icon-button ${muted ? 'muted' : ''}`} onClick={toggleMute} disabled={!active || pending} aria-label={muted ? '取消静音' : '静音'} aria-pressed={muted}>{muted ? <MicOff size={21}/> : <Mic size={21}/>}</button><button className={`primary-button ${active ? 'hangup' : ''}`} onClick={() => { void (active || connecting ? hangup() : start()); }} disabled={stopping || (loading && !active && !connecting)}>{pending ? <LoaderCircle className="spin" size={19}/> : active ? <PhoneOff size={19}/> : <Phone size={19}/>} {stopping ? '正在结束' : connecting ? '取消连接' : active ? '结束通话' : '开始通话'}</button><button className="icon-button" onClick={() => showSettings(true)} aria-label="打开服务配置"><SlidersHorizontal size={20}/></button></div>
            <div className="call-footnote"><ShieldCheck size={13}/> {active ? '通话结束后，服务端会话自动释放' : '开始通话时，会请求使用你的麦克风'}</div>
          </section>
          <section className="transcript-card"><div className="transcript-heading"><h2><MessageSquare size={17}/>实时对话</h2><span>语音与文字</span></div><Transcript/><VoiceComposer active={active && !switching} onSend={call.sendText}/></section>
        </div>
        <div className="tips"><div><span><Waves size={19}/></span><section><h3>像聊天一样自然</h3><p>不用长按，说完后我会自动回应。</p></section></div><div><span><Mic size={18}/></span><section><h3>随时接着说</h3><p>有新的想法，直接开口打断我。</p></section></div><div><span><Headphones size={19}/></span><section><h3>戴上耳机更清晰</h3><p>安静的环境，让对话更顺畅。</p></section></div></div>
        </div>
        <footer><span>留一点时间，给自己的想法。</span><span>POWERED BY PIPECAT</span></footer>
      </div>
    </main>
    {(settings || help) && <div className="modal-backdrop" onClick={() => { showSettings(false); showHelp(false); }}><section ref={modalRef} role="dialog" aria-modal="true" aria-label={settings ? '服务配置' : '使用帮助'} className="modal" onClick={event => event.stopPropagation()}><button autoFocus className="modal-close icon-button" aria-label="关闭" onClick={() => { showSettings(false); showHelp(false); }}><X size={20}/></button>{settings ? <><div className="eyebrow">SERVICE SETUP</div><h2>连接你的助手</h2><p>在后端 <code>server/.env</code> 中配置服务并重启后端，然后点击重新检查。文字模式使用对话模型；语音模式可选择实时语音模型，或语音识别、对话模型与语音合成的组合。密钥只保存在后端。</p><div className="service-list">{serviceRows.map(([key, title]) => <div key={key}><span>{title}</span><strong>{config?.services[key]?.provider || '尚未选择'}</strong>{config?.services[key]?.configured ? <Check size={16}/> : <span className="pending-dot"/>}</div>)}</div>{missingFields.length ? <div className="missing"><h3>待填写配置</h3><div>{missingFields.map(item => <code key={item}>{item}</code>)}</div></div> : null}{configIssues.map(issue => <p className="issue" key={issue}>{issue}</p>)}{!config && <p>暂时无法读取配置，请确认后端已启动。</p>}<button className="primary-button" onClick={() => { void refresh(); }} disabled={loading}><RefreshCw size={16} className={loading ? 'spin' : ''}/>{loading ? '检查中…' : '重新检查'}</button></> : <><div className="eyebrow">GETTING STARTED</div><h2>让我们开始聊天</h2><ol><li>文字聊天：配置对话模型后，直接输入消息并发送；支持停止生成和新对话。</li><li>语音通话：配置实时语音模型，或补齐语音识别和合成，点击「开始通话」并允许使用麦克风。</li><li>直接说话，等待助手回答；回答期间可以开口打断。</li><li>点击麦克风按钮静音，点击「结束通话」挂断。</li></ol><p>本机请通过 localhost 打开网页。远程使用需要 HTTPS。服务的模型与密钥配置方式见项目 README。</p></>}</section></div>}
  </div>;
}
