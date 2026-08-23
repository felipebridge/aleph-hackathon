import { useState } from 'react'
import { IconLogout } from './icons.jsx'
import { useT } from '../i18n.jsx'
import LangToggle from './LangToggle.jsx'
import PlansBar from './PlansBar.jsx'
import NotificationsMenu from './NotificationsMenu.jsx'
import AccountMenu from './AccountMenu.jsx'

function NavItem({ icon, label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium transition ${
        active
          ? 'bg-brand/15 text-white ring-1 ring-brand/30'
          : 'text-slate-400 hover:bg-panel2 hover:text-slate-200'
      }`}
    >
      <span className={active ? 'text-brand-glow' : 'text-slate-500'}>{icon}</span>
      {label}
    </button>
  )
}

export default function DashboardShell({
  role, nav, activeKey, onNav, onLogout, onSwitchRole, title, children,
}) {
  const { t } = useT()
  const [plansOpen, setPlansOpen] = useState(false)
  const roleLabel = role === 'owner' ? t('role.owner') : t('role.accountant')

  return (
    <div className="flex min-h-full">
      <PlansBar open={plansOpen} onClose={() => setPlansOpen(false)} currentPlan="free" />

      {/* Sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-stroke bg-panel/60 p-4 lg:flex">
        <div className="mb-8 flex items-center gap-3 px-2 pt-2">
          <img src="/zira-logo.png" alt="Zira" className="h-10 w-10 rounded-xl" />
          <div>
            <div className="text-lg font-extrabold leading-none text-white">Zira</div>
            <div className="text-[11px] text-slate-500">{t('brand.subtitle')}</div>
          </div>
        </div>

        <nav className="flex-1 space-y-1">
          {nav.map((item) => (
            <NavItem
              key={item.key} icon={item.icon} label={item.label}
              active={activeKey === item.key} onClick={() => onNav(item.key)}
            />
          ))}
        </nav>

        <button
          onClick={onLogout}
          className="mt-4 flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium text-slate-400 transition hover:bg-panel2 hover:text-slate-200"
        >
          <IconLogout className="h-5 w-5 text-slate-500" />
          {t('header.logout')}
        </button>
      </aside>

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 flex items-center justify-between border-b border-stroke bg-bg/80 px-6 py-4 backdrop-blur">
          <div className="flex items-center gap-3">
            <img src="/zira-logo.png" alt="Zira" className="h-8 w-8 rounded-lg lg:hidden" />
            <h1 className="text-xl font-bold text-white">{title}</h1>
          </div>
          <div className="flex items-center gap-2.5">
            {/* Insignia de planes */}
            <button
              onClick={() => setPlansOpen(true)}
              className="flex items-center gap-1.5 rounded-full bg-gradient-to-r from-brand to-brand-soft px-3.5 py-1.5 text-xs font-bold text-white shadow-sm transition hover:brightness-110"
            >
              <span>✦</span> {t('header.plans')}
            </button>
            <LangToggle />
            <span className="hidden rounded-full bg-panel2 px-3 py-1 text-xs font-semibold text-slate-300 ring-1 ring-stroke sm:inline">
              {roleLabel}
            </span>
            <NotificationsMenu />
            <AccountMenu role={role} onSwitchRole={onSwitchRole} onLogout={onLogout} />
          </div>
        </header>

        <main className="soft-scroll flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  )
}
