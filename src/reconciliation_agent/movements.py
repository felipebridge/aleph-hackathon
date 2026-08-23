"""Detección ingreso/egreso según el rol de ZIRA en cada comprobante.

Regla contable (facturas): el EMISOR es quien vende / factura.
  - ZIRA es EMISOR  -> ZIRA facturó una venta            -> INGRESO
  - ZIRA es RECEPTOR-> a ZIRA le facturaron una compra   -> EGRESO

Se identifica a ZIRA por nombre normalizado o por su CUIT. Esto vale tanto
para el dataset de movimientos como para un comprobante suelto que sube el
contador (donde ZIRA casi siempre es el receptor/consumidor -> egreso).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import pandas as pd

# Identidad de la empresa. El CUIT es la señal más confiable; el nombre es un
# respaldo por si el OCR no capta el CUIT.
ZIRA_CUIT = "30-71111111-4"
# "zira" como subcadena: el OCR a veces junta "ZIRA SA" en "ZIRASA".
_ZIRA_NAME_RE = re.compile(r"zira", re.IGNORECASE)
_CUIT_DIGITS_RE = re.compile(r"\d")


def _cuit_digits(value: str | None) -> str:
    return "".join(_CUIT_DIGITS_RE.findall(value or ""))


_ZIRA_CUIT_DIGITS = _cuit_digits(ZIRA_CUIT)


def is_zira(name: str | None = None, cuit: str | None = None) -> bool:
    """True si el nombre o el CUIT corresponden a ZIRA."""
    if cuit and _cuit_digits(cuit) == _ZIRA_CUIT_DIGITS:
        return True
    if name and _ZIRA_NAME_RE.search(name):
        return True
    return False


def classify_direction(
    emisor: str | None,
    receptor: str | None,
    emisor_cuit: str | None = None,
    receptor_cuit: str | None = None,
) -> str:
    """Devuelve 'ingreso' | 'egreso' | 'desconocido' según el rol de ZIRA."""
    zira_emisor = is_zira(emisor, emisor_cuit)
    zira_receptor = is_zira(receptor, receptor_cuit)
    if zira_emisor and not zira_receptor:
        return "ingreso"
    if zira_receptor and not zira_emisor:
        return "egreso"
    # Si ZIRA no aparece claramente en ningún lado, asumimos que un comprobante
    # que cae en el buzón del contador es un gasto de la empresa.
    return "egreso" if (emisor or receptor) else "desconocido"


_CUIT_RE = re.compile(r"\b(\d{2}-?\d{8}-?\d)\b")
# Nombres de razón social: terminan en una forma societaria típica argentina.
_COMPANY_RE = re.compile(
    r"([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚáéíóúÑñ&\.\s]{2,40}?\s(?:S\.?R\.?L\.?|S\.?A\.?S?\.?|SRL|SA|SAS))\b"
)


def _extract_counterparty(text: str) -> str | None:
    """Primer nombre de razón social del texto que no sea ZIRA."""
    for match in _COMPANY_RE.finditer(text or ""):
        name = re.sub(r"\s+", " ", match.group(1)).strip()
        if not is_zira(name):
            return name
    return None


def detect_from_text(text: str, fallback_merchant: str | None = None) -> dict:
    """Deduce ingreso/egreso y la contraparte a partir del texto OCR crudo.

    En una factura AFIP hay dos CUIT: el del EMISOR aparece primero (arriba) y
    el del RECEPTOR después. Si el CUIT de ZIRA es el primero, ZIRA emitió la
    factura (venta -> ingreso); si aparece después, a ZIRA le facturaron
    (compra -> egreso). Si el CUIT no se lee, se cae a la posición del nombre.
    Sin ZIRA a la vista, se asume egreso (un comprobante en el buzón del
    contador es, por defecto, un gasto).
    """
    cuits = _CUIT_RE.findall(text or "")
    cuit_digits = [_cuit_digits(c) for c in cuits]
    zira_by_cuit = _ZIRA_CUIT_DIGITS in cuit_digits
    zira_positions = [m.start() for m in _ZIRA_NAME_RE.finditer(text or "")]
    zira_present = bool(zira_positions) or zira_by_cuit

    direction, confidence = "egreso", "media"

    if zira_by_cuit:
        # Señal fuerte: el orden de los CUIT define quién es emisor/receptor.
        idx = cuit_digits.index(_ZIRA_CUIT_DIGITS)
        direction = "ingreso" if idx == 0 else "egreso"
        confidence = "alta"
    elif zira_positions:
        # Respaldo: posición del nombre (emisor arriba, receptor abajo).
        half = len(text) / 2 if text else 1
        direction = "ingreso" if zira_positions[0] <= half else "egreso"
        confidence = "media"

    counterparty = _extract_counterparty(text)
    if not counterparty:
        counterparty = None if (fallback_merchant and is_zira(fallback_merchant)) else fallback_merchant

    return {
        "direction": direction,
        "confidence": confidence,
        "zira_detected": zira_present,
        "counterparty": counterparty,
        "cuits_found": cuits,
    }


@dataclass(frozen=True)
class Movement:
    id: str
    direction: str            # ingreso | egreso
    detected_direction: str   # lo que dedujo el agente (para auditar)
    date: date | None
    counterparty: str         # la contraparte (el que no es ZIRA)
    counterparty_cuit: str
    concept: str
    amount: float
    net: float
    iva: float


def _parse_date(value) -> date | None:
    try:
        return pd.to_datetime(value, dayfirst=True, errors="coerce").date()
    except (ValueError, TypeError):
        return None


def load_movements(csv_path: str) -> list[Movement]:
    """Carga el CSV de movimientos de ZIRA y clasifica cada fila con el agente."""
    df = pd.read_csv(csv_path)
    df.columns = [c.strip().lower() for c in df.columns]

    movements: list[Movement] = []
    for row in df.itertuples(index=False):
        emisor = getattr(row, "emisor", "")
        receptor = getattr(row, "receptor", "")
        emisor_cuit = str(getattr(row, "cuit_emisor", "") or "")
        receptor_cuit = str(getattr(row, "cuit_receptor", "") or "")

        detected = classify_direction(emisor, receptor, emisor_cuit, receptor_cuit)
        # La contraparte es quien NO es ZIRA.
        if is_zira(emisor, emisor_cuit):
            counterparty, cp_cuit = receptor, receptor_cuit
        else:
            counterparty, cp_cuit = emisor, emisor_cuit

        movements.append(Movement(
            id=str(getattr(row, "id_transaccion", "")),
            direction=detected,
            detected_direction=detected,
            date=_parse_date(getattr(row, "fecha_emision", None)),
            counterparty=str(counterparty),
            counterparty_cuit=str(cp_cuit),
            concept=str(getattr(row, "concepto", "")),
            amount=float(getattr(row, "monto_total", 0) or 0),
            net=float(getattr(row, "monto_neto", 0) or 0),
            iva=float(getattr(row, "iva", 0) or 0),
        ))
    return movements


def summarize(movements: list[Movement]) -> dict:
    """Totales ingreso/egreso/ganancia listos para el dashboard del dueño."""
    income = sum(m.amount for m in movements if m.direction == "ingreso")
    expense = sum(m.amount for m in movements if m.direction == "egreso")
    profit = income - expense
    return {
        "income": round(income, 2),
        "expense": round(expense, 2),
        "profit": round(profit, 2),
        "margin_pct": round(profit / income * 100, 1) if income else 0.0,
        "count_income": sum(1 for m in movements if m.direction == "ingreso"),
        "count_expense": sum(1 for m in movements if m.direction == "egreso"),
    }


def zira_dashboard(csv_path: str) -> dict:
    """Dashboard completo del dueño a partir del dataset de movimientos de ZIRA.

    El agente clasifica cada comprobante en ingreso/egreso (por el rol de ZIRA)
    y arma: KPIs (ingresos/egresos/ganancia), egresos por rubro, flujo diario y
    detalle de movimientos.
    """
    from .categories import category_breakdown

    mv = load_movements(csv_path)
    kpis = summarize(mv)

    # Egresos por rubro: categorizamos por concepto + contraparte.
    expense_items = [
        (f"{m.concept} {m.counterparty}", m.amount) for m in mv if m.direction == "egreso"
    ]
    breakdown = category_breakdown(expense_items)

    # Flujo diario ingreso/egreso.
    daily: dict[str, dict] = {}
    for m in mv:
        key = m.date.isoformat() if m.date else "s/f"
        d = daily.setdefault(key, {"date": key, "income": 0.0, "expense": 0.0})
        d[m.direction] = round(d.get(m.direction, 0.0) + m.amount, 2)
    daily_flow = [daily[k] for k in sorted(daily)]

    detail = [
        {
            "id": m.id,
            "direction": m.direction,
            "date": m.date.isoformat() if m.date else None,
            "counterparty": m.counterparty,
            "counterparty_cuit": m.counterparty_cuit,
            "concept": m.concept,
            "amount": m.amount,
            "iva": m.iva,
        }
        for m in mv
    ]

    return {
        "kpis": kpis,
        "expense_breakdown": breakdown,
        "daily_flow": daily_flow,
        "top_expense": breakdown[0] if breakdown else None,
        "movements": detail,
    }
