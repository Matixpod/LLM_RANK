import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';

export default function TrendChart({ history }) {
  const data = (history || []).map((s) => ({
    date: new Date(s.started_at).toLocaleDateString(),
    overall: s.score,
    perplexity: s.perplexity_score,
    gemini: s.gemini_score,
  }));

  return (
    <div className="border border-terminal-border bg-terminal-panel p-4">
      <h2 className="text-accent text-xs uppercase tracking-wider mb-3">Score History</h2>
      {data.length === 0 ? (
        <div className="text-terminal-muted text-sm py-12 text-center">
          no scans yet — trigger one to populate the timeline
        </div>
      ) : (
        <div style={{ width: '100%', height: 240 }}>
          <ResponsiveContainer>
            <LineChart data={data}>
              <CartesianGrid stroke="#1e2a31" strokeDasharray="3 3" />
              <XAxis dataKey="date" stroke="#6b7b82" fontSize={11} />
              <YAxis stroke="#6b7b82" fontSize={11} domain={[0, 100]} />
              <Tooltip
                contentStyle={{ background: '#11161a', border: '1px solid #1e2a31', fontSize: 12 }}
                labelStyle={{ color: '#c6d4d9' }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line type="monotone" dataKey="overall" stroke="#00FF88" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="perplexity" stroke="#4ea8ff" strokeWidth={1.5} dot={{ r: 2 }} />
              <Line type="monotone" dataKey="gemini" stroke="#ff8c4a" strokeWidth={1.5} dot={{ r: 2 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
