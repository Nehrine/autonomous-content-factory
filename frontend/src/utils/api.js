const BASE = import.meta.env.VITE_API_URL + '/api';

export async function fetchConfig() {
  try { return await (await fetch(`${BASE}/config`)).json() } catch { return {} }
}

export async function uploadFile(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/upload`, { method: 'POST', body: form })
  if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail || `Upload failed`) }
  return res.json()
}

export async function runPipeline(payload) {
  const res = await fetch(`${BASE}/run-pipeline`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail || `Pipeline failed`) }
  return res.json()
}

export async function regenerateContent(payload) {
  const res = await fetch(`${BASE}/regenerate-json`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail || `Regeneration failed`) }
  return res.json()
}

export async function exportCampaign(factSheet, content) {
  const res = await fetch(`${BASE}/export`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fact_sheet: factSheet, content }),
  })
  if (!res.ok) throw new Error('Export failed')
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = 'campaign_kit.zip'; a.click()
  URL.revokeObjectURL(url)
}
