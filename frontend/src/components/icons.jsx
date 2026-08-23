// Íconos SVG inline (stroke), livianos y sin dependencias.
const base = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }

export const IconHome = (p) => (
  <svg viewBox="0 0 24 24" {...base} {...p}><path d="M3 10.5 12 3l9 7.5" /><path d="M5 9.5V21h14V9.5" /></svg>
)
export const IconChart = (p) => (
  <svg viewBox="0 0 24 24" {...base} {...p}><path d="M4 20h16" /><rect x="6" y="10" width="3" height="7" /><rect x="11" y="6" width="3" height="11" /><rect x="16" y="13" width="3" height="4" /></svg>
)
export const IconWallet = (p) => (
  <svg viewBox="0 0 24 24" {...base} {...p}><rect x="3" y="6" width="18" height="13" rx="2.5" /><path d="M3 10h18" /><circle cx="17" cy="14" r="1.2" fill="currentColor" stroke="none" /></svg>
)
export const IconReceipt = (p) => (
  <svg viewBox="0 0 24 24" {...base} {...p}><path d="M6 3h12v18l-3-2-3 2-3-2-3 2V3Z" /><path d="M9 8h6M9 12h6" /></svg>
)
export const IconUsers = (p) => (
  <svg viewBox="0 0 24 24" {...base} {...p}><circle cx="9" cy="8" r="3" /><path d="M3.5 20a5.5 5.5 0 0 1 11 0" /><path d="M16 5.5a3 3 0 0 1 0 5.8" /><path d="M17.5 20a5.5 5.5 0 0 0-3-4.9" /></svg>
)
export const IconUpload = (p) => (
  <svg viewBox="0 0 24 24" {...base} {...p}><path d="M12 16V4" /><path d="m7 9 5-5 5 5" /><path d="M4 20h16" /></svg>
)
export const IconBell = (p) => (
  <svg viewBox="0 0 24 24" {...base} {...p}><path d="M6 9a6 6 0 0 1 12 0c0 6 2 7 2 7H4s2-1 2-7Z" /><path d="M10 20a2 2 0 0 0 4 0" /></svg>
)
export const IconLogout = (p) => (
  <svg viewBox="0 0 24 24" {...base} {...p}><path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" /><path d="M10 12H3" /><path d="m6 8-4 4 4 4" /></svg>
)
export const IconAlert = (p) => (
  <svg viewBox="0 0 24 24" {...base} {...p}><path d="M12 3 2 20h20L12 3Z" /><path d="M12 10v4M12 17h.01" /></svg>
)
export const IconCheck = (p) => (
  <svg viewBox="0 0 24 24" {...base} {...p}><path d="m4 12 5 5L20 6" /></svg>
)
export const IconTrend = (p) => (
  <svg viewBox="0 0 24 24" {...base} {...p}><path d="m3 17 6-6 4 4 8-8" /><path d="M21 7h-5M21 7v5" /></svg>
)
export const IconSettings = (p) => (
  <svg viewBox="0 0 24 24" {...base} {...p}><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2" /></svg>
)
