import { useT } from '../i18n.jsx'

export default function LangToggle() {
  const { lang, toggle } = useT()
  return (
    <button
      onClick={toggle}
      title={lang === 'en' ? 'Cambiar a Español' : 'Switch to English'}
      className="flex items-center gap-1.5 rounded-full bg-panel2 px-3 py-1.5 text-xs font-bold text-slate-300 ring-1 ring-stroke transition hover:text-white"
    >
      <span className="text-sm">🌐</span>
      {lang === 'en' ? 'EN' : 'ES'}
    </button>
  )
}
