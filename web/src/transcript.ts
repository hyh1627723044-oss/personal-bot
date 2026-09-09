export function transcriptText(value: unknown): string {
  if (typeof value === 'string') return value;
  if (value && typeof value === 'object' && 'spoken' in value && 'unspoken' in value) {
    return [value.spoken, value.unspoken].filter(part => typeof part === 'string').join('');
  }
  return '';
}
