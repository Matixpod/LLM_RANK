function Metric({ label, value, tone, suffix }) {
  const color = tone === 'accent' ? 'text-accent' : 'text-terminal-text';
  return (
    <div className="flex-1 px-4 py-3 border border-terminal-border bg-terminal-bg">
      <div className="text-xs uppercase tracking-wider text-terminal-muted">{label}</div>
      <div className={`font-mono ${color} ${tone === 'accent' ? 'text-5xl' : 'text-2xl'} font-bold`}>
        {value != null ? value.toFixed(1) : '\u2014'}
      </div>
      {suffix && <div className="text-xs text-terminal-muted mt-1">{suffix}</div>}
    </div>
  );
}

export default function ScoreOverview({ latest }) {
  const score = latest?.score ?? null;
  const qCount = latest?.questions_count ?? 0;

  const pxEnabled = latest?.perplexity_score != null;
  const gmEnabled = latest?.gemini_score != null;
  const modelCount = (pxEnabled ? 1 : 0) + (gmEnabled ? 1 : 0);
  const maxPts = qCount * modelCount * 3;
  const pts = maxPts > 0 && score != null ? Math.round((score / 100) * maxPts) : null;

  const ptsLabel = pts != null ? `${pts} / ${maxPts} pts` : null;

  return (
    <div className="border border-terminal-border bg-terminal-panel p-4">
      <h2 className="text-accent text-xs uppercase tracking-wider mb-3">LLM Visibility Score</h2>
      <div className="flex gap-3">
        <Metric label="Overall" value={score} tone="accent" suffix={ptsLabel} />
        <Metric label="Perplexity" value={latest?.perplexity_score} />
        <Metric label="Gemini" value={latest?.gemini_score} />
      </div>
      {latest?.started_at && (
        <div className="text-xs text-terminal-muted mt-3">
          last scan {new Date(latest.started_at).toLocaleString()} · status {latest.status}
        </div>
      )}
    </div>
  );
}
