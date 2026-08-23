import { useT } from '../i18n.jsx'
import { IconChart, IconReceipt, IconCheck } from './icons.jsx'
import LangToggle from './LangToggle.jsx'

function AccessCard({ onClick, icon, title, subtitle, points, gradient, glow, cta }) {
  return (
    <button
      onClick={onClick}
      className="group relative w-full overflow-hidden rounded-3xl border border-stroke bg-panel p-px text-left transition duration-300 hover:-translate-y-1 hover:border-brand/40"
    >
      {/* halo de fondo al hover */}
      <div className={`pointer-events-none absolute -inset-24 bg-gradient-to-br ${glow} opacity-0 blur-3xl transition duration-500 group-hover:opacity-25`} />
      <div className="relative flex h-full flex-col rounded-3xl bg-panel/95 p-8">
        <div className="mb-6 flex items-start justify-between">
          <div className={`flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br ${gradient} shadow-lg ring-1 ring-white/10`}>
            {icon}
          </div>
          <span className="mt-1 text-2xl text-slate-700 transition duration-300 group-hover:translate-x-1 group-hover:text-brand-glow">
            →
          </span>
        </div>
        <h3 className="text-2xl font-bold tracking-tight text-white">{title}</h3>
        <p className="mt-2 text-sm leading-relaxed text-slate-400">{subtitle}</p>
        <ul className="mt-6 flex-1 space-y-3">
          {points.map((p) => (
            <li key={p} className="flex items-start gap-3 text-sm text-slate-300">
              <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-emerald-500/15">
                <IconCheck className="h-3 w-3 text-emerald-400" />
              </span>
              {p}
            </li>
          ))}
        </ul>
        <div className={`mt-8 flex items-center justify-center rounded-2xl bg-gradient-to-r ${gradient} py-3.5 text-sm font-bold uppercase tracking-wider text-white shadow-lg transition group-hover:brightness-110`}>
          {cta}
        </div>
      </div>
    </button>
  )
}

export default function Login({ onSelectRole }) {
  const { t } = useT()

  return (
    <div className="flex min-h-full flex-col px-4 py-8">
      {/* Toggle de idioma */}
      <div className="mx-auto flex w-full max-w-4xl justify-end">
        <LangToggle />
      </div>

      <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col justify-center animate-scale-in">
        {/* Marca */}
        <div className="mb-12 flex flex-col items-center text-center">
          <div className="relative">
            <div className="absolute inset-0 rounded-3xl bg-brand/30 blur-2xl" />
            <img src="/zira-logo.png" alt="Zira" className="relative h-24 w-24 rounded-3xl shadow-glow" />
          </div>
          <h1 className="mt-6 text-5xl font-extrabold tracking-tight text-white">Zira</h1>
          <p className="mt-4 max-w-xl text-base leading-relaxed text-slate-400">{t('app.tagline')}</p>
        </div>

        {/* Accesos por rol — protagonistas */}
        <p className="mb-6 text-center text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
          {t('login.accessTitle')}
        </p>
        <div className="grid gap-6 sm:grid-cols-2">
          <AccessCard
            onClick={() => onSelectRole('owner')}
            icon={<IconChart className="h-8 w-8 text-white" />}
            gradient="from-brand to-brand-soft" glow="from-brand to-indigo-600"
            title={t('login.owner.title')}
            subtitle={t('login.owner.subtitle')}
            points={[t('login.owner.p1'), t('login.owner.p2'), t('login.owner.p3')]}
            cta={t('login.owner.cta')}
          />
          <AccessCard
            onClick={() => onSelectRole('accountant')}
            icon={<IconReceipt className="h-8 w-8 text-white" />}
            gradient="from-violet-500 to-fuchsia-600" glow="from-violet-500 to-fuchsia-600"
            title={t('login.accountant.title')}
            subtitle={t('login.accountant.subtitle')}
            points={[t('login.accountant.p1'), t('login.accountant.p2'), t('login.accountant.p3')]}
            cta={t('login.accountant.cta')}
          />
        </div>

        <p className="mt-12 text-center text-xs text-slate-600">{t('app.footer')}</p>
      </div>
    </div>
  )
}
