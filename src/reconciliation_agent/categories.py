"""Clasificación de comercios en rubros de gasto para el dashboard de Zira.

Mapea el nombre del comercio (del recibo o del extracto bancario) a una
categoría de negocio -- Uber -> Transporte, PedidosYa -> Comida, etc. -- para
poder mostrar en qué rubros se va el dinero de la PyME. La detección es por
palabras clave sobre el nombre normalizado; conservadora y fácil de extender.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    color: str  # hex, usado por el donut del frontend


# Paleta alineada con el dashboard (tonos vivos sobre fondo oscuro).
CATEGORIES: dict[str, Category] = {
    "transporte": Category("transporte", "Transporte", "#8b5cf6"),
    "comida": Category("comida", "Comida y Delivery", "#f472b6"),
    "combustible": Category("combustible", "Combustible", "#f59e0b"),
    "servicios": Category("servicios", "Servicios (luz/gas/agua)", "#22d3ee"),
    "logistica": Category("logistica", "Logística y Envíos", "#34d399"),
    "pagos": Category("pagos", "Transferencias y Pagos", "#60a5fa"),
    "impuestos": Category("impuestos", "Impuestos", "#fb7185"),
    # Rubros B2B (para los movimientos de facturas de ZIRA).
    "insumos": Category("insumos", "Insumos y Oficina", "#a3e635"),
    "mercaderia": Category("mercaderia", "Mercadería", "#fbbf24"),
    "profesionales": Category("profesionales", "Servicios Profesionales", "#38bdf8"),
    "equipamiento": Category("equipamiento", "Equipamiento", "#c084fc"),
    "otros": Category("otros", "Otros", "#94a3b8"),
}

# Palabras clave por rubro. Se evalúan en orden; el primero que matchea gana.
# Se aplican tanto al nombre del comercio como al concepto del comprobante.
_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("transporte", ("uber", "cabify", "didi", "beat", "remis", "taxi", "sube")),
    ("comida", ("rappi", "pedidosya", "pedidos ya", "peya", "mcdonald", "burger",
                "restaurant", "cafe", "starbucks", "delivery", "kiosco")),
    ("combustible", ("petrosur", "shell", "ypf", "axion", "puma", "nafta", "gnc",
                     "combustible", "estacion")),
    ("equipamiento", ("equipamiento", "informatico", "informática", "hardware",
                      "notebook", "computadora", "servidor")),
    ("insumos", ("insumo", "oficina", "papeleria", "librería", "libreria")),
    ("mercaderia", ("mercaderia", "materia prima", "reventa", "stock")),
    ("profesionales", ("profesional", "consultoria", "consultoría", "honorario",
                       "desarrollo", "software", "soporte", "mantenimiento",
                       "capacitacion", "capacitación", "asesor", "legal", "contable")),
    ("servicios", ("luzsur", "edenor", "edesur", "metrogas", "aysa", "camuzzi",
                   "naturgy", "electricidad", "gas", "agua", "telecom", "movistar",
                   "claro", "personal", "fibertel", "internet")),
    ("logistica", ("courier", "correo", "oca", "andreani", "envio", "envío",
                   "flete", "encomienda", "dhl", "fedex", "logistica", "logística")),
    ("impuestos", ("afip", "arba", "agip", "rentas", "impuesto", "iibb", "monotributo",
                   "tasa", "municipal")),
    ("pagos", ("transferencia", "mercado pago", "mercadopago", "brubank", "uala",
               "ualá", "cvu", "cbu", "pago")),
]

_NORMALIZE_RE = re.compile(r"[^a-z0-9 ]")


def _normalize(name: str) -> str:
    lowered = name.lower()
    # Reemplazos de acentos comunes para que "envío" matchee "envio".
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u")):
        lowered = lowered.replace(a, b)
    return _NORMALIZE_RE.sub(" ", lowered).strip()


def categorize(*texts: str | None) -> Category:
    """Devuelve el rubro a partir de uno o más textos (comercio y/o concepto).

    Evalúa las palabras clave sobre todos los textos concatenados; el primer
    rubro que matchea gana. Cae en 'otros' si no reconoce nada.
    """
    joined = _normalize(" ".join(t for t in texts if t))
    if not joined:
        return CATEGORIES["otros"]
    for key, words in _KEYWORDS:
        if any(_normalize(w) in joined for w in words):
            return CATEGORIES[key]
    return CATEGORIES["otros"]


def category_breakdown(items: list[tuple[str | None, float]]) -> list[dict]:
    """Agrupa (comercio, monto) por rubro y devuelve totales + porcentajes.

    Ordenado de mayor a menor gasto, listo para el donut del dashboard.
    """
    totals: dict[str, float] = {}
    for merchant, amount in items:
        cat = categorize(merchant)
        totals[cat.key] = totals.get(cat.key, 0.0) + (amount or 0.0)

    grand_total = sum(totals.values()) or 1.0
    breakdown = [
        {
            "key": key,
            "label": CATEGORIES[key].label,
            "color": CATEGORIES[key].color,
            "amount": round(total, 2),
            "percent": round(total / grand_total * 100, 1),
        }
        for key, total in totals.items()
    ]
    breakdown.sort(key=lambda d: d["amount"], reverse=True)
    return breakdown
