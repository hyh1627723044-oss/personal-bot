import { describe, expect, it } from 'vitest';
import { transcriptText } from './transcript';

describe('transcriptText', () => {
  it('handles optional parts without crashing the whole call screen', () => {
    expect(transcriptText(undefined)).toBe('');
    expect(transcriptText(null)).toBe('');
    expect(transcriptText({})).toBe('');
  });
  it('renders both plain user text and structured assistant output', () => {
    expect(transcriptText('你好')).toBe('你好');
    expect(transcriptText({ spoken: '你好，', unspoken: '有什么可以帮你？' })).toBe('你好，有什么可以帮你？');
  });
});
