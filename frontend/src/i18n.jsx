import { createContext, useContext, useState, useCallback } from 'react'

// Diccionario de traducciones. Inglés por defecto; el usuario puede cambiar a
// español con el toggle del header. Claves planas por simplicidad.
const STRINGS = {
  en: {
    'app.tagline': 'Smart accounting for modern SMEs. With QVAC: 100% on-device OCR and reconciliation — total data privacy.',
    'app.footer': 'Privacy-First AI Financial Reconciliation Agent · Tether QVAC Track',

    'login.plansTitle': 'Our plans for SMEs',
    'login.accessTitle': 'Choose your access',
    'login.owner.title': 'Business Owner Access',
    'login.owner.subtitle': 'Strategic vision and full control of the business.',
    'login.owner.p1': 'Income, expenses and profitability in real time',
    'login.owner.p2': 'Cash flow and margins',
    'login.owner.p3': 'Spending category analysis',
    'login.owner.cta': 'Sign in as owner',
    'login.accountant.title': 'Accountant Access',
    'login.accountant.subtitle': 'Automation and precision for accounting.',
    'login.accountant.p1': 'AI-powered supplier detection',
    'login.accountant.p2': 'Invoice and receipt upload',
    'login.accountant.p3': 'General ledger and anomaly detection',
    'login.accountant.cta': 'Sign in as accountant',

    'nav.summary': 'Overview',
    'nav.accounting': 'Accounting',
    'title.owner': 'Business overview',
    'title.accountant': 'Accounting area',
    'role.owner': 'Owner',
    'role.accountant': 'Accountant',
    'header.plans': 'Plans',
    'header.logout': 'Sign out',

    'plans.title': 'Plans & Pricing',
    'plans.subtitle': 'Decentralized AI inconsistency detection. QVAC runs on your own hardware — zero variable cost, total privacy.',
    'plans.month': '/ month',
    'plans.current': 'Current plan',
    'plans.choose': 'Choose plan',
    'plans.contact': 'Contact sales',
    'plans.close': 'Close',

    'kpi.income': 'Income',
    'kpi.expense': 'Expenses',
    'kpi.profit': 'Profit',
    'kpi.loss': 'Loss',
    'kpi.receipts': 'receipts',
    'kpi.margin': 'Margin',
    'kpi.topExpense': 'Top expense',

    'chart.flowTitle': 'Income vs expenses by month',
    'chart.flowSubtitle': 'Cash flow evolution',
    'chart.income': 'Income',
    'chart.expense': 'Expenses',
    'chart.totalIncome': 'Total income',
    'chart.totalExpense': 'Total expenses',
    'chart.net': 'Net result',
    'donut.expenseTitle': 'Expenses by category',
    'donut.expenseSub': 'Where the money went.',
    'donut.incomeTitle': 'Income by category',
    'donut.incomeSub': 'Where revenue comes from.',
    'donut.total': 'Total',

    'mov.title': 'Movements',
    'mov.subtitle': 'Automatically classified by AI based on ZIRA\'s role',
    'mov.id': 'ID',
    'mov.type': 'Type',
    'mov.counterparty': 'Counterparty',
    'mov.category': 'Category',
    'mov.amount': 'Amount',
    'mov.income': 'Income',
    'mov.expense': 'Expense',

    'upload.title': 'Upload document',
    'upload.desc': 'Upload a photo or PDF of an invoice/receipt. The AI reads it and detects whether it is income or expense based on ZIRA\'s role, the category and the amount.',
    'upload.reading': 'Reading with AI…',
    'upload.drop': 'Drag a file or click',
    'upload.formats': 'PDF, JPG or PNG · or from WhatsApp',
    'upload.processed': 'Document processed',
    'upload.income': 'INCOME',
    'upload.expense': 'EXPENSE',
    'upload.incomeHint': 'ZIRA issued a sale',
    'upload.expenseHint': 'ZIRA was billed a purchase',
    'upload.confidence': 'confidence',
    'upload.category': 'Category',
    'upload.date': 'Date',
    'upload.ziraDetected': 'ZIRA detected',
    'upload.classifiedAs': 'Classified as',
    'upload.yes': 'Yes',
    'upload.no': 'No',

    'stats.invoices': 'Invoices',
    'stats.alerts': 'Alerts',
    'stats.suppliers': 'Suppliers',
    'stats.clients': 'Clients',
    'stats.collected': 'Collected',
    'stats.paid': 'Paid',

    'alerts.title': 'Invoices with alerts',
    'alerts.view': 'View →',

    'ledger.suppliers': 'Suppliers',
    'ledger.suppliersSub': 'Who we pay · click to see their invoices',
    'ledger.clients': 'Clients',
    'ledger.clientsSub': 'Who pays us · click to see their invoices',
    'ledger.idName': 'ID / Name',
    'ledger.mainCategory': 'Main category',
    'ledger.invoices': 'Invoices',
    'ledger.alerts': 'Alerts',
    'ledger.total': 'Total',
    'ledger.uploaded': 'uploaded',
    'ledger.alert': 'alert',

    'lang.switch': 'Español',
    'brand.subtitle': 'Accounting management',
  },
  es: {
    'app.tagline': 'Gestión contable inteligente para PyMEs modernas. Con QVAC: OCR y conciliación 100% local — total privacidad de tus datos.',
    'app.footer': 'Privacy-First AI Financial Reconciliation Agent · Tether QVAC Track',

    'login.plansTitle': 'Nuestros planes para PyMEs',
    'login.accessTitle': 'Elegí tu acceso',
    'login.owner.title': 'Acceso Dueño de Empresa',
    'login.owner.subtitle': 'Visión estratégica y control total del negocio.',
    'login.owner.p1': 'Ingresos, gastos y rentabilidad en tiempo real',
    'login.owner.p2': 'Flujo de caja y márgenes',
    'login.owner.p3': 'Análisis de rubros de gasto',
    'login.owner.cta': 'Iniciar sesión dueño',
    'login.accountant.title': 'Acceso Contador/a',
    'login.accountant.subtitle': 'Automatización y precisión para la gestión contable.',
    'login.accountant.p1': 'Detección de proveedores con IA',
    'login.accountant.p2': 'Carga de facturas y recibos',
    'login.accountant.p3': 'Libro mayor y detección de anomalías',
    'login.accountant.cta': 'Iniciar sesión contador',

    'nav.summary': 'Resumen',
    'nav.accounting': 'Área contable',
    'title.owner': 'Resumen del negocio',
    'title.accountant': 'Área contable',
    'role.owner': 'Dueño',
    'role.accountant': 'Contador',
    'header.plans': 'Planes',
    'header.logout': 'Cerrar sesión',

    'plans.title': 'Planes y Precios',
    'plans.subtitle': 'Detección de inconsistencias con IA descentralizada. QVAC corre en tu propio hardware — costo variable cero, total privacidad.',
    'plans.month': '/ mes',
    'plans.current': 'Plan actual',
    'plans.choose': 'Elegir plan',
    'plans.contact': 'Contactar ventas',
    'plans.close': 'Cerrar',

    'kpi.income': 'Ingresos',
    'kpi.expense': 'Egresos',
    'kpi.profit': 'Ganancia',
    'kpi.loss': 'Pérdida',
    'kpi.receipts': 'comprobantes',
    'kpi.margin': 'Margen',
    'kpi.topExpense': 'Mayor gasto',

    'chart.flowTitle': 'Ingresos vs egresos por mes',
    'chart.flowSubtitle': 'Evolución del flujo de caja',
    'chart.income': 'Ingresos',
    'chart.expense': 'Egresos',
    'chart.totalIncome': 'Total ingresos',
    'chart.totalExpense': 'Total egresos',
    'chart.net': 'Resultado neto',
    'donut.expenseTitle': 'Egresos por rubro',
    'donut.expenseSub': 'En qué categorías se fue el dinero.',
    'donut.incomeTitle': 'Ingresos por rubro',
    'donut.incomeSub': 'De dónde viene la facturación.',
    'donut.total': 'Total',

    'mov.title': 'Movimientos',
    'mov.subtitle': 'Clasificados automáticamente por la IA según el rol de ZIRA',
    'mov.id': 'ID',
    'mov.type': 'Tipo',
    'mov.counterparty': 'Contraparte',
    'mov.category': 'Rubro',
    'mov.amount': 'Monto',
    'mov.income': 'Ingreso',
    'mov.expense': 'Egreso',

    'upload.title': 'Cargar comprobante',
    'upload.desc': 'Subí una foto o PDF de una factura/recibo. La IA lo lee y detecta si es ingreso o egreso según el rol de ZIRA, el rubro y el monto.',
    'upload.reading': 'Leyendo con IA…',
    'upload.drop': 'Arrastrá un archivo o hacé clic',
    'upload.formats': 'PDF, JPG o PNG · o desde WhatsApp',
    'upload.processed': 'Comprobante procesado',
    'upload.income': 'INGRESO',
    'upload.expense': 'EGRESO',
    'upload.incomeHint': 'ZIRA facturó una venta',
    'upload.expenseHint': 'A ZIRA le facturaron una compra',
    'upload.confidence': 'confianza',
    'upload.category': 'Rubro',
    'upload.date': 'Fecha',
    'upload.ziraDetected': 'ZIRA detectada',
    'upload.classifiedAs': 'Clasificado como',
    'upload.yes': 'Sí',
    'upload.no': 'No',

    'stats.invoices': 'Facturas',
    'stats.alerts': 'Alertas',
    'stats.suppliers': 'Proveedores',
    'stats.clients': 'Clientes',
    'stats.collected': 'Cobrado',
    'stats.paid': 'Pagado',

    'alerts.title': 'Facturas con alertas',
    'alerts.view': 'Ver →',

    'ledger.suppliers': 'Proveedores',
    'ledger.suppliersSub': 'A quién le pagamos · click para ver sus facturas',
    'ledger.clients': 'Clientes',
    'ledger.clientsSub': 'Quién nos paga · click para ver sus facturas',
    'ledger.idName': 'ID / Nombre',
    'ledger.mainCategory': 'Rubro principal',
    'ledger.invoices': 'Facturas',
    'ledger.alerts': 'Alertas',
    'ledger.total': 'Total',
    'ledger.uploaded': 'subida',
    'ledger.alert': 'alerta',

    'lang.switch': 'English',
    'brand.subtitle': 'Gestión contable',
  },
}

// Planes de precios (bilingües), tomados del pricing de ZIRA.
export const PLANS = [
  {
    key: 'free',
    name: 'Free',
    price: '$0',
    highlight: false,
    accent: 'text-slate-300',
    en: {
      tagline: 'To get started', cta: 'Current plan',
      features: ['Up to 20 receipts / month', '1 user', 'QVAC on-device', 'Basic inconsistency detection', 'Manual CSV export', 'Community support'],
    },
    es: {
      tagline: 'Para empezar', cta: 'Plan actual',
      features: ['Hasta 20 comprobantes / mes', '1 usuario', 'QVAC en el dispositivo', 'Detección básica de inconsistencias', 'Exportación manual a CSV', 'Soporte comunidad'],
    },
  },
  {
    key: 'pro',
    name: 'Pro',
    price: 'USD 9',
    highlight: true,
    accent: 'text-brand-glow',
    en: {
      tagline: 'Most popular', cta: 'Choose Pro',
      features: ['Unlimited receipts', '1 user', 'QVAC on-device', 'Full detection + automatic alerts', 'Auto export to Sheets / Excel', 'Email support (48 h)'],
    },
    es: {
      tagline: 'Más elegido', cta: 'Elegir Pro',
      features: ['Comprobantes ilimitados', '1 usuario', 'QVAC en el dispositivo', 'Detección completa + alertas automáticas', 'Exportación automática a Sheets / Excel', 'Soporte por email (48 h)'],
    },
  },
  {
    key: 'business',
    name: 'Business',
    price: 'USD 19',
    highlight: false,
    accent: 'text-violet-400',
    en: {
      tagline: 'Up to 5 users', cta: 'Choose Business',
      features: ['Unlimited receipts', 'Up to 5 users', 'QVAC on client\'s own server', 'Full + audit dashboard', 'Auto export to local Excel', 'Priority support (24 h)'],
    },
    es: {
      tagline: 'Hasta 5 usuarios', cta: 'Elegir Business',
      features: ['Comprobantes ilimitados', 'Hasta 5 usuarios', 'QVAC en el servidor del cliente', 'Completo + panel de auditoría', 'Exportación automática a Excel local', 'Soporte prioritario (24 h)'],
    },
  },
  {
    key: 'enterprise',
    name: 'Enterprise',
    price: 'Custom',
    highlight: false,
    accent: 'text-amber-400',
    en: {
      tagline: 'Dedicated', cta: 'Contact sales',
      features: ['Unlimited receipts & users', 'QVAC dedicated on-premise', 'Full + custom rules', 'Direct ERP / SAP integration', 'Data never leaves your environment', 'Dedicated SLA + onboarding'],
    },
    es: {
      tagline: 'Dedicado', cta: 'Contactar ventas',
      features: ['Comprobantes y usuarios ilimitados', 'QVAC dedicado on-premise', 'Completo + reglas a medida', 'Integración directa ERP / SAP', 'Los datos nunca salen de tu entorno', 'SLA dedicado + onboarding'],
    },
  },
]

// Rubros por category_key (el backend clasifica; el frontend traduce la etiqueta).
const CATEGORY_LABELS = {
  en: {
    transporte: 'Transport', comida: 'Food & Delivery', combustible: 'Fuel',
    servicios: 'Utilities (power/gas/water)', logistica: 'Logistics & Shipping',
    pagos: 'Transfers & Payments', impuestos: 'Taxes', insumos: 'Supplies & Office',
    mercaderia: 'Merchandise', profesionales: 'Professional Services',
    equipamiento: 'Equipment', otros: 'Other',
  },
  es: {
    transporte: 'Transporte', comida: 'Comida y Delivery', combustible: 'Combustible',
    servicios: 'Servicios (luz/gas/agua)', logistica: 'Logística y Envíos',
    pagos: 'Transferencias y Pagos', impuestos: 'Impuestos', insumos: 'Insumos y Oficina',
    mercaderia: 'Mercadería', profesionales: 'Servicios Profesionales',
    equipamiento: 'Equipamiento', otros: 'Otros',
  },
}

// Formatea el monto como el backend (es-AR) para los mensajes de alerta.
const fmtMoney = (n) => '$ ' + Number(n).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

// Arma el texto de una alerta según su tipo y parámetros, en el idioma activo.
function alertText(lang, type, p = {}) {
  const en = {
    incomplete: 'Incomplete data: review the uploaded document reading.',
    total: `Total doesn't add up: net ${fmtMoney(p.net)} + VAT ${fmtMoney(p.iva)} = ${fmtMoney(p.sum)}, but the document says ${fmtMoney(p.amount)}.`,
    iva: `Inconsistent VAT: shows ${fmtMoney(p.iva)} but 21% of ${fmtMoney(p.net)} is ${fmtMoney(p.expected)}.`,
    duplicate: `Possible duplicate of ${p.of} (same counterparty and amount).`,
  }
  const es = {
    incomplete: 'Datos incompletos: revisar la lectura del comprobante subido.',
    total: `El total no cuadra: neto ${fmtMoney(p.net)} + IVA ${fmtMoney(p.iva)} = ${fmtMoney(p.sum)}, pero el comprobante dice ${fmtMoney(p.amount)}.`,
    iva: `IVA inconsistente: figura ${fmtMoney(p.iva)} pero el 21% de ${fmtMoney(p.net)} es ${fmtMoney(p.expected)}.`,
    duplicate: `Posible duplicado de ${p.of} (misma contraparte y monto).`,
  }
  return (lang === 'en' ? en : es)[type] || ''
}

const LangContext = createContext(null)

export function LanguageProvider({ children }) {
  const [lang, setLang] = useState('en')
  const t = useCallback((key) => STRINGS[lang][key] ?? STRINGS.en[key] ?? key, [lang])
  const toggle = useCallback(() => setLang((l) => (l === 'en' ? 'es' : 'en')), [])
  // Traduce un rubro por su category_key; usa el label del backend como respaldo.
  const cat = useCallback(
    (key, fallback) => CATEGORY_LABELS[lang][key] ?? fallback ?? CATEGORY_LABELS.en[key] ?? key,
    [lang],
  )
  // Arma el texto de una alerta en el idioma activo.
  const alert = useCallback((type, params) => alertText(lang, type, params), [lang])
  return (
    <LangContext.Provider value={{ lang, t, cat, alert, toggle }}>
      {children}
    </LangContext.Provider>
  )
}

export function useT() {
  const ctx = useContext(LangContext)
  if (!ctx) throw new Error('useT must be used within LanguageProvider')
  return ctx
}
