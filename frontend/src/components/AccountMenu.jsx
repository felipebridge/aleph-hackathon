import { useState, useRef, useEffect } from 'react'
import { IconChart, IconReceipt, IconCheck, IconLogout } from './icons.jsx'
import { useT } from '../i18n.jsx'

export default function AccountMenu({ role, onSwitchRole, onLogout }) {
  const { t } = useT()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const onClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const options = [
    { key: 'owner', icon: IconChart, grad: 'from-brand to-brand-soft',
      title: t('switch.owner'), desc: t('switch.ownerDesc') },
    { key: 'accountant', icon: IconReceipt, grad: 'from-violet-500 to-fuchsia-600',
      title: t('switch.accountant'), desc: t('switch.accountantDesc') },
  ]

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-brand to-brand-soft text-sm font-bold text-white ring-2 ring-transparent transition hover:ring-brand/40"
      >
        {role === 'owner' ? 'D' : 'C'}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-72 animate-fade-up overflow-hidden rounded-2xl border border-stroke bg-panel shadow-glow">
          <div className="border-b border-stroke px-4 py-3">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              {t('switch.title')}
            </p>
          </div>
          <div className="p-1.5">
            {options.map((o) => {
              const Icon = o.icon
              const active = role === o.key
              return (
                <button
                  key={o.key}
                  onClick={() => { if (!active) onSwitchRole(o.key); setOpen(false) }}
                  className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition ${
                    active ? 'bg-panel2' : 'hover:bg-panel2/60'
                  }`}
                >
                  <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br ${o.grad}`}>
                    <Icon className="h-5 w-5 text-white" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold text-slate-100">{o.title}</div>
                    <div className="text-[11px] text-slate-500">{o.desc}</div>
                  </div>
                  {active && (
                    <span className="flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
                      <IconCheck className="h-3 w-3" /> {t('switch.active')}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
          <div className="border-t border-stroke p-1.5">
            <button
              onClick={() => { onLogout(); setOpen(false) }}
              className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-400 transition hover:bg-panel2/60 hover:text-slate-200"
            >
              <IconLogout className="h-5 w-5 text-slate-500" />
              {t('header.logout')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
