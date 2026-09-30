import { useMemo, useState } from 'react';
import { Button } from './ui';

function highlight(json: string) {
  return json.replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false)\b|\bnull\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g, (m) => {
      let cls = 'n';
      if (/^"/.test(m)) cls = /:$/.test(m) ? 'k' : 's';
      else if (/true|false/.test(m)) cls = 'b';
      else if (/null/.test(m)) cls = 'z';
      return `<span class="${cls}">${m}</span>`;
    });
}
export function JsonViewer({ data, maxChars = 200_000, filename = 'report.json' }: { data: unknown; maxChars?: number; filename?: string }) {
  const [compact, setCompact] = useState(true);
  const text = useMemo(() => {
    const replacer = compact ? (_k: string, v: unknown) => (Array.isArray(v) && v.length > 24 ? [...v.slice(0, 24), `… ${v.length - 24} more`] : v) : undefined;
    const s = JSON.stringify(data, replacer as any, 2) || '';
    return s.length > maxChars ? s.slice(0, maxChars) + '\n…' : s;
  }, [data, compact, maxChars]);
  const download = () => {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = filename; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };
  return (
    <div className="stack" style={{ ['--gap' as string]: '8px' }}>
      <div className="row"><Button size="sm" onClick={() => setCompact(!compact)}>{compact ? 'Show full arrays' : 'Compact arrays'}</Button><Button size="sm" onClick={download}>Download JSON</Button></div>
      <pre className="json" dangerouslySetInnerHTML={{ __html: highlight(text) }} />
    </div>
  );
}
