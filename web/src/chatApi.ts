export type RequestMessage = { role: 'user' | 'assistant'; content: string };

export async function streamChat(
  messages: RequestMessage[], signal: AbortSignal, onText: (text: string) => void,
) {
  const response = await fetch('/api/chat', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }), signal,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    throw new Error(typeof detail === 'string' ? detail
      : typeof detail?.message === 'string' ? detail.message
      : response.status === 422 ? '消息或上下文过长，请缩短内容或开始新对话。'
      : `请求失败（HTTP ${response.status}），请检查服务配置。`);
  }
  if (!response.body) throw new Error('浏览器无法读取流式回复。');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '', completed = false;
  const consume = (block: string) => {
    const lines = block.split(/\r?\n/);
    const name = lines.find(line => line.startsWith('event:'))?.slice(6).trim();
    const data = lines.filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
    if (!data) return;
    const payload = JSON.parse(data) as { text?: string; message?: string };
    if (name === 'delta' && typeof payload.text === 'string') onText(payload.text);
    if (name === 'error') throw new Error(payload.message || '生成回复失败。');
    if (name === 'done') completed = true;
  };
  try {
    while (!completed) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let boundary: RegExpExecArray | null;
      while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
        consume(buffer.slice(0, boundary.index));
        buffer = buffer.slice(boundary.index + boundary[0].length);
      }
      if (done) {
        if (buffer.trim()) consume(buffer);
        break;
      }
    }
    if (!completed) throw new Error('连接提前结束，回复可能不完整，请重试。');
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
