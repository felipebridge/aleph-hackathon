import { PLANS, useT } from '../i18n.jsx'
import { IconCheck } from './icons.jsx'

export default function PlansBar({ open, onClose, currentPlan = 'free' }) {
  const { t, lang } = useT()
  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        className="mt-10 w-full max-w-6xl animate-scale-in rounded-3xl border border-stroke bg-panel p-6 shadow-glow sm:p-8"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-6 flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <img src="/zira-logo.png" alt="Zira" className="h-11 w-11 rounded-xl" />
            <div>
              <h2 className="text-xl font-extrabold text-white">{t('plans.title')}</h2>
              <p className="mt-0.5 max-w-xl text-xs text-slate-400">{t('plans.subtitle')}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg bg-panel2 px-3 py-1.5 text-sm font-semibold text-slate-300 ring-1 ring-stroke transition hover:text-white"
          >
            {t('plans.close')} ✕
          </button>
        </div>

        <div className="grid gap-4 lg:grid-cols-4">
          {PLANS.map((plan) => {
            const loc = plan[lang] || plan.en
            const isCurrent = plan.key === currentPlan
            return (
              <div
                key={plan.key}
                className={`relative flex flex-col rounded-2xl border p-5 transition ${
                  plan.highlight
                    ? 'border-brand/50 bg-gradient-to-b from-brand/10 to-panel'
                    : 'border-stroke bg-panel2/40'
                }`}
              >
                {plan.highlight && (
                  <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 rounded-full bg-brand px-3 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">
                    {loc.tagline}
                  </span>
                )}
                <h3 className={`text-xs font-bold uppercase tracking-widest ${plan.accent}`}>{plan.name}</h3>
                <div className="mt-2 flex items-end gap-1">
                  <span className="text-3xl font-extrabold text-white">{plan.price}</span>
                  {plan.price !== 'Custom' && (
                    <span className="mb-1 text-xs text-slate-500">{t('plans.month')}</span>
                  )}
                </div>
                <p className="mt-0.5 text-[11px] text-slate-500">{!plan.highlight && loc.tagline}</p>
                <ul className="mt-4 flex-1 space-y-2">
                  {loc.features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-xs text-slate-400">
                      <IconCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" />
                      {f}
                    </li>
                  ))}
                </ul>
                <button
                  disabled={isCurrent}
                  className={`mt-5 rounded-xl py-2.5 text-sm font-bold transition ${
                    isCurrent
                      ? 'cursor-default bg-panel2 text-slate-500 ring-1 ring-stroke'
                      : plan.highlight
                        ? 'bg-brand text-white hover:bg-brand-soft'
                        : 'bg-panel2 text-slate-200 ring-1 ring-stroke hover:bg-stroke'
                  }`}
                >
                  {isCurrent ? t('plans.current') : loc.cta}
                </button>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
