import { afterEach, describe, expect, it, vi } from 'vitest';
import { streamChat } from './chatApi';

afterEach(() => vi.unstubAllGlobals());

function streamResponse(text: string) {
  const bytes = new TextEncoder().encode(text);
  return new Response(new ReadableStream({
    start(controller) {
      // One byte at a time splits both SSE delimiters and Chinese UTF-8 characters.
      for (let i = 0; i < bytes.length; i++) controller.enqueue(bytes.slice(i, i + 1));
      controller.close();
    },
  }));
}

describe('chat stream boundary', () => {
  it('preserves Chinese text across byte chunks and CRLF events', async () => {
    vi.stubGlobal('fetch', async () => streamResponse('event: delta\r\ndata: {"text":"你好"}\r\n\r\nevent: done\r\ndata: {}\r\n\r\n'));
    const output: string[] = [];
    await streamChat([{ role: 'user', content: '你好' }], new AbortController().signal, text => output.push(text));
    expect(output.join('')).toBe('你好');
  });
  it('reports server errors rather than accepting an incomplete answer', async () => {
    vi.stubGlobal('fetch', async () => streamResponse('event: error\ndata: {"message":"鉴权失败"}\n\n'));
    await expect(streamChat([], new AbortController().signal, () => {})).rejects.toThrow('鉴权失败');
  });
  it('rejects an unexpected end without done', async () => {
    vi.stubGlobal('fetch', async () => streamResponse('event: delta\ndata: {"text":"半句"}\n\n'));
    await expect(streamChat([], new AbortController().signal, () => {})).rejects.toThrow('连接提前结束');
  });
  it('surfaces missing configuration from HTTP 503', async () => {
    vi.stubGlobal('fetch', async () => Response.json({ detail: { message: '请配置模型' } }, { status: 503 }));
    await expect(streamChat([], new AbortController().signal, () => {})).rejects.toThrow('请配置模型');
  });
});
