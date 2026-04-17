import { useState } from 'react';
import { api } from '../api.js';

export default function DomainHeader({ domain, onDeleted }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const remove = async () => {
    const msg =
      `Delete "${domain.domain}" and all its scans, questions, and results?\n\n` +
      `This cannot be undone.`;
    if (!window.confirm(msg)) return;
    setBusy(true); setErr('');
    try {
      await api.deleteDomain(domain.id);
      onDeleted?.(domain.id);
    } catch (e) {
      setErr(String(e.message || e));
      setBusy(false);
    }
  };

  return (
    <div className="border border-terminal-border bg-terminal-panel p-4 flex items-center justify-between gap-4">
      <div className="min-w-0">
        <div className="text-accent text-xs uppercase tracking-wider">Tracking</div>
        <div className="text-terminal-text font-bold truncate">{domain.domain}</div>
        <div className="text-terminal-muted text-xs">
          {domain.industry} · {domain.language || 'English'}
        </div>
      </div>
      <div className="flex flex-col items-end gap-1">
        <button
          type="button"
          onClick={remove}
          disabled={busy}
          className="border border-red-400 text-red-400 px-4 py-2 text-xs uppercase tracking-wider hover:bg-red-400 hover:text-terminal-bg disabled:opacity-50"
        >
          {busy ? 'deleting…' : '🗑 delete domain'}
        </button>
        {err && <div className="text-red-400 text-xs">{err}</div>}
      </div>
    </div>
  );
}
