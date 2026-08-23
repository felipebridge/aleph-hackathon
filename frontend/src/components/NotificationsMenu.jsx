import { useState, useRef, useEffect } from 'react'
import { IconBell, IconCheck, IconUpload, IconReceipt, IconAlert } from './icons.jsx'
import { useT } from '../i18n.jsx'

// Notificaciones simuladas (demo): recibos subidos/adjuntados, anomalías, etc.
const NOTIFS = [
  { id: 1, icon: IconUpload, color: 'text-emerald-400 bg-emerald-500/15', ago: [8, 'min'], read: false },
  { id: 2, icon: IconReceipt, color: 'text-brand-glow bg-brand/15', ago: [42, 'min'], read: false },
  { id: 3, icon: IconAlert, color: 'text-amber-400 bg-amber-500/15', ago: [3, 'hour'], read: false },
  { id: 4, icon: IconUpload, color: 'text-emerald-400 bg-emerald-500/15', ago: [6, 'hour'], read: true },
  { id: 5, icon: IconCheck, color: 'text-sky-400 bg-sky-500/15', ago: [1, 'day'], read: true },
]

export default function NotificationsMenu() {
  const { t } = useT()
  const [open, setOpen] = useState(false)
  const [readAll, setReadAll] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const onClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const unread = readAll ? 0 : NOTIFS.filter((n) => !n.read).length

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative flex h-9 w-9 items-center justify-center rounded-full bg-panel2 text-slate-400 ring-1 ring-stroke transition hover:text-white"
      >
        <IconBell className="h-5 w-5" />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[9px] font-bold text-white">
            {unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 animate-fade-up overflow-hidden rounded-2xl border border-stroke bg-panel shadow-glow">
          <div className="flex items-center justify-between border-b border-stroke px-4 py-3">
            <h3 className="text-sm font-bold text-white">{t('notif.title')}</h3>
            <button
              onClick={() => setReadAll(true)}
              className="text-[11px] font-semibold text-brand-glow hover:underline"
            >
              {t('notif.markAll')}
            </button>
          </div>
          <div className="max-h-96 overflow-y-auto soft-scroll">
            {NOTIFS.map((n) => {
              const Icon = n.icon
              const isRead = readAll || n.read
              const [num, unit] = n.ago
              return (
                <div
                  key={n.id}
                  className={`flex gap-3 border-b border-stroke/50 px-4 py-3 transition last:border-0 hover:bg-panel2/50 ${
                    isRead ? '' : 'bg-brand/[0.04]'
                  }`}
                >
                  <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${n.color}`}>
                    <Icon className="h-4.5 w-4.5" style={{ height: 18, width: 18 }} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm font-semibold text-slate-100">{t(`notif.${n.id}.title`)}</p>
                      {!isRead && <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-brand-glow" />}
                    </div>
                    <p className="mt-0.5 text-xs leading-snug text-slate-400">{t(`notif.${n.id}.body`)}</p>
                    <p className="mt-1 text-[10px] text-slate-600">
                      {num} {t(`notif.ago.${unit}`)}
                    </p>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
