type VoiceTextClient = {
  state: string;
  sendText: (content: string, options: { run_immediately: boolean; audio_response: boolean }) => Promise<void>;
};

export async function sendVoiceText(client: VoiceTextClient, draft: string): Promise<string> {
  if (client.state !== 'ready') throw new Error('请先建立语音通话，再发送文字。');
  const text = draft.trim();
  if (!text) throw new Error('消息不能为空。');
  if (text.length > 8000) throw new Error('消息不能超过 8000 字。');
  try {
    await client.sendText(text, { run_immediately: true, audio_response: true });
  } catch {
    throw new Error('文字发送失败，请检查通话连接后重试。');
  }
  return text;
}
