export default function ContentGaps({ gaps }) {
  return (
    <div className="border border-terminal-border bg-terminal-panel p-4 h-full">
      <h2 className="text-accent text-xs uppercase tracking-wider mb-3">
        Content Gaps <span className="text-terminal-muted">(not_present in last scan)</span>
      </h2>
      {(!gaps || gaps.length === 0) ? (
        <div className="text-terminal-muted text-sm py-6 text-center">no gaps recorded</div>
      ) : (
        <ul className="space-y-2 text-sm max-h-80 overflow-y-auto">
          {gaps.map((g) => (
            <li key={g.question_id} className="flex gap-2 items-start py-2 border-b border-terminal-border/40">
              <span className="text-accent text-xs px-2 py-0.5 border border-accent whitespace-nowrap">
                {g.models_missing.length}/2
              </span>
              <span className="flex-1">{g.text}</span>
              <span className="text-terminal-muted text-xs">
                {g.models_missing.join(', ')}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
