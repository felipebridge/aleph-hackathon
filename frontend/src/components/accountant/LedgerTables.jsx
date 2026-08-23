import { money } from '../../api.js'
import { useT } from '../../i18n.jsx'

function InvoiceRows({ invoices, highlightId, t, cat }) {
  return (
    <div className="bg-bg/40">
      {invoices.map((inv) => (
        <div
          key={inv.id}
          id={`inv-${inv.id}`}
          className={`flex items-center justify-between border-t border-stroke/40 px-5 py-2.5 pl-12 text-sm transition ${
            highlightId === inv.id ? 'bg-amber-500/10 ring-1 ring-amber-500/30' : ''
          }`}
        >
          <div className="flex items-center gap-3">
            <span className="font-mono text-[11px] text-slate-500">{inv.id}</span>
            <span className="text-slate-300">{inv.concept}</span>
            {inv.source === 'upload' && (
              <span className="rounded-full bg-brand/15 px-2 py-0.5 text-[10px] font-semibold text-brand-glow">
                {t('ledger.uploaded')}
              </span>
            )}
            {inv.status === 'alerta' && (
              <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold text-amber-400">
                {t('ledger.alert')}
              </span>
            )}
          </div>
          <div className="flex items-center gap-4">
            <span className="inline-flex items-center gap-1.5 text-xs text-slate-400">
              <span className="h-2 w-2 rounded-sm" style={{ background: inv.category_color }} />
              {cat(inv.category_key, inv.category)}
            </span>
            <span className="text-xs text-slate-500">{inv.date || '—'}</span>
            <span className="w-24 text-right font-semibold tabular-nums text-slate-200">
              {money(inv.amount)}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}

function PartyTable({ title, subtitle, parties, accent, expandedId, onToggle, highlightId, t, cat }) {
  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between border-b border-stroke px-5 py-4">
        <div>
          <h2 className="text-base font-bold text-white">{title}</h2>
          <p className="text-xs text-slate-500">{subtitle}</p>
        </div>
        <span className="rounded-full bg-panel2 px-2.5 py-0.5 text-xs font-semibold text-slate-400">
          {parties.length}
        </span>
      </div>
      <div>
        <div className="grid grid-cols-[1fr_auto] items-center border-b border-stroke px-5 py-2.5 text-[11px] uppercase tracking-wide text-slate-500 sm:grid-cols-[auto_1fr_auto_auto_auto] sm:gap-4">
          <span>{t('ledger.idName')}</span>
          <span className="hidden sm:block">{t('ledger.mainCategory')}</span>
          <span className="hidden text-right sm:block">{t('ledger.invoices')}</span>
          <span className="hidden text-right sm:block">{t('ledger.alerts')}</span>
          <span className="text-right">{t('ledger.total')}</span>
        </div>
        {parties.map((p) => {
          const open = expandedId === p.id
          return (
            <div key={p.id} className="border-b border-stroke/60 last:border-0">
              <button
                onClick={() => onToggle(p.id)}
                className="grid w-full grid-cols-[1fr_auto] items-center gap-2 px-5 py-3 text-left transition hover:bg-panel2/40 sm:grid-cols-[auto_1fr_auto_auto_auto] sm:gap-4"
              >
                <div className="flex items-center gap-3">
                  <span className={`flex h-5 w-5 items-center justify-center rounded text-[10px] text-slate-400 transition ${open ? 'rotate-90' : ''}`}>▶</span>
                  <div>
                    <div className="font-medium text-slate-200">{p.name}</div>
                    <div className="font-mono text-[11px] text-slate-500">{p.id}</div>
                  </div>
                </div>
                <span className="hidden text-xs text-slate-400 sm:block">{cat(p.top_category_key, p.top_category)}</span>
                <span className="hidden text-right text-sm text-slate-400 sm:block">{p.count}</span>
                <span className="hidden text-right sm:block">
                  {p.alerts > 0
                    ? <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-xs font-semibold text-amber-400">{p.alerts}</span>
                    : <span className="text-xs text-slate-600">—</span>}
                </span>
                <span className={`text-right font-bold tabular-nums ${accent}`}>{money(p.total)}</span>
              </button>
              {open && <InvoiceRows invoices={p.invoices} highlightId={highlightId} t={t} cat={cat} />}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function ProviderLedger({ providers, expandedId, onToggle, highlightId }) {
  const { t, cat } = useT()
  return (
    <PartyTable
      title={t('ledger.suppliers')} subtitle={t('ledger.suppliersSub')}
      parties={providers} accent="text-rose-400"
      expandedId={expandedId} onToggle={onToggle} highlightId={highlightId} t={t} cat={cat}
    />
  )
}

export function ClientLedger({ clients, expandedId, onToggle, highlightId }) {
  const { t, cat } = useT()
  return (
    <PartyTable
      title={t('ledger.clients')} subtitle={t('ledger.clientsSub')}
      parties={clients} accent="text-emerald-400"
      expandedId={expandedId} onToggle={onToggle} highlightId={highlightId} t={t} cat={cat}
    />
  )
}
