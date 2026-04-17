import { useState } from 'react';
import { api } from '../api.js';

const LANGUAGES = [
  'English',
  'Polish',
  'German',
  'French',
  'Spanish',
  'Italian',
  'Portuguese',
  'Dutch',
  'Czech',
  'Ukrainian',
  'Russian',
  'Japanese',
  'Chinese',
];

export default function DomainSelector({ domains, selectedId, onSelect, onCreated }) {
  const [domain, setDomain] = useState('');
  const [industry, setIndustry] = useState('');
  const [language, setLanguage] = useState('English');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    if (!domain.trim() || !industry.trim()) return;
    setBusy(true); setErr('');
    try {
      const d = await api.createDomain(domain.trim(), industry.trim(), language);
      setDomain(''); setIndustry('');
      onCreated(d);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border border-terminal-border bg-terminal-panel p-4">
      <h2 className="text-accent text-xs uppercase tracking-wider mb-3">Domains</h2>
      <select
        value={selectedId || ''}
        onChange={(e) => onSelect(Number(e.target.value))}
        className="w-full bg-terminal-bg border border-terminal-border px-3 py-2 text-sm text-terminal-text mb-4"
      >
        {domains.length === 0 && <option value="">— none —</option>}
        {domains.map((d) => (
          <option key={d.id} value={d.id}>
            {d.domain} · {d.industry}{d.language ? ` · ${d.language}` : ''}
          </option>
        ))}
      </select>

      <form onSubmit={submit} className="space-y-2">
        <input
          placeholder="domain (e.g. example.com)"
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          className="w-full bg-terminal-bg border border-terminal-border px-3 py-2 text-sm"
        />
        <input
          placeholder="industry (e.g. SEO tooling)"
          value={industry}
          onChange={(e) => setIndustry(e.target.value)}
          className="w-full bg-terminal-bg border border-terminal-border px-3 py-2 text-sm"
        />
        <label className="block text-[10px] uppercase tracking-wider text-terminal-muted pt-1">
          question language
        </label>
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          className="w-full bg-terminal-bg border border-terminal-border px-3 py-2 text-sm text-terminal-text"
        >
          {LANGUAGES.map((l) => (
            <option key={l} value={l}>{l}</option>
          ))}
        </select>
        <button
          disabled={busy}
          className="w-full border border-accent text-accent px-3 py-2 text-sm hover:bg-accent hover:text-terminal-bg disabled:opacity-50"
        >
          {busy ? '…' : '+ add domain'}
        </button>
        {err && <div className="text-red-400 text-xs">{err}</div>}
      </form>
    </div>
  );
}
