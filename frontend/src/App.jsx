import { useState } from 'react'
import Login from './components/Login.jsx'
import DashboardShell from './components/DashboardShell.jsx'
import OwnerDashboard from './components/owner/OwnerDashboard.jsx'
import AccountantDashboard from './components/accountant/AccountantDashboard.jsx'
import { IconHome, IconReceipt } from './components/icons.jsx'
import { useT } from './i18n.jsx'

export default function App() {
  const { t } = useT()
  const [role, setRole] = useState(null)
  const [activeKey, setActiveKey] = useState(null)

  const NAV = {
    owner: [{ key: 'resumen', label: t('nav.summary'), icon: <IconHome className="h-5 w-5" />, title: t('title.owner') }],
    accountant: [{ key: 'contable', label: t('nav.accounting'), icon: <IconReceipt className="h-5 w-5" />, title: t('title.accountant') }],
  }

  if (!role) {
    return (
      <Login
        onSelectRole={(r) => {
          setRole(r)
          setActiveKey(NAV[r][0].key)
        }}
      />
    )
  }

  const nav = NAV[role]
  const current = nav.find((n) => n.key === activeKey) || nav[0]

  return (
    <DashboardShell
      role={role} nav={nav} activeKey={activeKey} onNav={setActiveKey}
      onLogout={() => { setRole(null); setActiveKey(null) }}
      title={current.title}
    >
      {role === 'owner' && <OwnerDashboard />}
      {role === 'accountant' && <AccountantDashboard />}
    </DashboardShell>
  )
}
