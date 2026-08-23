#!/usr/bin/env python
"""Generates deterministic OCR sidecar files for the Argentine demo receipts.

Writes a `<receipt>.ocr.txt` next to each file in data/receipts_ar/ so the
web UI and the pipeline can run end-to-end WITHOUT the ~2.2 GB QVAC worker
installed (the SidecarOcrEngine reads these when QVAC is unavailable). The
text mimics what a vision-OCR model would transcribe from each receipt type
(AFIP facturas vs. ride/delivery app receipts) and is dated to line up with
data/bank_statement_ar.csv (July 2026).

Demo outcome by design:
  - 7 clean matches
  - 1 AMOUNT_MISMATCH  (LuzSur: receipt reads 15,000 vs bank 18,500)
  - 2 UNACCOUNTED_CHARGE (the 95,000 transfer and the 1,200 Mercado Pago,
    which have no receipt on file)

Run: python scripts/generate_ar_sidecars.py
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECEIPTS_DIR = ROOT / "data" / "receipts_ar"

# filename -> OCR text. ISO dates (YYYY-MM-DD) are used so the extractor
# parses them unambiguously regardless of day/month order.
SIDECARS: dict[str, str] = {
    "Uber_receipt_5.pdf": """\
Uber
Gracias por viajar, Martina
Fecha: 2026-07-02
Viaje                       ARS 3,880.00
Tarifa de reserva           ARS 300.00
Promoción                  -ARS 650.00
Uber One Credits           -ARS 410.00
Total                       ARS 3,120.00
Mercado Pago
""",
    "Uber_receipt_6.jpg": """\
Uber
Gracias por viajar, Martina
Fecha: 2026-07-20
Viaje                       ARS 3,400.00
Tarifa de reserva           ARS 280.00
Promoción                  -ARS 560.00
Total                       ARS 3,120.00
Mercado Pago
""",
    "Rappi_recibo_1.jpg": """\
Rappi
Pedido #A-88213
Fecha: 2026-07-05
Producto                    ARS 2,340.00
Costo de envío              ARS 450.00
Servicio                    ARS 150.00
Total                       ARS 2,940.00
Pago: Tarjeta de crédito
""",
    "PetroSur_combustible_1.pdf": """\
ORIGINAL (EJEMPLO)
B
COD. 06
PETROSUR COMBUSTIBLES S.A.   FACTURA (MUESTRA)
Razon Social: PETROSUR COMBUSTIBLES S.A.
CUIT: 30-71234567-8
Fecha de Emision: 2026-07-08
Nafta Super  1.00 unidades  4,630.00
Subtotal: $ 3,826.45
Importe Otros Tributos: $ 0.00
Importe Total: $ 4,630.00
CAE: 74123456789012
""",
    "PeYA_RECIPT.pdf": """\
PedidosYa
Comprobante de compra
Fecha: 2026-07-10
Empanadas x12               ARS 1,400.00
Costo de envio              ARS 350.00
Servicio                    ARS 100.00
Total                       ARS 1,850.00
Pago: Mercado Pago
""",
    # Intentional AMOUNT_MISMATCH: receipt total 15,000 vs bank charge 18,500.
    "LuzSur_electricidad_1.pdf": """\
ORIGINAL (EJEMPLO)
B
COD. 06
LUZSUR DISTRIBUIDORA S.A.   FACTURA (MUESTRA)
Razon Social: LUZSUR DISTRIBUIDORA S.A.
CUIT: 30-70987654-3
Fecha de Emision: 2026-07-12
Consumo electrico kWh       12,300.00
Cargo fijo                  2,700.00
Subtotal: $ 12,396.69
Importe Total: $ 15,000.00
CAE: 74987654321098
""",
    "Cabify_recibo_1.pdf": """\
Cabify
Recibo de viaje
Fecha: 2026-07-15
Tarifa                      ARS 2,520.00
Peaje                       ARS 300.00
Total                       ARS 2,820.00
Pago: Tarjeta
""",
    "ExpressCourier_envio_1.jpg": """\
ORIGINAL (EJEMPLO)
B
COD. 06
EXPRESS COURIER S.R.L.   FACTURA (MUESTRA)
Razon Social: EXPRESS COURIER S.R.L.
CUIT: 30-71555666-9
Fecha de Emision: 2026-07-18
Envio express 5kg           5,120.00
Seguro                      1,080.00
Subtotal: $ 5,123.97
Importe Total: $ 6,200.00
CAE: 74555666777888
""",
}


def main() -> None:
    if not RECEIPTS_DIR.exists():
        raise SystemExit(f"No existe {RECEIPTS_DIR}. ¿Corriste desde la raíz del repo?")

    written = 0
    for filename, text in SIDECARS.items():
        receipt = RECEIPTS_DIR / filename
        if not receipt.exists():
            print(f"  (saltando {filename}: el recibo no está en data/receipts_ar/)")
            continue
        sidecar = receipt.with_suffix(receipt.suffix + ".ocr.txt")
        sidecar.write_text(text, encoding="utf-8")
        print(f"  Escrito {sidecar.relative_to(ROOT)}")
        written += 1

    print(f"\nListo. {written} sidecars generados en {RECEIPTS_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
