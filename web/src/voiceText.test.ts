import { describe, expect, it } from 'vitest';
import { sendVoiceText } from './voiceText';

describe('text inside a voice session', () => {
  it('sends a new turn over the active call with interruption and audio enabled', async () => {
    const sent: unknown[] = [];
    const client = { state: 'ready', sendText: async (...args: unknown[]) => { sent.push(args); } };
    expect(await sendVoiceText(client, '  接着刚才说的  ')).toBe('接着刚才说的');
    expect(sent).toEqual([['接着刚才说的', { run_immediately: true, audio_response: true }]]);
  });

  it('does not send on a disconnected call or accept blank input', async () => {
    const client = { state: 'disconnected', sendText: async () => { throw new Error('should not send'); } };
    await expect(sendVoiceText(client, '你好')).rejects.toThrow('通话');
    client.state = 'ready';
    await expect(sendVoiceText(client, '   ')).rejects.toThrow('为空');
  });

  it('reports transport failure so the composer can preserve its draft', async () => {
    const client = { state: 'ready', sendText: async () => { throw new Error('closed'); } };
    await expect(sendVoiceText(client, '你好')).rejects.toThrow('发送失败');
  });
});
