"""Minimal local web UI for the reconciliation agent.

One FastAPI app, two routes, server-rendered HTML -- no JS framework, no
build step. It's a thin HTTP layer over the exact same pipeline the CLI
uses (bank_loader, ocr_engine, extractor, matcher, report_html); nothing
here duplicates business logic.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

from . import monthly_dataset
from .bank_loader import BankStatementError, load_bank_statement
from .cli import discover_receipt_files
from .config import Settings
from .extractor import parse_receipt
from .matcher import reconcile
from .models import Receipt
from .ocr_engine import OcrEngineError, QVACOcrEngine
from .report import write_text_report
from .report_html import render_html_report, write_html_report

logger = logging.getLogger(__name__)

_engine: QVACOcrEngine | None = None


def _get_engine() -> QVACOcrEngine:
    global _engine
    if _engine is None:
        _engine = QVACOcrEngine()
    return _engine


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    yield
    if _engine is not None:
        _engine.close()


app = FastAPI(title="Reconciliation Agent", lifespan=_lifespan)

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #f4f6f9; color: #2c3e50; padding: 32px 24px; }
.container { max-width: 640px; margin: 60px auto; }
header { background: #1a252f; color: #fff; border-radius: 10px;
         padding: 28px 32px; margin-bottom: 28px; }
header h1 { font-size: 1.5rem; font-weight: 700; margin-bottom: 6px; }
header p  { font-size: 0.85rem; color: #aab7b8; }
.badge { display: inline-block; background: #27ae60; color: #fff;
         font-size: 0.7rem; font-weight: 600; padding: 2px 8px;
         border-radius: 20px; margin-left: 8px; vertical-align: middle; }
.card { background: #fff; border-radius: 10px; padding: 28px 32px;
        box-shadow: 0 1px 4px rgba(0,0,0,.08); }
.field { margin-bottom: 18px; }
label { display: block; font-size: 0.8rem; font-weight: 600; color: #566573;
        text-transform: uppercase; letter-spacing: .04em; margin-bottom: 6px; }
.radio-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px;
             font-size: 0.95rem; font-weight: 500; text-transform: none;
             letter-spacing: normal; color: #2c3e50; }
input[type=text], select { width: 100%; padding: 10px 12px; border: 1px solid #dfe4ea;
       border-radius: 6px; font-size: 0.9rem; font-family: inherit; }
button { width: 100%; background: #2980b9; color: #fff; border: none;
         border-radius: 6px; padding: 13px; font-size: 0.95rem; font-weight: 600;
         cursor: pointer; margin-top: 8px; }
button:hover { background: #21618c; }
button:disabled { background: #95a5a6; cursor: wait; }
.error { background: #fdf2f2; border: 1px solid #c0392b; color: #922b21;
         border-radius: 8px; padding: 16px 20px; margin-bottom: 20px; font-size: 0.9rem; }
.nav-back { display: inline-block; margin-bottom: 16px; color: #2980b9;
            text-decoration: none; font-size: 0.85rem; font-weight: 600; }
.nav-back:hover { text-decoration: underline; }
"""


def _page(body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agente de Reconciliación</title>
  <style>{_CSS}</style>
</head>
<body>
<div class="container">{body}</div>
</body>
</html>"""


def _available_whatsapp_months() -> list[str]:
    if not monthly_dataset.DATA_ROOT.exists():
        return []
    return sorted(p.name for p in monthly_dataset.DATA_ROOT.iterdir() if p.is_dir())


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    months = _available_whatsapp_months()
    month_options = "".join(f'<option value="{m}">{m}</option>' for m in months) or (
        '<option value="" disabled selected>(corré el simulador primero)</option>'
    )
    return _page(f"""
<header>
  <h1>Agente de Reconciliación <span class="badge">100% local</span></h1>
  <p>El OCR y el cruce contra el banco corren en esta máquina vía QVAC. Elegí de dónde vienen los recibos y reconciliá.</p>
</header>
<form class="card" method="post" action="/reconcile"
      onsubmit="const b=document.getElementById('btn'); b.disabled=true; b.textContent='Procesando… puede tardar un minuto';">
  <div class="field">
    <label class="radio-row"><input type="radio" name="source" value="folder" checked
      onchange="document.getElementById('folder-fields').style.display='block';document.getElementById('whatsapp-fields').style.display='none';">
      Carpeta local de recibos</label>
    <div id="folder-fields">
      <input type="text" name="receipts_dir" value="data/receipts" placeholder="data/receipts">
    </div>
    <label class="radio-row" style="margin-top:14px">
      <input type="radio" name="source" value="whatsapp"
      onchange="document.getElementById('folder-fields').style.display='none';document.getElementById('whatsapp-fields').style.display='block';">
      Dataset de WhatsApp (mensual)</label>
    <div id="whatsapp-fields" style="display:none">
      <select name="whatsapp_month">{month_options}</select>
    </div>
  </div>
  <div class="field">
    <label for="bank_csv">Extracto bancario (CSV)</label>
    <input type="text" id="bank_csv" name="bank_csv" value="data/bank_statement.csv">
  </div>
  <button id="btn" type="submit">Reconciliar</button>
</form>
""")


@app.post("/reconcile", response_class=HTMLResponse)
def do_reconcile(
    source: str = Form(...),
    receipts_dir: str = Form("data/receipts"),
    whatsapp_month: str = Form(""),
    bank_csv: str = Form("data/bank_statement.csv"),
) -> str:
    back = '<a class="nav-back" href="/">&larr; Nueva reconciliación</a>'

    try:
        bank_df = load_bank_statement(Path(bank_csv))
    except BankStatementError as exc:
        return _page(f'{back}<div class="error">{exc}</div>')

    if source == "whatsapp":
        if not whatsapp_month:
            return _page(f'{back}<div class="error">Elegí un mes del dataset de WhatsApp.</div>')
        receipts = monthly_dataset.load(whatsapp_month)
    else:
        try:
            files = discover_receipt_files(Path(receipts_dir))
        except FileNotFoundError as exc:
            return _page(f'{back}<div class="error">{exc}</div>')

        engine = _get_engine()
        if not engine.is_available():
            return _page(
                f'{back}<div class="error">El worker de QVAC no está disponible. '
                "Instalalo con <code>npm install -g @qvac/sdk@0.17.1</code> y "
                "seteá <code>QVAC_SDK_DIR</code> antes de levantar este servidor.</div>"
            )
        receipts: list[Receipt] = []
        for path in files:
            try:
                ocr_result = engine.read(path)
            except OcrEngineError as exc:
                logger.warning("Skipping %s: %s", path.name, exc)
                continue
            receipts.append(parse_receipt(ocr_result, path))

    settings = Settings(
        receipts_dir=Path(receipts_dir),
        bank_csv=Path(bank_csv),
        output_path=Path("reports/reconciliation_report.txt"),
    )
    result = reconcile(receipts, bank_df, settings)

    write_text_report(result, settings.output_path)
    write_html_report(result, settings.output_path.with_suffix(".html"))

    return render_html_report(result, nav_html=back)
