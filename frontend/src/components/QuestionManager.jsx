import { useEffect, useState } from 'react';
import { api } from '../api.js';

export default function QuestionManager({ domain, onChange }) {
  const [questions, setQuestions] = useState([]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [err, setErr] = useState('');

  const load = async () => {
    const q = await api.listQuestions(domain.id);
    setQuestions(q);
  };

  useEffect(() => { load(); }, [domain.id]);

  const add = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    try {
      await api.addQuestion(domain.id, text.trim());
      setText('');
      await load();
      onChange?.();
    } finally { setBusy(false); }
  };

  const generate = async () => {
    setGenerating(true); setErr('');
    try {
      await api.generateMoreQuestions(domain.id, 10);
      await load();
      onChange?.();
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setGenerating(false);
    }
  };

  const del = async (id) => {
    await api.deleteQuestion(id);
    await load();
    onChange?.();
  };

  return (
    <div className="border border-terminal-border bg-terminal-panel p-4 h-full">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-accent text-xs uppercase tracking-wider">
          Questions <span className="text-terminal-muted">({questions.length})</span>
        </h2>
        <button
          type="button"
          onClick={generate}
          disabled={generating}
          title="Generate 10 more questions via LLM"
          className="border border-accent text-accent px-3 py-1 text-xs uppercase tracking-wider hover:bg-accent hover:text-terminal-bg disabled:opacity-50"
        >
          {generating ? 'generating…' : '✨ generate 10 more'}
        </button>
      </div>
      {err && <div className="text-red-400 text-xs mb-2">{err}</div>}

      <form onSubmit={add} className="flex gap-2 mb-3">
        <input
          placeholder="add a question…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          className="flex-1 bg-terminal-bg border border-terminal-border px-2 py-1 text-sm"
        />
        <button
          disabled={busy}
          className="border border-accent text-accent px-3 text-sm hover:bg-accent hover:text-terminal-bg disabled:opacity-50"
        >
          +
        </button>
      </form>

      <ul className="space-y-1 text-sm max-h-80 overflow-y-auto">
        {questions.map((q) => (
          <li key={q.id} className="flex gap-2 items-start py-1 border-b border-terminal-border/40">
            <span className="flex-1">{q.text}</span>
            <button
              onClick={() => del(q.id)}
              className="text-terminal-muted hover:text-red-400 text-xs"
              title="delete"
            >
              ×
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
