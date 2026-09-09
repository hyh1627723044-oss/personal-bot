import { useEffect, useRef, useState } from 'react';
import { ArrowUp, MessageSquarePlus, RefreshCw, SlidersHorizontal, Sparkles, Square } from 'lucide-react';
import { streamChat, type RequestMessage } from './chatApi';
import './chat.css';

type Message = RequestMessage & { id: string; state?: 'streaming' | 'complete' | 'stopped' | 'error' };
type Request = { abort: AbortController; assistantId: string; history: Message[] };

export default function TextChat({ ready, enabled = true, onConfigure }: { ready: boolean; enabled?: boolean; onConfigure: () => void }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [retryHistory, setRetryHistory] = useState<Message[] | null>(null);
  const current = useRef<Request | null>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const follow = useRef(true);

  useEffect(() => {
    if (follow.current && scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight;
  }, [messages]);
  useEffect(() => () => { current.current?.abort.abort(); current.current = null; }, []);

  const stop = () => {
    const request = current.current;
    if (!request) return;
    current.current = null;
    request.abort.abort();
    setMessages(items => items.map(item => item.id === request.assistantId ? { ...item, state: 'stopped' } : item));
    setRetryHistory(request.history);
    setBusy(false);
  };

  useEffect(() => {
    if (!enabled) stop();
  }, [enabled]);

  const generate = async (history: Message[]) => {
    if (current.current) return;
    if (!ready) { onConfigure(); return; }
    const assistantId = crypto.randomUUID();
    const request = { abort: new AbortController(), assistantId, history };
    current.current = request;
    setMessages([...history, { id: assistantId, role: 'assistant', content: '', state: 'streaming' }]);
    setBusy(true); setError(''); setRetryHistory(null); follow.current = true;
    const timer = setTimeout(() => request.abort.abort(new Error('回复超时，请重试。')), 185000);
    try {
      const context = history.filter(item => item.role === 'user' || item.state === 'complete').slice(-40);
      if (context[0]?.role === 'assistant') context.shift();
      await streamChat(context.map(({ role, content }) => ({ role, content })), request.abort.signal, text => {
        if (current.current !== request) return;
        setMessages(items => items.map(item => item.id === assistantId ? { ...item, content: item.content + text } : item));
      });
      if (current.current === request) {
        setMessages(items => items.map(item => item.id === assistantId ? { ...item, state: 'complete' } : item));
      }
    } catch (cause) {
      if (current.current === request) {
        setError(cause instanceof Error ? cause.message : '无法连接服务，请稍后重试。');
        setRetryHistory(history);
        setMessages(items => items.map(item => item.id === assistantId ? { ...item, state: 'error' } : item));
      }
    } finally {
      clearTimeout(timer);
      if (current.current === request) { current.current = null; setBusy(false); }
    }
  };

  const send = () => {
    if (!draft.trim() || current.current) return;
    if (!ready) { onConfigure(); return; }
    const message: Message = { id: crypto.randomUUID(), role: 'user', content: draft.trim() };
    setDraft('');
    void generate([...messages, message]);
  };

  const reset = () => {
    stop(); setMessages([]); setError(''); setRetryHistory(null); setDraft('');
    input.current?.focus();
  };

  return <section className="text-chat" aria-label="文字聊天">
    <div className="text-chat-header"><span><Sparkles size={17}/>与你的助手对话</span><button onClick={reset}><MessageSquarePlus size={16}/>新对话</button></div>
    <div className="chat-messages" ref={scroll} role="log" aria-label="聊天记录" aria-live="polite" onScroll={() => {
      if (scroll.current) follow.current = scroll.current.scrollHeight - scroll.current.scrollTop - scroll.current.clientHeight < 80;
    }}>
      {!messages.length ? <div className="chat-welcome"><span className="welcome-symbol"><Sparkles size={30}/></span><h2>今天，想聊点什么？</h2><p>整理一个想法，解答一个问题，或一起规划接下来的一天。</p><div className="chat-suggestions">{['帮我梳理一下今天的待办', '我有个想法，想和你聊聊', '帮我把复杂的问题讲简单'].map(text => <button key={text} onClick={() => { setDraft(text); input.current?.focus(); }}>{text}</button>)}</div></div> : messages.map(message => <article className={`chat-message ${message.role}`} key={message.id}>
        <div className="chat-message-author">{message.role === 'user' ? '你' : '轻声'}</div>
        <div className="chat-message-content">{message.content || (message.state === 'streaming' ? '正在思考…' : message.state === 'stopped' ? '已停止生成' : '未收到回复')}{message.state === 'streaming' && message.content && <span className="text-cursor" aria-hidden="true"/>}</div>
        {message.state === 'stopped' && message.content && <small>已停止生成</small>}
        {message.state === 'error' && message.content && <small>回复未完成</small>}
      </article>)}
    </div>
    <div className="chat-compose-area">
      {error && <div className="chat-error" role="alert">{error}</div>}
      {retryHistory && !busy && <button className="retry-button" onClick={() => { void generate(retryHistory); }}><RefreshCw size={13}/>重新生成</button>}
      {!ready && <div className="chat-setup"><span>配置对话模型后即可聊天，无需语音服务。</span><button onClick={onConfigure}><SlidersHorizontal size={13}/>配置模型</button></div>}
      <form className="chat-composer" onSubmit={event => { event.preventDefault(); send(); }}>
        <textarea ref={input} value={draft} onChange={event => setDraft(event.target.value)} maxLength={8000} rows={2} placeholder="输入你想说的话…" aria-label="聊天消息" onKeyDown={event => {
          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); send(); }
        }}/>
        {busy ? <button type="button" className="send-button stop-button" onClick={stop} aria-label="停止生成"><Square size={17}/></button> : <button type="submit" className="send-button" disabled={!draft.trim()} aria-label="发送消息"><ArrowUp size={21}/></button>}
      </form>
      <div className="composer-footnote"><span>Enter 发送 · Shift + Enter 换行</span><span>仅保留在本页，刷新后清空</span></div>
    </div>
  </section>;
}
