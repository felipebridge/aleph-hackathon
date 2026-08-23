import { useState } from 'react'
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts'
import { money } from '../../api.js'
import { useT } from '../../i18n.jsx'

export default function ExpenseDonut({ breakdown }) {
  const { t, cat } = useT()
  const [active, setActive] = useState(0)
  if (!breakdown?.length) {
    return <p className="text-sm text-slate-500">—</p>
  }

  const total = breakdown.reduce((s, b) => s + b.amount, 0)
  const focused = breakdown[active] || breakdown[0]

  return (
    <div>
      <div className="relative mx-auto h-[220px] w-full max-w-[260px]">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={breakdown}
              dataKey="amount"
              nameKey="label"
              innerRadius={72}
              outerRadius={100}
              paddingAngle={3}
              cornerRadius={8}
              stroke="none"
              onMouseEnter={(_, i) => setActive(i)}
            >
              {breakdown.map((b, i) => (
                <Cell
                  key={b.key}
                  fill={b.color}
                  opacity={i === active ? 1 : 0.55}
                  style={{ transition: 'opacity .2s', cursor: 'pointer' }}
                />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        {/* Centro */}
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <div className="text-lg font-extrabold text-white">{money(focused.amount)}</div>
          <div className="mt-0.5 max-w-[120px] text-center text-[11px] leading-tight text-slate-400">
            {cat(focused.key, focused.label)}
          </div>
        </div>
      </div>

      {/* Leyenda */}
      <div className="mt-5 space-y-2.5">
        {breakdown.map((b, i) => (
          <button
            key={b.key}
            onMouseEnter={() => setActive(i)}
            className={`flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left transition ${
              i === active ? 'bg-panel2' : ''
            }`}
          >
            <div className="flex items-center gap-2.5">
              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: b.color }} />
              <span className="text-sm text-slate-300">{cat(b.key, b.label)}</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-slate-500">{money(b.amount)}</span>
              <span className="w-10 text-right text-sm font-semibold text-white">
                {b.percent}%
              </span>
            </div>
          </button>
        ))}
      </div>
      <div className="mt-4 flex items-center justify-between border-t border-stroke pt-3">
        <span className="text-xs uppercase tracking-wide text-slate-500">{t('donut.total')}</span>
        <span className="text-sm font-bold text-white">{money(total)}</span>
      </div>
    </div>
  )
}
