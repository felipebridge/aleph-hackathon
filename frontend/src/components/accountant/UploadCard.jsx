import { useState, useRef } from 'react'
import { analyzeFile, money } from '../../api.js'
import { IconUpload, IconCheck, IconReceipt } from '../icons.jsx'
import { useT } from '../../i18n.jsx'

function DetectedField({ label, value, mono }) {
  return (
    <div className="rounded-lg bg-panel2 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-0.5 text-sm font-semibold text-white ${mono ? 'font-mono' : ''}`}>
        {value ?? '—'}
      </div>
    </div>
  )
}

function DirectionBadge({ direction, confidence, t }) {
  const ingreso = direction === 'ingreso'
  return (
    <div className={`flex items-center justify-between rounded-xl px-4 py-3 ${
      ingreso ? 'bg-emerald-500/10 ring-1 ring-emerald-500/30' : 'bg-rose-500/10 ring-1 ring-rose-500/30'
    }`}>
      <div className="flex items-center gap-2.5">
        <span className={`flex h-8 w-8 items-center justify-center rounded-lg text-lg font-bold ${
          ingreso ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'
        }`}>
          {ingreso ? '↓' : '↑'}
        </span>
        <div>
          <div className={`text-sm font-bold ${ingreso ? 'text-emerald-400' : 'text-rose-400'}`}>
            {ingreso ? t('upload.income') : t('upload.expense')}
          </div>
          <div className="text-[11px] text-slate-500">
            {ingreso ? t('upload.incomeHint') : t('upload.expenseHint')}
          </div>
        </div>
      </div>
      <span className="rounded-full bg-black/20 px-2 py-0.5 text-[10px] font-semibold uppercase text-slate-400">
        {t('upload.confidence')} {confidence}
      </span>
    </div>
  )
}

export default function UploadCard({ onAnalyzed }) {
  const { t, cat } = useT()
  const [dragOver, setDragOver] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const inputRef = useRef(null)

  const handleFile = async (file) => {
    if (!file) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const data = await analyzeFile(file)
      setResult(data)
      onAnalyzed?.(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card p-6">
      <div className="mb-1 flex items-center gap-2">
        <IconReceipt className="h-5 w-5 text-brand-glow" />
        <h2 className="text-base font-bold text-white">{t('upload.title')}</h2>
      </div>
      <p className="mb-4 text-xs text-slate-500">{t('upload.desc')}</p>

      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault(); setDragOver(false)
          handleFile(e.dataTransfer.files?.[0])
        }}
        onClick={() => inputRef.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-8 text-center transition ${
          dragOver ? 'border-brand bg-brand/10' : 'border-stroke hover:border-brand/50 hover:bg-panel2/50'
        }`}
      >
        <div className="mb-2 flex h-11 w-11 items-center justify-center rounded-xl bg-panel2 text-brand-glow">
          {loading
            ? <span className="h-5 w-5 animate-spin rounded-full border-2 border-stroke border-t-brand-glow" />
            : <IconUpload className="h-5 w-5" />}
        </div>
        <div className="text-sm font-semibold text-slate-200">
          {loading ? t('upload.reading') : t('upload.drop')}
        </div>
        <div className="mt-1 text-xs text-slate-500">{t('upload.formats')}</div>
        <input
          ref={inputRef} type="file" accept=".pdf,.jpg,.jpeg,.png" className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
      </div>

      {error && (
        <div className="mt-4 rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-xs text-rose-300">
          {error}
        </div>
      )}

      {result && (
        <div className="mt-4 animate-fade-up space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-emerald-400">
            <IconCheck className="h-4 w-4" /> {t('upload.processed')}
            <span className="ml-auto rounded-full bg-panel2 px-2 py-0.5 text-[10px] font-normal text-slate-500">
              OCR: {result.engine}
            </span>
          </div>

          <DirectionBadge direction={result.direction} confidence={result.direction_confidence} t={t} />

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <DetectedField label={result.role} value={result.counterparty} />
            <DetectedField label={`ID ${result.role}`} value={result.party_id} mono />
            <DetectedField label={t('upload.category')} value={cat(result.category_key, result.category)} />
            <DetectedField label={t('mov.amount')} value={money(result.amount)} />
            <DetectedField label={t('upload.date')} value={result.date} />
            <DetectedField label={t('upload.ziraDetected')} value={result.zira_detected ? t('upload.yes') : t('upload.no')} />
          </div>

          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: result.category_color }} />
            <span className="text-xs text-slate-400">
              {t('upload.classifiedAs')} <b className="text-slate-200">{cat(result.category_key, result.category)}</b>
              {result.cuits_found?.length > 0 && (
                <span className="text-slate-500"> · CUITs: {result.cuits_found.join(', ')}</span>
              )}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
