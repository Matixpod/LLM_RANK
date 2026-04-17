const BASE = '/api';

async function req(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok && res.status !== 204) {
    const text = await res.text().catch(() => '');
    throw new Error(`${res.status} ${text}`);
  }
  if (res.status === 204) return null;
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res.text();
}

export const api = {
  listDomains: () => req('/domains'),
  createDomain: (domain, industry, language = 'English') =>
    req('/domains', {
      method: 'POST',
      body: JSON.stringify({ domain, industry, language }),
    }),
  deleteDomain: (domainId) => req(`/domains/${domainId}`, { method: 'DELETE' }),
  triggerScan: (domainId) => req(`/scan/${domainId}`, { method: 'POST' }),
  scanStatus: (scanId) => req(`/scan/${scanId}/status`),
  latestScan: (domainId) => req(`/domains/${domainId}/scans/latest`),
  scanResults: (scanId) => req(`/scans/${scanId}/results`),
  history: (domainId) => req(`/domains/${domainId}/history`),
  gaps: (domainId) => req(`/domains/${domainId}/gaps`),
  listQuestions: (domainId) => req(`/questions/${domainId}`),
  addQuestion: (domainId, text) =>
    req(`/questions/${domainId}`, { method: 'POST', body: JSON.stringify({ text }) }),
  generateMoreQuestions: (domainId, count = 10) =>
    req(`/questions/${domainId}/generate?count=${count}`, { method: 'POST' }),
  deleteQuestion: (qid) => req(`/questions/${qid}`, { method: 'DELETE' }),
  exportCsvUrl: (domainId) => `${BASE}/export/${domainId}/csv`,
};
