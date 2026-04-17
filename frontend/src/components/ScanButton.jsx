import { useEffect, useRef, useState } from 'react';
import { api } from '../api.js';

export default function ScanButton({ domain, onDone }) {
  const [scanId, setScanId] = useState(null);
  const [status, setStatus] = useState(null);
  const pollRef = useRef(null);

  useEffect(() => () => clearInterval(pollRef.current), []);

  const trigger = async () => {
    const r = await api.triggerScan(domain.id);
    setScanId(r.scan_id);
    setStatus({ status: r.status, progress: 0, total: 0 });

    clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.scanStatus(r.scan_id);
        setStatus(s);
        if (s.status === 'complete' || s.status === 'error') {
          clearInterval(pollRef.current);
          onDone?.();
        }
      } catch (_) {
        // transient poll failure — keep trying
      }
    }, 1500);
  };

  const running = status && status.status !== 'complete' && status.status !== 'error';
  const pct = status?.total
    ? Math.min(100, Math.round((status.progress / status.total) * 100))
    : 0;

  return (
    <div className="border border-terminal-border bg-terminal-panel p-4">
      <h2 className="text-accent text-xs uppercase tracking-wider mb-3">Run Scan</h2>
      <button
        onClick={trigger}
        disabled={running}
        className="w-full border border-accent text-accent px-3 py-2 text-sm hover:bg-accent hover:text-terminal-bg disabled:opacity-50"
      >
        {running ? `scanning · ${pct}%` : '▶ scan now'}
      </button>
      {status && (
        <div className="mt-3 text-xs text-terminal-muted">
          status: {status.status}
          {status.total > 0 && ` · ${status.progress}/${status.total}`}
          {status.score != null && ` · score ${status.score.toFixed(1)}`}
        </div>
      )}
      {running && (
        <div className="mt-2 h-1 w-full bg-terminal-bg border border-terminal-border">
          <div className="h-full bg-accent transition-all" style={{ width: `${pct}%` }} />
        </div>
      )}
    </div>
  );
}
