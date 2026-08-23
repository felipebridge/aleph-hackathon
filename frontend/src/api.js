// Thin wrapper over the FastAPI JSON endpoints. During dev, Vite proxies
// /api to the backend on :8080 (see vite.config.js); in prod the SPA is
// served from the same origin, so relative paths just work.

async function getJSON(url) {
  const res = await fetch(url)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || `Error ${res.status}`)
  return data
}

export async function getHealth() {
  return getJSON('/api/health')
}

export async function getMonths() {
  const data = await getJSON('/api/months')
  return data.months
}

export async function getOwnerDashboard() {
  // Dashboard del dueño sobre el dataset de movimientos de ZIRA (ingreso/egreso
  // detectado por el agente, ganancia auto-calculada).
  return getJSON('/api/zira/dashboard')
}

export async function getAccountantLedger() {
  return getJSON('/api/accountant/ledger')
}

export async function analyzeFile(file) {
  const body = new FormData()
  body.append('file', file)
  const res = await fetch('/api/analyze', { method: 'POST', body })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || 'No se pudo analizar el archivo.')
  return data
}

export async function reconcile({ source, receiptsDir, whatsappMonth, bankCsv }) {
  const body = new FormData()
  body.append('source', source)
  body.append('receipts_dir', receiptsDir)
  body.append('whatsapp_month', whatsappMonth)
  body.append('bank_csv', bankCsv)

  const res = await fetch('/api/reconcile', { method: 'POST', body })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || 'Error al reconciliar.')
  return data
}

export const money = (n) =>
  n == null ? '—' : n.toLocaleString('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 })

export const moneyFull = (n) =>
  n == null ? '—' : n.toLocaleString('es-AR', { style: 'currency', currency: 'ARS' })
