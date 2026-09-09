import { useRef, useState } from 'react';
import { ArrowUp, LoaderCircle } from 'lucide-react';

export default function VoiceComposer({ active, onSend }: {
  active: boolean;
  onSend: (text: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState('');
  const [error, setError] = useState('');
  const [sending, setSending] = useState(false);
  const inFlight = useRef(false);
  const send = async () => {
    if (!active || inFlight.current || !draft.trim()) return;
    inFlight.current = true;
    setSending(true); setError('');
    const submitted = draft;
    try {
      await onSend(submitted);
      setDraft(current => current === submitted ? '' : current);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '发送失败，请重试。');
    } finally {
      inFlight.current = false; setSending(false);
    }
  };
  return <div className="chat-compose-area voice-compose-area">
    {error && <div className="chat-error" role="alert">{error}</div>}
    <form className="chat-composer" onSubmit={event => { event.preventDefault(); void send(); }}>
      <textarea aria-label="通话文字消息" placeholder={active ? '也可以打字，接着刚才的话聊…' : '开始通话后，可以说话或打字…'}
        value={draft} onChange={event => setDraft(event.target.value)} maxLength={8000} rows={2}
        disabled={!active} onKeyDown={event => {
          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault(); void send();
          }
        }}/>
      <button type="submit" className="send-button" aria-label="发送通话文字" disabled={!active || sending || !draft.trim()}>
        {sending ? <LoaderCircle className="spin" size={18}/> : <ArrowUp size={20}/>}
      </button>
    </form>
    <div className="composer-footnote"><span>{active ? '说话和打字共享本次对话 · 静音时也能打字' : '通话结束后会释放连接'}</span></div>
  </div>;
}
