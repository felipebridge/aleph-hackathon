#!/usr/bin/env python
"""Genera un PDF explicativo de una corrida de reconciliación.

Corre el pipeline sobre una carpeta de recibos + un extracto bancario y
produce un documento que explica, comprobante por comprobante, cuáles
conciliaron correctamente y cuáles dispararon un hallazgo crítico (y por qué).

Uso:
    python scripts/generate_report_pdf.py \
        --receipts-dir data/receipts_ar \
        --bank-csv data/bank_statement_ar.csv \
        --output reports/reporte_reconciliacion.pdf
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from reconciliation_agent.bank_loader import load_bank_statement
from reconciliation_agent.config import Settings
from reconciliation_agent.extractor import parse_receipt
from reconciliation_agent.matcher import reconcile
from reconciliation_agent.models import Severity
from reconciliation_agent.ocr_engine import QVACOcrEngine, SidecarOcrEngine

# --- paleta ---------------------------------------------------------------
INK = colors.HexColor("#0f172a")
SLATE = colors.HexColor("#475569")
MUTED = colors.HexColor("#94a3b8")
GREEN = colors.HexColor("#059669")
GREEN_BG = colors.HexColor("#ecfdf5")
RED = colors.HexColor("#dc2626")
RED_BG = colors.HexColor("#fef2f2")
AMBER = colors.HexColor("#d97706")
LINE = colors.HexColor("#e2e8f0")


def _money(n) -> str:
    if n is None:
        return "—"
    return "$ " + f"{n:,.2f}"


def _load_receipts(receipts_dir: Path):
    """QVAC si está disponible; si no, sidecars pre-computados."""
    files = sorted(
        p
        for p in receipts_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".pdf"}
    )
    qvac = QVACOcrEngine()
    engine = qvac if qvac.is_available() else SidecarOcrEngine()
    receipts = []
    for path in files:
        try:
            receipts.append(parse_receipt(engine.read(path), path))
        except Exception:  # noqa: BLE001 -- un archivo ilegible no frena el resto
            continue
    if hasattr(engine, "close"):
        engine.close()
    return receipts, engine.name


def _styles():
    ss = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "title", parent=ss["Title"], textColor=colors.white, fontSize=20,
            leading=24, alignment=TA_LEFT, fontName="Helvetica-Bold",
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=ss["Normal"], textColor=colors.HexColor("#cbd5e1"),
            fontSize=9, leading=13,
        ),
        "h2": ParagraphStyle(
            "h2", parent=ss["Heading2"], textColor=INK, fontSize=13, leading=16,
            spaceBefore=6, spaceAfter=4, fontName="Helvetica-Bold",
        ),
        "body": ParagraphStyle(
            "body", parent=ss["Normal"], textColor=SLATE, fontSize=9.5, leading=14,
        ),
        "small": ParagraphStyle(
            "small", parent=ss["Normal"], textColor=MUTED, fontSize=8, leading=11,
        ),
        "cell": ParagraphStyle("cell", parent=ss["Normal"], fontSize=8.5, leading=12,
                               textColor=SLATE),
        "cellb": ParagraphStyle("cellb", parent=ss["Normal"], fontSize=8.5, leading=12,
                                textColor=INK, fontName="Helvetica-Bold"),
        "statnum": ParagraphStyle("statnum", fontSize=22, leading=24,
                                  fontName="Helvetica-Bold", alignment=TA_CENTER),
        "statlbl": ParagraphStyle("statlbl", fontSize=7, leading=9, textColor=MUTED,
                                  alignment=TA_CENTER),
    }
    return styles


def _header(styles, engine_name):
    ts = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    inner = Table(
        [[
            Paragraph("Reporte de Reconciliación Financiera", styles["title"]),
        ], [
            Paragraph(
                f"Generado: {ts} &nbsp;·&nbsp; Motor OCR: {engine_name} &nbsp;·&nbsp; "
                "100% procesado localmente, ningún dato salió del equipo.",
                styles["subtitle"],
            ),
        ]],
        colWidths=[17 * cm],
    )
    inner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), INK),
        ("LEFTPADDING", (0, 0), (-1, -1), 18),
        ("RIGHTPADDING", (0, 0), (-1, -1), 18),
        ("TOPPADDING", (0, 0), (0, 0), 16),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 16),
        ("TOPPADDING", (0, 1), (-1, 1), 2),
    ]))
    return inner


def _stat_cards(styles, result):
    def card(num, label, color):
        n = ParagraphStyle("n", parent=styles["statnum"], textColor=color)
        return Table([[Paragraph(str(num), n)], [Paragraph(label, styles["statlbl"])]],
                     colWidths=[3.1 * cm])

    cards = [
        card(result.receipts_processed, "RECIBOS", INK),
        card(result.bank_transactions_total, "TRANSACCIONES", INK),
        card(len(result.matched), "MATCHES OK", GREEN),
        card(result.critical_count, "CRÍTICOS", RED),
        card(result.warning_count, "ALERTAS", AMBER),
    ]
    row = Table([cards], colWidths=[3.4 * cm] * 5)
    row.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return row


def _clean_table(styles, matched):
    header = [
        Paragraph("Comercio", styles["cellb"]),
        Paragraph("Archivo", styles["cellb"]),
        Paragraph("Monto recibo", styles["cellb"]),
        Paragraph("Monto banco", styles["cellb"]),
        Paragraph("Fecha", styles["cellb"]),
    ]
    rows = [header]
    for m in matched:
        rows.append([
            Paragraph(m.receipt.merchant or "—", styles["cell"]),
            Paragraph(m.receipt.display_name, styles["small"]),
            Paragraph(_money(m.receipt.amount), styles["cell"]),
            Paragraph(_money(m.bank_txn.amount), styles["cell"]),
            Paragraph(str(m.bank_txn.txn_date), styles["cell"]),
        ])
    t = Table(rows, colWidths=[4 * cm, 4.6 * cm, 2.8 * cm, 2.8 * cm, 2.6 * cm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN_BG),
        ("LINEBELOW", (0, 0), (-1, 0), 1, GREEN),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


_TYPE_EXPLAIN = {
    "AMOUNT_MISMATCH": "El comprobante y el banco coinciden en comercio y fecha, "
                       "pero el importe difiere. Es la alerta principal de error de "
                       "facturación o cobro indebido.",
    "UNACCOUNTED_CHARGE": "El banco registra un cargo que no tiene ningún comprobante "
                          "asociado en el archivo. Dinero que salió sin respaldo documental.",
    "MISSING_IN_BANK": "Hay un comprobante cargado que no encuentra ningún cargo "
                       "correspondiente en el extracto bancario.",
    "DUPLICATE_RECEIPT": "Dos comprobantes parecen la misma compra (mismo comercio, "
                         "monto y fecha) pero solo existe un cargo bancario.",
}


def _critical_block(styles, d, idx):
    label = {
        "AMOUNT_MISMATCH": "Monto no coincide",
        "UNACCOUNTED_CHARGE": "Cargo sin recibo",
        "MISSING_IN_BANK": "Falta en el banco",
        "DUPLICATE_RECEIPT": "Recibo duplicado",
    }.get(d.type.value, d.type.value)

    title = Paragraph(f"<b>{idx}. {label}</b>", ParagraphStyle(
        "ct", fontSize=10.5, leading=14, textColor=RED, fontName="Helvetica-Bold"))
    msg = Paragraph(d.message, styles["body"])
    why = Paragraph(f"<i>Qué significa:</i> {_TYPE_EXPLAIN.get(d.type.value, '')}",
                    styles["small"])

    detail_rows = []
    if d.receipt:
        detail_rows.append(["Comprobante", d.receipt.display_name])
        detail_rows.append(["Comercio (recibo)", d.receipt.merchant or "—"])
        detail_rows.append(["Monto recibo", _money(d.receipt.amount)])
    if d.bank_txn:
        detail_rows.append(["Transacción banco", d.bank_txn.transaction_id])
        detail_rows.append(["Comercio (banco)", d.bank_txn.merchant])
        detail_rows.append(["Monto banco", _money(d.bank_txn.amount)])
    if d.delta_amount is not None:
        detail_rows.append(["Diferencia", _money(d.delta_amount)])

    detail = Table(
        [[Paragraph(k, styles["small"]), Paragraph(str(v), styles["cell"])]
         for k, v in detail_rows],
        colWidths=[3.6 * cm, 8.8 * cm],
    )
    detail.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    wrapper = Table([[title], [msg], [why], [Spacer(1, 4)], [detail]],
                    colWidths=[12.8 * cm])
    wrapper.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), RED_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#fecaca")),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (0, 0), 10),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
    ]))
    return wrapper


def build_pdf(receipts_dir: Path, bank_csv: Path, output: Path) -> Path:
    receipts, engine_name = _load_receipts(receipts_dir)
    bank_df = load_bank_statement(bank_csv)
    settings = Settings(
        receipts_dir=receipts_dir, bank_csv=bank_csv,
        output_path=Path("reports/_tmp.txt"),
    )
    result = reconcile(receipts, bank_df, settings)

    styles = _styles()
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output), pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.6 * cm, bottomMargin=1.6 * cm,
        title="Reporte de Reconciliación",
    )

    story = [
        _header(styles, engine_name),
        Spacer(1, 14),
        _stat_cards(styles, result),
        Spacer(1, 18),
        Paragraph("Cómo leer este documento", styles["h2"]),
        Paragraph(
            "Cada recibo cargado se cruza contra el extracto bancario por comercio, "
            "monto y fecha (con tolerancia de días por demora de acreditación). Abajo "
            "se listan primero los comprobantes que conciliaron correctamente y luego, "
            "en detalle, cada hallazgo crítico que requiere revisión humana.",
            styles["body"],
        ),
        Spacer(1, 14),
    ]

    # --- Sección OK ---
    story.append(Paragraph(
        f"Comprobantes conciliados correctamente ({len(result.matched)})",
        ParagraphStyle("okh", fontSize=13, leading=16, textColor=GREEN,
                       fontName="Helvetica-Bold")))
    if result.matched:
        story.append(Paragraph(
            "Comercio, monto y fecha coinciden con un cargo del banco dentro de la "
            "tolerancia. No requieren acción.", styles["small"]))
        story.append(Spacer(1, 6))
        story.append(_clean_table(styles, result.matched))
    else:
        story.append(Paragraph("No hubo matches limpios en esta corrida.", styles["body"]))
    story.append(Spacer(1, 18))

    # --- Sección crítica ---
    criticals = [d for d in result.discrepancies if d.severity is Severity.CRITICAL]
    story.append(HRFlowable(width="100%", thickness=0.5, color=LINE))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"Hallazgos críticos ({len(criticals)})", ParagraphStyle(
            "hc", fontSize=13, leading=16, textColor=RED, fontName="Helvetica-Bold")))
    story.append(Paragraph(
        "Requieren revisión manual antes de dar por cerrada la conciliación.",
        styles["small"]))
    story.append(Spacer(1, 8))
    for i, d in enumerate(criticals, 1):
        story.append(_critical_block(styles, d, i))
        story.append(Spacer(1, 10))

    # --- Alertas (warnings), si hubiera ---
    warnings = [d for d in result.discrepancies if d.severity is Severity.WARNING]
    if warnings:
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"Alertas menores ({len(warnings)})", styles["h2"]))
        for d in warnings:
            story.append(Paragraph(f"• {d.message}", styles["body"]))
            story.append(Spacer(1, 4))

    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=LINE))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Privacy-First AI Financial Reconciliation Agent · Tether QVAC Track · "
        "Documento generado localmente.", styles["small"]))

    doc.build(story)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipts-dir", type=Path, default=Path("data/receipts_ar"))
    parser.add_argument("--bank-csv", type=Path, default=Path("data/bank_statement_ar.csv"))
    parser.add_argument("--output", type=Path,
                        default=Path("reports/reporte_reconciliacion.pdf"))
    args = parser.parse_args()

    out = build_pdf(args.receipts_dir, args.bank_csv, args.output)
    print(f"PDF generado: {out}")


if __name__ == "__main__":
    main()
