import { useEffect, useMemo, useState } from 'react';
import { api } from '../api.js';

const POINTS = { cited: 3, mentioned: 1, not_present: 0, error: 0 };

const STATUS_STYLES = {
  cited: 'text-accent border-accent',
  mentioned: 'text-yellow-400 border-yellow-400',
  not_present: 'text-terminal-muted border-terminal-border',
  error: 'text-red-400 border-red-400',
};

const SECTION_CFG = {
  cited: {
    label: 'Fully Cited',
    accent: 'text-accent',
    border: 'border-accent/30',
    desc: 'Domain confirmed as a grounded source',
  },
  partial: {
    label: 'Partially Mentioned',
    accent: 'text-yellow-400',
    border: 'border-yellow-400/30',
    desc: 'Mentioned in text or cited by some models',
  },
  absent: {
    label: 'Not Cited',
    accent: 'text-terminal-muted',
    border: 'border-terminal-border',
    desc: 'Domain not found in any model output',
  },
};

function getDomainBase(domain) {
  if (!domain) return '';
  const d = domain.replace(/^(https?:\/\/)?(www\.)?/i, '').split('/')[0];
  return d.split('.')[0].toLowerCase();
}

function nameInText(responseText, domainBase) {
  if (!responseText || !domainBase) return false;
  return responseText.toLowerCase().includes(domainBase);
}

function Indicator({ ok, label }) {
  return (
    <span className={`text-[10px] px-1.5 py-0.5 border rounded-sm ${ok ? 'text-accent border-accent/50' : 'text-terminal-muted border-terminal-border'}`}>
      {ok ? '\u2713' : '\u2717'} {label}
    </span>
  );
}

function QuestionCard({ group, domainBase, openId, setOpenId }) {
  const isOpen = openId === group.question_id;
  return (
    <li className="border border-terminal-border/60">
      <button
        type="button"
        onClick={() => setOpenId(isOpen ? null : group.question_id)}
        className="w-full text-left px-3 py-2 text-sm flex items-start gap-2 hover:bg-terminal-bg/50"
      >
        <span className="text-terminal-muted text-xs mt-0.5">
          {isOpen ? '\u25BE' : '\u25B8'}
        </span>
        <span className="flex-1">{group.text}</span>
        <span className="flex gap-1">
          {group.entries.map((e) => (
            <span
              key={e.id}
              className={`text-[10px] uppercase px-1.5 py-0.5 border ${STATUS_STYLES[e.visibility_status] || STATUS_STYLES.not_present}`}
              title={`${e.model}: ${e.visibility_status}`}
            >
              {e.model[0]}:{e.visibility_status === 'not_present' ? '\u2014' : e.visibility_status === 'cited' ? 'C' : 'M'}
            </span>
          ))}
        </span>
      </button>

      {isOpen && (
        <div className="border-t border-terminal-border/60 divide-y divide-terminal-border/40">
          {group.entries.map((e) => {
            const hasName = nameInText(e.response_text, domainBase);
            const hasLink = e.visibility_status === 'cited';
            return (
              <div key={e.id} className="px-3 py-3 text-xs">
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  <span className="text-accent uppercase tracking-wider font-bold">{e.model}</span>
                  <span
                    className={`text-[10px] uppercase px-1.5 py-0.5 border ${STATUS_STYLES[e.visibility_status] || STATUS_STYLES.not_present}`}
                  >
                    {e.visibility_status}
                  </span>
                  <Indicator ok={hasName} label="Name in text" />
                  <Indicator ok={hasLink} label="Link to site" />
                </div>
                {e.response_text ? (
                  <pre className="whitespace-pre-wrap font-mono text-terminal-text leading-relaxed max-h-64 overflow-y-auto">
                    {e.response_text}
                  </pre>
                ) : (
                  <div className="text-terminal-muted italic">no response text</div>
                )}
                {e.cited_urls?.length > 0 && (
                  <div className="mt-3">
                    <div className="text-[10px] uppercase text-terminal-muted mb-1">cited sources</div>
                    <ul className="space-y-0.5">
                      {e.cited_urls.map((u, i) => (
                        <li key={i}>
                          <a href={u} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline break-all">
                            {u}
                          </a>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </li>
  );
}

function Section({ cfg, questions, domainBase, openId, setOpenId }) {
  const [collapsed, setCollapsed] = useState(false);
  if (questions.length === 0) return null;
  return (
    <div className={`border ${cfg.border} bg-terminal-panel`}>
      <button
        type="button"
        onClick={() => setCollapsed(!collapsed)}
        className="w-full text-left px-4 py-2 flex items-center gap-2"
      >
        <span className="text-terminal-muted text-xs">{collapsed ? '\u25B8' : '\u25BE'}</span>
        <span className={`text-xs uppercase tracking-wider font-bold ${cfg.accent}`}>
          {cfg.label}
        </span>
        <span className="text-terminal-muted text-xs">
          ({questions.length} question{questions.length === 1 ? '' : 's'})
        </span>
        <span className="text-terminal-muted text-[10px] ml-auto">{cfg.desc}</span>
      </button>
      {!collapsed && (
        <ul className="px-3 pb-3 space-y-2">
          {questions.map((g) => (
            <QuestionCard key={g.question_id} group={g} domainBase={domainBase} openId={openId} setOpenId={setOpenId} />
          ))}
        </ul>
      )}
    </div>
  );
}

export default function ScanResults({ scanId, domain }) {
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const [openId, setOpenId] = useState(null);

  useEffect(() => {
    if (!scanId) { setResults([]); return; }
    let cancelled = false;
    setLoading(true); setErr('');
    api.scanResults(scanId)
      .then((r) => { if (!cancelled) setResults(r); })
      .catch((e) => { if (!cancelled) setErr(String(e.message || e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [scanId]);

  const domainBase = useMemo(() => getDomainBase(domain?.domain), [domain]);

  const { grouped, sections, scorePoints, scoreMax } = useMemo(() => {
    const by = new Map();
    let pts = 0;
    for (const r of results) {
      if (!by.has(r.question_id)) {
        by.set(r.question_id, { question_id: r.question_id, text: r.question_text, entries: [] });
      }
      by.get(r.question_id).entries.push(r);
      pts += POINTS[r.visibility_status] ?? 0;
    }
    const all = Array.from(by.values());
    const maxPts = results.length * 3;

    const cited = [];
    const partial = [];
    const absent = [];
    for (const g of all) {
      const statuses = g.entries.map((e) => e.visibility_status);
      if (statuses.every((s) => s === 'cited')) {
        cited.push(g);
      } else if (statuses.every((s) => s === 'not_present' || s === 'error')) {
        absent.push(g);
      } else {
        partial.push(g);
      }
    }
    return {
      grouped: all,
      sections: { cited, partial, absent },
      scorePoints: pts,
      scoreMax: maxPts,
    };
  }, [results]);

  if (!scanId) {
    return (
      <div className="border border-terminal-border bg-terminal-panel p-4 text-xs text-terminal-muted">
        Run a scan to see model responses here.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="border border-terminal-border bg-terminal-panel p-4">
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-accent text-xs uppercase tracking-wider">
            Model Responses{' '}
            <span className="text-terminal-muted">
              (scan #{scanId} · {grouped.length} question{grouped.length === 1 ? '' : 's'})
            </span>
          </h2>
          {scoreMax > 0 && (
            <div className="text-sm font-bold">
              <span className="text-accent">{scorePoints}</span>
              <span className="text-terminal-muted"> / {scoreMax} pts</span>
              <span className="text-terminal-muted text-xs ml-2">
                ({scoreMax > 0 ? ((scorePoints / scoreMax) * 100).toFixed(1) : 0}%)
              </span>
            </div>
          )}
        </div>
        <div className="flex gap-4 text-[10px] text-terminal-muted">
          <span>cited = 3pts</span>
          <span>mentioned = 1pt</span>
          <span>not present = 0pts</span>
        </div>
      </div>

      {loading && <div className="text-xs text-terminal-muted">loading…</div>}
      {err && <div className="text-red-400 text-xs">{err}</div>}

      <Section cfg={SECTION_CFG.cited} questions={sections.cited} domainBase={domainBase} openId={openId} setOpenId={setOpenId} />
      <Section cfg={SECTION_CFG.partial} questions={sections.partial} domainBase={domainBase} openId={openId} setOpenId={setOpenId} />
      <Section cfg={SECTION_CFG.absent} questions={sections.absent} domainBase={domainBase} openId={openId} setOpenId={setOpenId} />
    </div>
  );
}
