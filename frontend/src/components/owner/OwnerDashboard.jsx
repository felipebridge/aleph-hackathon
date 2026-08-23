import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from 'recharts'
import { getOwnerDashboard, money, moneyFull } from '../../api.js'
import { IconTrend, IconWallet, IconChart } from '../icons.jsx'
import { useT } from '../../i18n.jsx'
import ExpenseDonut from './ExpenseDonut.jsx'

function Kpi({ label, value, sub, accent, icon }) {
  return (
    <div className="card animate-fade-up p-5">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
          <div className={`mt-2 text-2xl font-extrabold tracking-tight ${accent}`}>{value}</div>
          {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
        </div>
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-panel2 text-slate-400">
          {icon}
        </div>
      </div>
    </div>
  )
}

function FlowTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-stroke bg-panel px-3 py-2 text-xs shadow-card">
      <div className="mb-1 font-semibold text-slate-300">{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: p.fill }} />
          <span className="text-slate-400">{p.name}:</span>
          <span className="font-semibold text-white">{money(p.value)}</span>
        </div>
      ))}
    </div>
  )
}

const monthLabel = (m) => {
  const meses = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
  const [, mm] = (m || '').split('-')
  return meses[parseInt(mm, 10) - 1] || m
}

export default function OwnerDashboard() {
  const { t, cat } = useT()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    getOwnerDashboard().then(setData).catch((e) => setError(e.message))
  }, [])

  if (error) return <div className="card p-6 text-sm text-rose-400">Error: {error}</div>
  if (!data) {
    return (
      <div className="flex h-64 items-center justify-center">
        <span className="h-8 w-8 animate-spin rounded-full border-2 border-stroke border-t-brand-glow" />
      </div>
    )
  }

  const { kpis, expense_breakdown, income_breakdown, monthly_flow, top_expense, movements } = data
  const profitable = kpis.profit >= 0
  const flow = (monthly_flow || []).map((f) => ({ ...f, label: monthLabel(f.month) }))

  return (
    <div className="space-y-6">
      {/* KPIs */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi label={t('kpi.income')} value={money(kpis.income)} sub={`${kpis.count_income} ${t('kpi.receipts')}`}
          accent="text-emerald-400" icon={<IconWallet className="h-5 w-5" />} />
        <Kpi label={t('kpi.expense')} value={money(kpis.expense)} sub={`${kpis.count_expense} ${t('kpi.receipts')}`}
          accent="text-rose-400" icon={<IconChart className="h-5 w-5" />} />
        <Kpi label={profitable ? t('kpi.profit') : t('kpi.loss')} value={money(Math.abs(kpis.profit))}
          sub={`${t('kpi.margin')} ${kpis.margin_pct}%`} accent={profitable ? 'text-white' : 'text-rose-400'}
          icon={<IconTrend className="h-5 w-5" />} />
        <Kpi label={t('kpi.topExpense')} value={top_expense ? cat(top_expense.key, top_expense.label) : '—'}
          sub={top_expense ? `${money(top_expense.amount)} · ${top_expense.percent}%` : ''}
          accent="text-brand-glow" icon={<IconChart className="h-5 w-5" />} />
      </div>

      {/* Flujo mensual ingreso vs egreso */}
      <div className="card animate-fade-up p-6">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-white">{t('chart.flowTitle')}</h2>
            <p className="text-xs text-slate-500">{t('chart.flowSubtitle')}</p>
          </div>
        </div>
        <div className="h-[280px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={flow} margin={{ top: 6, right: 6, left: -10, bottom: 0 }} barGap={6}>
              <CartesianGrid strokeDasharray="3 3" stroke="#222835" vertical={false} />
              <XAxis dataKey="label" tick={{ fill: '#94a3b8', fontSize: 11 }}
                axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#64748b', fontSize: 10 }}
                tickFormatter={(v) => v >= 1000 ? `${(v / 1000000).toFixed(1)}M` : v}
                axisLine={false} tickLine={false} width={44} />
              <Tooltip content={<FlowTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
              <Legend iconType="circle" wrapperStyle={{ fontSize: 12, color: '#94a3b8' }} />
              <Bar dataKey="income" name={t('chart.income')} fill="#34d399" radius={[5, 5, 0, 0]} maxBarSize={40} />
              <Bar dataKey="expense" name={t('chart.expense')} fill="#fb7185" radius={[5, 5, 0, 0]} maxBarSize={40} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-4 grid grid-cols-3 gap-4 border-t border-stroke pt-4">
          <div>
            <div className="text-xs text-slate-500">{t('chart.totalIncome')}</div>
            <div className="mt-1 text-sm font-bold text-emerald-400">{moneyFull(kpis.income)}</div>
          </div>
          <div>
            <div className="text-xs text-slate-500">{t('chart.totalExpense')}</div>
            <div className="mt-1 text-sm font-bold text-rose-400">{moneyFull(kpis.expense)}</div>
          </div>
          <div>
            <div className="text-xs text-slate-500">{t('chart.net')}</div>
            <div className={`mt-1 text-sm font-bold ${profitable ? 'text-white' : 'text-rose-400'}`}>
              {profitable ? '+' : '−'}{moneyFull(Math.abs(kpis.profit))}
            </div>
          </div>
        </div>
      </div>

      {/* Dos donuts: egresos e ingresos por rubro */}
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card animate-fade-up p-6">
          <div className="mb-1 flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-rose-400" />
            <h2 className="text-base font-bold text-white">{t('donut.expenseTitle')}</h2>
          </div>
          <p className="mb-4 text-xs text-slate-500">{t('donut.expenseSub')}</p>
          <ExpenseDonut breakdown={expense_breakdown} />
        </div>
        <div className="card animate-fade-up p-6">
          <div className="mb-1 flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
            <h2 className="text-base font-bold text-white">{t('donut.incomeTitle')}</h2>
          </div>
          <p className="mb-4 text-xs text-slate-500">{t('donut.incomeSub')}</p>
          <ExpenseDonut breakdown={income_breakdown} />
        </div>
      </div>

      {/* Movimientos */}
      {movements?.length > 0 && <MovementsTable movements={movements} t={t} cat={cat} />}
    </div>
  )
}

function MovementsTable({ movements, t, cat }) {
  return (
    <div className="card overflow-hidden animate-fade-up">
      <div className="flex items-center justify-between border-b border-stroke px-5 py-4">
        <div>
          <h2 className="text-base font-bold text-white">{t('mov.title')}</h2>
          <p className="text-xs text-slate-500">{t('mov.subtitle')}</p>
        </div>
        <span className="rounded-full bg-panel2 px-2.5 py-0.5 text-xs font-semibold text-slate-400">
          {movements.length}
        </span>
      </div>
      <div className="max-h-[420px] overflow-y-auto soft-scroll">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-panel">
            <tr className="border-b border-stroke text-left text-[11px] uppercase tracking-wide text-slate-500">
              <th className="px-5 py-3 font-semibold">{t('mov.id')}</th>
              <th className="px-5 py-3 font-semibold">{t('mov.type')}</th>
              <th className="px-5 py-3 font-semibold">{t('mov.counterparty')}</th>
              <th className="px-5 py-3 font-semibold">{t('mov.category')}</th>
              <th className="px-5 py-3 text-right font-semibold">{t('mov.amount')}</th>
            </tr>
          </thead>
          <tbody>
            {movements.map((m) => {
              const ingreso = m.direction === 'ingreso'
              return (
                <tr key={m.id} className="border-b border-stroke/60 last:border-0 hover:bg-panel2/40">
                  <td className="px-5 py-3 font-mono text-xs text-slate-500">
                    {m.id}
                    {m.source === 'upload' && <span className="ml-1 text-brand-glow">•</span>}
                  </td>
                  <td className="px-5 py-3">
                    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                      ingreso ? 'bg-emerald-500/15 text-emerald-400' : 'bg-rose-500/15 text-rose-400'
                    }`}>
                      {ingreso ? `↓ ${t('mov.income')}` : `↑ ${t('mov.expense')}`}
                    </span>
                  </td>
                  <td className="px-5 py-3 font-medium text-slate-200">{m.counterparty}</td>
                  <td className="px-5 py-3">
                    <span className="inline-flex items-center gap-1.5 text-xs text-slate-400">
                      <span className="h-2 w-2 rounded-sm" style={{ background: m.category_color }} />
                      {cat(m.category_key, m.category)}
                    </span>
                  </td>
                  <td className={`px-5 py-3 text-right tabular-nums font-semibold ${
                    ingreso ? 'text-emerald-400' : 'text-rose-400'
                  }`}>
                    {ingreso ? '+' : '−'}{money(m.amount)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
