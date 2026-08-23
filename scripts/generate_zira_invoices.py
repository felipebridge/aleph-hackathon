#!/usr/bin/env python
"""Renderiza facturas AFIP de muestra a partir del dataset de movimientos de ZIRA.

Genera imágenes PNG legibles por OCR (Tesseract/QVAC) para probar en vivo la
detección ingreso/egreso desde la interfaz del contador:
  - Facturas donde ZIRA es EMISOR  -> venta   -> el agente marca INGRESO
  - Facturas donde ZIRA es RECEPTOR-> compra  -> el agente marca EGRESO

El layout pone al emisor arriba y al receptor abajo, que es lo que usa la
heurística de posición de `movements.detect_from_text`.

Uso: python scripts/generate_zira_invoices.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "movimientos_zira.csv"
OUT = ROOT / "data" / "facturas_zira"


def _font(size: int, bold: bool = False):
    candidates = (
        ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "arialbd.ttf"]
        if bold
        else ["/System/Library/Fonts/Supplemental/Arial.ttf", "arial.ttf",
              "/Library/Fonts/Arial.ttf"]
    )
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _money(v: float) -> str:
    return "$ " + f"{v:,.2f}"


def render_invoice(row, out_path: Path) -> None:
    W, H = 900, 620
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    f_big = _font(30, bold=True)
    f_h = _font(18, bold=True)
    f = _font(16)
    f_sm = _font(13)

    # Marco
    d.rectangle([10, 10, W - 10, H - 10], outline=(30, 30, 30), width=2)
    d.line([(W // 2, 10), (W // 2, 120)], fill=(30, 30, 30), width=2)

    # Tipo de comprobante (letra grande en el centro)
    letra = str(row.tipo_comprobante).replace("Factura", "").strip() or "A"
    d.rectangle([W // 2 - 30, 30, W // 2 + 30, 90], outline=(30, 30, 30), width=2)
    d.text((W // 2 - 12, 38), letra, font=f_big, fill=(20, 20, 20))
    d.text((W // 2 - 25, 95), f"COD. {int(row.punto_venta):02d}", font=f_sm, fill=(60, 60, 60))

    # --- EMISOR (arriba) ---
    d.text((30, 30), str(row.emisor), font=f_h, fill=(10, 10, 10))
    d.text((30, 58), f"CUIT: {row.cuit_emisor}", font=f, fill=(30, 30, 30))
    d.text((30, 80), "IVA Responsable Inscripto", font=f_sm, fill=(80, 80, 80))
    d.text((W // 2 + 40, 30), "FACTURA", font=f_h, fill=(10, 10, 10))
    d.text((W // 2 + 40, 58),
           f"N° {int(row.punto_venta):04d}-{int(row.numero_comprobante):08d}",
           font=f, fill=(30, 30, 30))
    d.text((W // 2 + 40, 80), f"Fecha: {row.fecha_emision}", font=f_sm, fill=(80, 80, 80))

    d.line([(20, 128), (W - 20, 128)], fill=(200, 200, 200), width=1)

    # --- RECEPTOR (abajo del emisor) ---
    y = 145
    d.text((30, y), "CLIENTE / RECEPTOR", font=f_sm, fill=(120, 120, 120))
    d.text((30, y + 22), f"Razón Social: {row.receptor}", font=f, fill=(10, 10, 10))
    d.text((30, y + 46), f"CUIT: {row.cuit_receptor}", font=f, fill=(30, 30, 30))
    d.text((30, y + 70), f"Condición de venta: {row.condicion_venta}", font=f_sm, fill=(80, 80, 80))

    d.line([(20, y + 100), (W - 20, y + 100)], fill=(200, 200, 200), width=1)

    # --- DETALLE ---
    y2 = y + 120
    d.text((30, y2), "Concepto", font=f_sm, fill=(120, 120, 120))
    d.text((W - 220, y2), "Importe", font=f_sm, fill=(120, 120, 120))
    d.text((30, y2 + 26), str(row.concepto), font=f, fill=(10, 10, 10))
    d.text((W - 220, y2 + 26), _money(row.monto_neto), font=f, fill=(10, 10, 10))

    # --- TOTALES ---
    y3 = y2 + 90
    d.line([(W - 340, y3), (W - 20, y3)], fill=(200, 200, 200), width=1)
    d.text((W - 340, y3 + 12), "Neto Gravado:", font=f, fill=(60, 60, 60))
    d.text((W - 200, y3 + 12), _money(row.monto_neto), font=f, fill=(10, 10, 10))
    d.text((W - 340, y3 + 40), "IVA 21%:", font=f, fill=(60, 60, 60))
    d.text((W - 200, y3 + 40), _money(row.iva), font=f, fill=(10, 10, 10))
    d.text((W - 340, y3 + 72), "IMPORTE TOTAL:", font=f_h, fill=(10, 10, 10))
    d.text((W - 200, y3 + 72), _money(row.monto_total), font=f_h, fill=(10, 10, 10))

    d.text((30, H - 45), f"CAE N°: 7412{int(row.numero_comprobante):08d}", font=f_sm,
           fill=(90, 90, 90))

    img.save(out_path)


def main() -> None:
    df = pd.read_csv(CSV)
    OUT.mkdir(parents=True, exist_ok=True)

    # Una venta (ingreso: ZIRA emisor) y una compra (egreso: ZIRA receptor).
    ingreso = df[df.tipo_movimiento == "ingreso"].iloc[0]
    egreso = df[df.tipo_movimiento == "egreso"].iloc[0]

    render_invoice(ingreso, OUT / f"VENTA_{ingreso.id_transaccion}_ingreso.png")
    render_invoice(egreso, OUT / f"COMPRA_{egreso.id_transaccion}_egreso.png")
    print(f"Facturas de muestra generadas en {OUT.relative_to(ROOT)}:")
    print(f"  VENTA_{ingreso.id_transaccion}_ingreso.png  (ZIRA emisor -> ingreso)")
    print(f"  COMPRA_{egreso.id_transaccion}_egreso.png   (ZIRA receptor -> egreso)")


if __name__ == "__main__":
    main()
