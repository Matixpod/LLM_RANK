import { useEffect, useState, useCallback } from 'react';
import { api } from './api.js';
import DomainSelector from './components/DomainSelector.jsx';
import DomainHeader from './components/DomainHeader.jsx';
import ScoreOverview from './components/ScoreOverview.jsx';
import TrendChart from './components/TrendChart.jsx';
import ContentGaps from './components/ContentGaps.jsx';
import QuestionManager from './components/QuestionManager.jsx';
import ScanButton from './components/ScanButton.jsx';
import ScanResults from './components/ScanResults.jsx';

export default function App() {
  const [domains, setDomains] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [history, setHistory] = useState([]);
  const [gaps, setGaps] = useState([]);
  const [latest, setLatest] = useState(null);

  const loadDomains = useCallback(async () => {
    const d = await api.listDomains();
    setDomains(d);
    if (!selectedId && d.length > 0) setSelectedId(d[0].id);
  }, [selectedId]);

  const loadDomainData = useCallback(async (id) => {
    if (!id) return;
    const [h, g, l] = await Promise.all([
      api.history(id),
      api.gaps(id),
      api.latestScan(id),
    ]);
    setHistory(h);
    setGaps(g);
    setLatest(l);
  }, []);

  useEffect(() => { loadDomains(); }, [loadDomains]);
  useEffect(() => { loadDomainData(selectedId); }, [selectedId, loadDomainData]);

  const selectedDomain = domains.find((d) => d.id === selectedId);

  return (
    <div className="min-h-screen font-mono text-terminal-text">
      <header className="border-b border-terminal-border px-6 py-3 flex items-center justify-between">
        <div className="flex items-baseline gap-3">
          <h1 className="text-accent font-bold tracking-wider">LLM-RANK</h1>
          <span className="text-terminal-muted text-xs uppercase">AI Visibility Tracker</span>
        </div>
        <div className="text-xs text-terminal-muted">
          {domains.length} domain{domains.length === 1 ? '' : 's'} tracked
        </div>
      </header>

      <main className="p-6 grid grid-cols-12 gap-4">
        <section className="col-span-12 lg:col-span-4 space-y-4">
          <DomainSelector
            domains={domains}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onCreated={async (d) => { await loadDomains(); setSelectedId(d.id); }}
          />
          {selectedDomain && (
            <ScanButton
              domain={selectedDomain}
              onDone={() => loadDomainData(selectedId)}
            />
          )}
        </section>

        <section className="col-span-12 lg:col-span-8 space-y-4">
          {selectedDomain && (
            <DomainHeader
              key={selectedDomain.id}
              domain={selectedDomain}
              onDeleted={async (deletedId) => {
                const d = await api.listDomains();
                setDomains(d);
                if (deletedId === selectedId) {
                  const next = d[0]?.id ?? null;
                  setSelectedId(next);
                  if (next == null) {
                    setHistory([]);
                    setGaps([]);
                    setLatest(null);
                  }
                }
              }}
            />
          )}
          <ScoreOverview latest={latest} />
          <TrendChart history={history} />
        </section>

        <section className="col-span-12 lg:col-span-6">
          <ContentGaps gaps={gaps} />
        </section>

        <section className="col-span-12 lg:col-span-6">
          {selectedDomain && (
            <QuestionManager
              domain={selectedDomain}
              onChange={() => loadDomainData(selectedId)}
            />
          )}
        </section>

        <section className="col-span-12">
          <ScanResults scanId={latest?.id ?? null} domain={selectedDomain} />
        </section>

        <section className="col-span-12">
          {selectedDomain && (
            <div className="flex justify-end">
              <a
                href={api.exportCsvUrl(selectedDomain.id)}
                className="px-4 py-2 border border-accent text-accent hover:bg-accent hover:text-terminal-bg transition-colors text-sm"
              >
                ⬇ Export CSV
              </a>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
