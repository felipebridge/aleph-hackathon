"""Agrega los datos crudos del pipeline en las vistas del dashboard de Zira.

Dos consumidores:
  - El DUEÑO ve rendimiento: ingresos, egresos, ganancia y en qué rubros se
    va la plata (owner_dashboard).
  - El CONTADOR ve el libro mayor: cada proveedor y cliente con un ID estable,
    cuánto se facturó vs cuánto se pagó/cobró, y si hay diferencias
    (provider_ledger / client_ledger).

Todo se calcula sobre los mismos objetos del pipeline (Receipt, DataFrame del
banco), sin tocar la lógica de matching.
"""

from __future__ import annotations

import hashlib

import pandas as pd

from .categories import categorize, category_breakdown
from .matcher import _normalize_merchant_name
from .models import DiscrepancyType, ReconciliationResult


def _stable_id(prefix: str, name: str) -> str:
    """ID corto y determinístico por nombre normalizado (mismo nombre -> mismo ID)."""
    digest = hashlib.sha1(_normalize_merchant_name(name).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:6].upper()}"


def owner_dashboard(income_df: pd.DataFrame, expense_df: pd.DataFrame) -> dict:
    """KPIs de rendimiento + desglose de egresos por rubro, para el dueño."""
    total_income = float(income_df["amount"].sum()) if not income_df.empty else 0.0
    total_expense = float(expense_df["amount"].sum()) if not expense_df.empty else 0.0
    profit = total_income - total_expense

    breakdown = category_breakdown(
        [(row.merchant, row.amount) for row in expense_df.itertuples(index=False)]
    )

    # Serie temporal simple (por día) para un mini-gráfico de flujo.
    flow = _daily_flow(income_df, expense_df)

    return {
        "kpis": {
            "income": round(total_income, 2),
            "expense": round(total_expense, 2),
            "profit": round(profit, 2),
            "margin_pct": round(profit / total_income * 100, 1) if total_income else 0.0,
        },
        "expense_breakdown": breakdown,
        "daily_flow": flow,
        "top_expense": breakdown[0] if breakdown else None,
    }


def _daily_flow(income_df: pd.DataFrame, expense_df: pd.DataFrame) -> list[dict]:
    inc = income_df.groupby("date")["amount"].sum() if not income_df.empty else pd.Series(dtype=float)
    exp = expense_df.groupby("date")["amount"].sum() if not expense_df.empty else pd.Series(dtype=float)
    all_dates = sorted(set(inc.index) | set(exp.index))
    return [
        {
            "date": str(d),
            "income": round(float(inc.get(d, 0.0)), 2),
            "expense": round(float(exp.get(d, 0.0)), 2),
        }
        for d in all_dates
    ]


def provider_ledger(result: ReconciliationResult) -> list[dict]:
    """Libro mayor de proveedores, construido sobre el resultado de la
    reconciliación (que ya resolvió el matching difuso de nombres).

    Agrupa por el nombre canónico del proveedor (el del banco cuando existe,
    si no el del recibo). Para cada proveedor:
      - facturado: suma de montos de los comprobantes
      - pagado:    suma de cargos del banco
      - saldo:     pagado - facturado
      - estado:    ok | diferencia | sin_comprobante | pendiente_pago | duplicado
    """
    agg: dict[str, dict] = {}

    def _bucket(name: str) -> dict:
        norm = _normalize_merchant_name(name or "")
        if norm not in agg:
            cat = categorize(name)
            agg[norm] = {
                "id": _stable_id("PROV", name or "desconocido"),
                "name": name or "Desconocido",
                "category": cat.label,
                "category_key": cat.key,
                "category_color": cat.color,
                "invoiced": 0.0,
                "paid": 0.0,
                "receipts": 0,
                "charges": 0,
                "estados": set(),
            }
        return agg[norm]

    # Matches limpios: comercio canónico = el del banco. Facturado y pagado ok.
    for m in result.matched:
        b = _bucket(m.bank_txn.merchant)
        b["invoiced"] += m.receipt.amount or 0.0
        b["paid"] += m.bank_txn.amount
        b["receipts"] += 1
        b["charges"] += 1
        b["estados"].add("ok")

    for d in result.discrepancies:
        if d.type is DiscrepancyType.AMOUNT_MISMATCH and d.bank_txn and d.receipt:
            b = _bucket(d.bank_txn.merchant)
            b["invoiced"] += d.receipt.amount or 0.0
            b["paid"] += d.bank_txn.amount
            b["receipts"] += 1
            b["charges"] += 1
            b["estados"].add("diferencia")
        elif d.type is DiscrepancyType.UNACCOUNTED_CHARGE and d.bank_txn:
            b = _bucket(d.bank_txn.merchant)
            b["paid"] += d.bank_txn.amount
            b["charges"] += 1
            b["estados"].add("sin_comprobante")
        elif d.type is DiscrepancyType.MISSING_IN_BANK and d.receipt:
            b = _bucket(d.receipt.merchant or "Desconocido")
            b["invoiced"] += d.receipt.amount or 0.0
            b["receipts"] += 1
            b["estados"].add("pendiente_pago")
        elif d.type is DiscrepancyType.DUPLICATE_RECEIPT and d.receipt:
            b = _bucket(d.receipt.merchant or "Desconocido")
            b["invoiced"] += d.receipt.amount or 0.0
            b["receipts"] += 1
            b["estados"].add("duplicado")

    # Prioridad de estado cuando un proveedor tiene varios movimientos.
    priority = ["diferencia", "sin_comprobante", "pendiente_pago", "duplicado", "ok"]

    ledger = []
    for b in agg.values():
        estados = b.pop("estados")
        estado = next((e for e in priority if e in estados), "ok")
        ledger.append({
            **b,
            "invoiced": round(b["invoiced"], 2),
            "paid": round(b["paid"], 2),
            "balance": round(b["paid"] - b["invoiced"], 2),
            "estado": estado,
        })

    ledger.sort(key=lambda d: d["paid"] + d["invoiced"], reverse=True)
    return ledger


def client_ledger(income_df: pd.DataFrame) -> list[dict]:
    """Libro mayor de clientes: cuánto nos cobró cada uno, con ID estable."""
    if income_df.empty:
        return []
    ledger = []
    for name, group in income_df.groupby("client"):
        ledger.append({
            "id": _stable_id("CLI", str(name)),
            "name": str(name),
            "collected": round(float(group["amount"].sum()), 2),
            "invoices": int(len(group)),
        })
    ledger.sort(key=lambda d: d["collected"], reverse=True)
    return ledger
