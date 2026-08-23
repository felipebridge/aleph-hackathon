import { useState, useEffect, useCallback } from 'react'
import { getAccountantLedger, money } from '../../api.js'
import { IconAlert } from '../icons.jsx'
import { useT } from '../../i18n.jsx'
import UploadCard from './UploadCard.jsx'
import { ProviderLedger, ClientLedger } from './LedgerTables.jsx'

function MiniStat({ label, value, accent }) {
  return (
    <div className="card p-4">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1.5 text-xl font-extrabold ${accent}`}>{value}</div>
    </div>
  )
}

export default function AccountantDashboard() {
  const { t, alert: alertText } = useT()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [expandedProvider, setExpandedProvider] = useState(null)
  const [expandedClient, setExpandedClient] = useState(null)
  const [highlightId, setHighlightId] = useState(null)

  const load = useCallback(() => {
    getAccountantLedger().then(setData).catch((e) => setError(e.message))
  }, [])

  useEffect(() => { load() }, [load])

  // Al hacer click en una alerta: expandir la parte que contiene esa factura,
  // resaltarla y hacer scroll hasta ella.
  const goToInvoice = (inv) => {
    const isIngreso = inv.direction === 'ingreso'
    const parties = isIngreso ? data.clients : data.providers
    const party = parties.find((p) => p.invoices.some((i) => i.id === inv.id))
    if (!party) return
    if (isIngreso) { setExpandedClient(party.id); setExpandedProvider(null) }
    else { setExpandedProvider(party.id); setExpandedClient(null) }
    setHighlightId(inv.id)
    setTimeout(() => {
      document.getElementById(`inv-${inv.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 80)
  }

  if (error) return <div className="card p-6 text-sm text-rose-400">Error: {error}</div>
  if (!data) {
    return (
      <div className="flex h-64 items-center justify-center">
        <span className="h-8 w-8 animate-spin rounded-full border-2 border-stroke border-t-brand-glow" />
      </div>
    )
  }

  const { providers, clients, alerts, totals } = data
  const totalCobrado = clients.reduce((s, c) => s + c.total, 0)
  const totalPagado = providers.reduce((s, p) => s + p.total, 0)

  return (
    <div className="space-y-6">
      {/* Fila superior: carga + stats */}
      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <UploadCard onAnalyzed={load} />
        <div className="grid grid-cols-2 gap-4 content-start">
          <MiniStat label={t('stats.invoices')} value={totals.invoices} accent="text-white" />
          <MiniStat label={t('stats.alerts')} value={totals.alerts} accent="text-amber-400" />
          <MiniStat label={t('stats.suppliers')} value={totals.providers} accent="text-white" />
          <MiniStat label={t('stats.clients')} value={totals.clients} accent="text-white" />
          <div className="card p-4">
            <div className="text-xs uppercase tracking-wide text-slate-500">{t('stats.collected')}</div>
            <div className="mt-1.5 text-lg font-extrabold text-emerald-400">{money(totalCobrado)}</div>
          </div>
          <div className="card p-4">
            <div className="text-xs uppercase tracking-wide text-slate-500">{t('stats.paid')}</div>
            <div className="mt-1.5 text-lg font-extrabold text-rose-400">{money(totalPagado)}</div>
          </div>
        </div>
      </div>

      {/* Alertas -> click lleva a la factura */}
      {alerts.length > 0 && (
        <div className="card border-amber-500/25 p-5">
          <div className="mb-3 flex items-center gap-2">
            <IconAlert className="h-5 w-5 text-amber-400" />
            <h2 className="text-base font-bold text-white">{t('alerts.title')} ({alerts.length})</h2>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {alerts.map((a) => (
              <button
                key={a.id}
                onClick={() => goToInvoice(a)}
                className="flex items-start justify-between gap-3 rounded-lg bg-panel2 px-4 py-3 text-left transition hover:bg-panel2/70 hover:ring-1 hover:ring-amber-500/30"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-slate-200">{a.counterparty}</span>
                    <span className="font-mono text-[11px] text-slate-500">{a.id}</span>
                  </div>
                  <div className="mt-0.5 text-xs text-amber-300/90">{alertText(a.alert_type, a.alert_params)}</div>
                </div>
                <span className="shrink-0 text-xs font-semibold text-brand-glow">{t('alerts.view')}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Libro mayor */}
      <ProviderLedger
        providers={providers} expandedId={expandedProvider}
        onToggle={(id) => setExpandedProvider(expandedProvider === id ? null : id)}
        highlightId={highlightId}
      />
      <ClientLedger
        clients={clients} expandedId={expandedClient}
        onToggle={(id) => setExpandedClient(expandedClient === id ? null : id)}
        highlightId={highlightId}
      />
    </div>
  )
}
