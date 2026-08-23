"""Contenedor único de facturas de ZIRA + vistas de dueño y contador.

Una sola fuente de verdad: cada comprobante (del dataset de movimientos y cada
factura que sube el contador) se guarda como una "factura" con la misma forma.
De ahí salen tanto el dashboard del dueño (ingresos/egresos/ganancia y rubros)
como el libro mayor del contador (proveedores y clientes con sus facturas), así
lo que se sube en el área contable se refleja al instante en ambos lados.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .categories import CATEGORIES, categorize, category_breakdown
from .matcher import _normalize_merchant_name
from .movements import load_movements

# Contenedor persistente de las facturas subidas por el contador (una por línea).
UPLOAD_STORE = Path("data/uploaded_invoices.jsonl")
MOVEMENTS_CSV = "data/movimientos_zira.csv"


def _stable_id(prefix: str, name: str) -> str:
    digest = hashlib.sha1(_normalize_merchant_name(name).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:6].upper()}"


# --- Carga de facturas ----------------------------------------------------


def _movement_to_invoice(m) -> dict:
    cat = categorize(m.concept, m.counterparty)
    return {
        "id": m.id,
        "direction": m.direction,
        "date": m.date.isoformat() if m.date else None,
        "counterparty": m.counterparty,
        "counterparty_cuit": m.counterparty_cuit,
        "concept": m.concept,
        "category": cat.label,
        "category_key": cat.key,
        "category_color": cat.color,
        "amount": round(m.amount, 2),
        "net": round(m.net, 2),
        "iva": round(m.iva, 2),
        "source": "dataset",
    }


def dataset_invoices(csv_path: str = MOVEMENTS_CSV) -> list[dict]:
    if not Path(csv_path).exists():
        return []
    return [_movement_to_invoice(m) for m in load_movements(csv_path)]


def uploaded_invoices() -> list[dict]:
    if not UPLOAD_STORE.exists():
        return []
    out = []
    with UPLOAD_STORE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def append_uploaded(invoice: dict) -> None:
    UPLOAD_STORE.parent.mkdir(parents=True, exist_ok=True)
    with UPLOAD_STORE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(invoice, ensure_ascii=False) + "\n")


def all_invoices(csv_path: str = MOVEMENTS_CSV) -> list[dict]:
    """Dataset + facturas subidas, con alertas ya calculadas."""
    invoices = dataset_invoices(csv_path) + uploaded_invoices()
    _annotate_alerts(invoices)
    return invoices


# --- Detección de alertas por factura -------------------------------------


def _annotate_alerts(invoices: list[dict]) -> None:
    """Marca cada factura con status ok|alerta y el motivo (para navegar a ella).

    Detecta anomalías contables típicas que el contador debe revisar:
    duplicados, IVA que no da el 21%, y comprobantes donde el total no cuadra
    con neto + IVA (error de facturación).
    """
    # Para duplicados: agrupamos por (contraparte, monto) y recordamos las fechas
    # ya vistas; sólo es duplicado si las fechas están cerca (mismo cobro repetido),
    # no un cargo recurrente legítimo de meses distintos.
    seen: dict[tuple, list[tuple[str, str]]] = {}
    for inv in invoices:
        alert_type = None
        params: dict = {}
        severity = "media"
        amount = inv.get("amount", 0) or 0
        iva = inv.get("iva", 0) or 0
        net = inv.get("net")
        if net is None:
            net = round(amount - iva, 2)

        # 1) OCR incompleto en una factura subida.
        if inv.get("source") == "upload" and not inv.get("fully_parsed", True):
            alert_type, severity = "incomplete", "media"

        # 2) El total no cuadra: neto + IVA debería dar el total.
        if not alert_type and net > 0:
            suma = round(net + iva, 2)
            if abs(suma - amount) > max(1.0, amount * 0.005):
                alert_type, severity = "total", "alta"
                params = {"net": net, "iva": iva, "sum": suma, "amount": amount}

        # 3) IVA que no es el 21% del neto.
        if not alert_type and net > 0 and iva > 0:
            expected = round(net * 0.21, 2)
            if abs(iva - expected) > max(1.0, expected * 0.05):
                alert_type, severity = "iva", "alta"
                params = {"iva": iva, "net": net, "expected": expected}

        # 4) Posible duplicado: misma contraparte + mismo monto + fechas cercanas
        # (<= 10 días). Los cargos recurrentes de meses distintos NO se marcan.
        key = (_normalize_merchant_name(inv.get("counterparty") or ""), round(amount, 2))
        inv_date = inv.get("date")
        if not alert_type and key in seen:
            for prev_id, prev_date in seen[key]:
                if _days_between(inv_date, prev_date) <= 10:
                    alert_type, severity = "duplicate", "alta"
                    params = {"of": prev_id}
                    break
        seen.setdefault(key, []).append((inv["id"], inv_date))

        inv["status"] = "alerta" if alert_type else "ok"
        inv["alert_type"] = alert_type
        inv["alert_params"] = params
        inv["alert"] = _alert_text_es(alert_type, params)  # fallback en español
        inv["alert_severity"] = severity if alert_type else None


def _days_between(a: str | None, b: str | None) -> int:
    """Días absolutos entre dos fechas ISO; grande si falta alguna."""
    if not a or not b:
        return 9999
    from datetime import date
    try:
        return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)
    except ValueError:
        return 9999


def _alert_text_es(alert_type: str | None, p: dict) -> str | None:
    """Texto en español (fallback; el frontend arma el texto según idioma)."""
    if alert_type == "incomplete":
        return "Datos incompletos: revisar la lectura del comprobante subido."
    if alert_type == "total":
        return (f"El total no cuadra: neto ${p['net']:,.2f} + IVA ${p['iva']:,.2f} = "
                f"${p['sum']:,.2f}, pero el comprobante dice ${p['amount']:,.2f}.")
    if alert_type == "iva":
        return (f"IVA inconsistente: figura ${p['iva']:,.2f} pero el 21% de "
                f"${p['net']:,.2f} es ${p['expected']:,.2f}.")
    if alert_type == "duplicate":
        return f"Posible duplicado de {p['of']} (misma contraparte y monto)."
    return None


# --- Vista del DUEÑO ------------------------------------------------------


def owner_dashboard(csv_path: str = MOVEMENTS_CSV) -> dict:
    invoices = all_invoices(csv_path)
    income = sum(i["amount"] for i in invoices if i["direction"] == "ingreso")
    expense = sum(i["amount"] for i in invoices if i["direction"] == "egreso")
    profit = income - expense

    expense_breakdown = category_breakdown(
        [(f"{i['concept']} {i['counterparty']}", i["amount"])
         for i in invoices if i["direction"] == "egreso"]
    )
    income_breakdown = category_breakdown(
        [(f"{i['concept']} {i['counterparty']}", i["amount"])
         for i in invoices if i["direction"] == "ingreso"]
    )

    # Flujo mensual (más legible que diario cuando las fechas están dispersas).
    monthly: dict[str, dict] = {}
    for i in invoices:
        month = (i["date"] or "s/f")[:7]
        d = monthly.setdefault(month, {"month": month, "income": 0.0, "expense": 0.0})
        bucket = "income" if i["direction"] == "ingreso" else "expense"
        d[bucket] = round(d[bucket] + i["amount"], 2)
    monthly_flow = [monthly[k] for k in sorted(monthly)]

    return {
        "kpis": {
            "income": round(income, 2),
            "expense": round(expense, 2),
            "profit": round(profit, 2),
            "margin_pct": round(profit / income * 100, 1) if income else 0.0,
            "count_income": sum(1 for i in invoices if i["direction"] == "ingreso"),
            "count_expense": sum(1 for i in invoices if i["direction"] == "egreso"),
        },
        "expense_breakdown": expense_breakdown,
        "income_breakdown": income_breakdown,
        "monthly_flow": monthly_flow,
        "top_expense": expense_breakdown[0] if expense_breakdown else None,
        "top_income": income_breakdown[0] if income_breakdown else None,
        "movements": sorted(invoices, key=lambda i: i.get("date") or "", reverse=True),
    }


# --- Vista del CONTADOR ---------------------------------------------------


def _party_group(invoices: list[dict], direction: str, prefix: str) -> list[dict]:
    groups: dict[str, dict] = {}
    for inv in invoices:
        if inv["direction"] != direction:
            continue
        norm = _normalize_merchant_name(inv.get("counterparty") or "")
        g = groups.setdefault(norm, {
            "id": _stable_id(prefix, inv.get("counterparty") or "s/d"),
            "name": inv.get("counterparty") or "Desconocido",
            "total": 0.0,
            "invoices": [],
            "alerts": 0,
        })
        g["total"] = round(g["total"] + inv["amount"], 2)
        g["invoices"].append(inv)
        if inv.get("status") == "alerta":
            g["alerts"] += 1
    result = list(groups.values())
    for g in result:
        g["count"] = len(g["invoices"])
        # rubro dominante del grupo (por monto), guardando también su key
        cats: dict[tuple, float] = {}
        for inv in g["invoices"]:
            ck = (inv["category"], inv.get("category_key", "otros"))
            cats[ck] = cats.get(ck, 0) + inv["amount"]
        if cats:
            (label, key), _ = max(cats.items(), key=lambda kv: kv[1])
        else:
            label, key = "Otros", "otros"
        g["top_category"] = label
        g["top_category_key"] = key
    result.sort(key=lambda g: g["total"], reverse=True)
    return result


def accountant_ledger(csv_path: str = MOVEMENTS_CSV) -> dict:
    invoices = all_invoices(csv_path)
    providers = _party_group(invoices, "egreso", "PROV")
    clients = _party_group(invoices, "ingreso", "CLI")
    alerts = [i for i in invoices if i.get("status") == "alerta"]
    return {
        "providers": providers,
        "clients": clients,
        "alerts": alerts,
        "totals": {
            "invoices": len(invoices),
            "providers": len(providers),
            "clients": len(clients),
            "alerts": len(alerts),
        },
    }
