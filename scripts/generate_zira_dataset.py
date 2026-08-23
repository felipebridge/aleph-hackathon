#!/usr/bin/env python
"""Genera un dataset de movimientos de ZIRA realista y balanceado por mes.

Cada mes (ene-jul 2026) tiene ingresos Y egresos en proporciones creíbles de
una PyME sana: la mayoría de los meses con ganancia, uno con pérdida (marzo),
márgenes variables. Incluye 3 anomalías contables intencionales para que el
contador las detecte:
  - duplicado de una factura de proveedor
  - IVA que no da el 21%
  - total que no cuadra con neto + IVA

Uso: python scripts/generate_zira_dataset.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "movimientos_zira.csv"

ZIRA = ("ZIRA SA", "30-71111111-4", "901-123456-7")

# Contrapartes (razón social, CUIT, ingresos brutos).
CLIENTES = [
    ("Norte Insumos SRL", "30-70222222-5", "909-407419-9"),
    ("Delta Logistica SA", "30-70333333-6", "904-910620-4"),
    ("Manantial Servicios SRL", "30-70444444-7", "902-114455-2"),
    ("Vertice Comercial SA", "30-70555555-8", "901-778899-3"),
    ("Horizonte Distribuciones SRL", "30-70666666-9", "905-223344-1"),
    ("Pampa Soluciones SA", "30-70777777-0", "903-556677-4"),
    ("Austral Provisiones SRL", "30-70888888-1", "906-889900-5"),
]

CONCEPTOS_INGRESO = [
    "Servicio de consultoria mensual", "Venta de mercaderia - lote A",
    "Honorarios por desarrollo de software", "Servicio de mantenimiento tecnico",
    "Alquiler de equipamiento", "Venta de mercaderia - lote B",
    "Servicio de capacitacion corporativa", "Comision por intermediacion comercial",
    "Servicio de soporte tecnico anual", "Venta de licencias de software",
]
CONCEPTOS_EGRESO = [
    "Compra de insumos de oficina", "Pago de servicios de logistica",
    "Compra de materia prima", "Pago de servicios profesionales",
    "Compra de equipamiento informatico", "Pago de fletes y transporte",
    "Compra de mercaderia para reventa",
]

# Plan mensual: (mes, [ingresos en total $], [egresos en total $]).
# Diseñado para que se vea realista: ingresos > egresos casi siempre, marzo con
# pérdida, y márgenes que varían mes a mes.
PLAN = {
    1:  ([320000, 285000, 240000], [210000, 175000, 140000]),   # +320k
    2:  ([410000, 295000, 215000], [230000, 190000, 165000]),   # +335k
    3:  ([260000, 210000, 190000], [280000, 245000, 190000]),   # -95k  (mes malo)
    4:  ([445000, 360000, 250000], [225000, 185000, 160000]),   # +485k
    5:  ([330000, 275000, 205000], [240000, 210000, 175000]),   # +185k
    6:  ([420000, 355000, 300000], [255000, 205000, 175000]),   # +440k
    7:  ([390000, 340000, 260000], [235000, 195000, 165000]),   # +395k
}


def _row(idx, direction, day, month, counterparty, concept, total, pv, anomaly=None):
    """Construye una fila AFIP. total = neto + IVA(21%), salvo anomalías."""
    cli_name, cli_cuit, cli_ib = counterparty
    if direction == "ingreso":
        emisor, e_cuit, e_ib = ZIRA
        receptor, r_cuit = cli_name, cli_cuit
    else:
        emisor, e_cuit, e_ib = cli_name, cli_cuit, cli_ib
        receptor, r_cuit = ZIRA[0], ZIRA[1]

    neto = round(total / 1.21, 2)
    iva = round(total - neto, 2)
    monto_total = total

    if anomaly == "iva":          # IVA muy por debajo del 21%
        iva = round(neto * 0.06, 2)
        monto_total = round(neto + iva, 2)
    elif anomaly == "total":      # total no cuadra con neto + iva
        monto_total = round((neto + iva) * 1.09, 2)

    return {
        "id_transaccion": f"TX-{idx:04d}",
        "tipo_movimiento": direction,
        "fecha_emision": f"{day:02d}/{month:02d}/2026",
        "tipo_comprobante": "Factura A",
        "punto_venta": pv,
        "numero_comprobante": 1000 + idx * 7,
        "emisor": emisor, "cuit_emisor": e_cuit, "ingresos_brutos_emisor": e_ib,
        "receptor": receptor, "cuit_receptor": r_cuit,
        "concepto": concept,
        "monto_neto": neto, "iva": iva, "monto_total": monto_total,
        "condicion_iva_emisor": "IVA Responsable Inscripto",
        "condicion_venta": "Contado" if idx % 3 else "Cuenta Corriente",
    }


def main() -> None:
    rows = []
    idx = 1
    for month, (ingresos, egresos) in PLAN.items():
        for j, amount in enumerate(ingresos):
            cli = CLIENTES[(idx + j) % len(CLIENTES)]
            concept = CONCEPTOS_INGRESO[(idx + j) % len(CONCEPTOS_INGRESO)]
            rows.append(_row(idx, "ingreso", 4 + j * 9, month, cli, concept, amount, 1))
            idx += 1
        for j, amount in enumerate(egresos):
            cli = CLIENTES[(idx + j) % len(CLIENTES)]
            concept = CONCEPTOS_EGRESO[(idx + j) % len(CONCEPTOS_EGRESO)]
            rows.append(_row(idx, "egreso", 6 + j * 8, month, cli, concept, amount, 2 + (j % 5)))
            idx += 1

    # --- 3 anomalías intencionales ---
    # (a) IVA mal: modificamos IN-PLACE un egreso de mayo (no agrega dinero nuevo).
    may_egresos = [r for r in rows
                   if r["tipo_movimiento"] == "egreso" and r["fecha_emision"].endswith("05/2026")]
    bad_iva = may_egresos[-1]
    bad_iva["iva"] = round(bad_iva["monto_neto"] * 0.06, 2)
    bad_iva["monto_total"] = round(bad_iva["monto_neto"] + bad_iva["iva"], 2)

    # (b) Total no cuadra: modificamos IN-PLACE un egreso de junio (infla ~9% el total).
    jun_egresos = [r for r in rows
                   if r["tipo_movimiento"] == "egreso" and r["fecha_emision"].endswith("06/2026")]
    bad_total = jun_egresos[-1]
    bad_total["monto_total"] = round((bad_total["monto_neto"] + bad_total["iva"]) * 1.09, 2)

    # (c) Duplicado: doble facturación en abril, pocos días después del original
    # (misma contraparte, mismo monto, fechas cercanas) -> doble cobro real.
    apr_egreso = next(r for r in rows
                      if r["tipo_movimiento"] == "egreso" and r["fecha_emision"].endswith("04/2026"))
    orig_day = int(apr_egreso["fecha_emision"][:2])
    rows.append({**apr_egreso, "id_transaccion": f"TX-{idx:04d}",
                 "fecha_emision": f"{orig_day + 3:02d}/04/2026", "numero_comprobante": 9001})

    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)

    # Resumen por mes.
    df["mes"] = pd.to_datetime(df["fecha_emision"], dayfirst=True).dt.strftime("%Y-%m")
    piv = df.pivot_table(index="mes", columns="tipo_movimiento",
                         values="monto_total", aggfunc="sum", fill_value=0)
    print(f"Escrito {OUT.relative_to(ROOT)} ({len(df)} movimientos)\n")
    for mes, r in piv.iterrows():
        ing, egr = r.get("ingreso", 0), r.get("egreso", 0)
        print(f"  {mes}: ingresos ${ing:>12,.0f} | egresos ${egr:>12,.0f} | "
              f"{'GANANCIA' if ing >= egr else 'PERDIDA '} ${abs(ing - egr):>11,.0f}")


if __name__ == "__main__":
    main()
