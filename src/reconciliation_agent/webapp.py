"""Minimal local web UI for the reconciliation agent.

One FastAPI app, two routes, server-rendered HTML -- no JS framework, no
build step. It's a thin HTTP layer over the exact same pipeline the CLI
uses (bank_loader, ocr_engine, extractor, matcher, report_html); nothing
here duplicates business logic.
"""

from __future__ import annotations

import logging
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import time

from . import dashboard, ledger, monthly_dataset, movements
from .bank_loader import BankStatementError, load_bank_statement
from .categories import categorize
from .cli import discover_receipt_files
from .config import Settings
from .extractor import parse_receipt
from .matcher import reconcile
from .models import Receipt
from .ocr_engine import (
    OcrEngineError,
    QVACOcrEngine,
    SidecarOcrEngine,
    TesseractOcrEngine,
)
from .report import write_text_report
from .report_html import render_html_report, write_html_report
from .serializers import result_to_dict

logger = logging.getLogger(__name__)

# Rutas por defecto de los datasets de demo argentinos.
_DEFAULT_EXPENSES = "data/bank_statement_ar.csv"
_DEFAULT_INCOME = "data/income_ar.csv"
_DEFAULT_RECEIPTS = "data/receipts_ar"

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

# The React dev server (Vite) runs on a different port during development.
# In production the SPA is built and served from the same origin, so this
# only matters for local dev -- kept permissive for localhost convenience.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _run_reconciliation(
    source: str,
    receipts_dir: str,
    whatsapp_month: str,
    bank_csv: str,
):
    """Shared pipeline used by both the HTML and JSON endpoints.

    Returns (result, None) on success or (None, error_message) on a
    recoverable input/engine error.
    """
    try:
        bank_df = load_bank_statement(Path(bank_csv))
    except BankStatementError as exc:
        return None, str(exc)

    if source == "whatsapp":
        if not whatsapp_month:
            return None, "Elegí un mes del dataset de WhatsApp."
        receipts: list[Receipt] = monthly_dataset.load(whatsapp_month)
    else:
        try:
            files = discover_receipt_files(Path(receipts_dir))
        except FileNotFoundError as exc:
            return None, str(exc)

        # QVAC is the primary engine. When the worker isn't installed (e.g. on a
        # demo laptop without the ~2.2 GB model), fall back to deterministic
        # sidecar OCR text for files that have it, so the pipeline still runs
        # end-to-end. If neither QVAC nor any sidecar is available, surface the
        # actionable install error.
        engine = _get_engine()
        if engine.is_available():
            active_engine = engine
        else:
            sidecar = SidecarOcrEngine()
            if not any(sidecar.has_sidecar(p) for p in files):
                return None, (
                    "El worker de QVAC no está disponible y no hay texto OCR "
                    "pre-computado para esta carpeta. Instalá QVAC con "
                    "`npm install -g @qvac/sdk@0.17.1` (y seteá QVAC_SDK_DIR), "
                    "o generá los sidecars con "
                    "`python scripts/generate_ar_sidecars.py`."
                )
            active_engine = sidecar

        receipts = []
        for path in files:
            try:
                ocr_result = active_engine.read(path)
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
    return result, None

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


@app.get("/classic", response_class=HTMLResponse)
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

    result, error = _run_reconciliation(source, receipts_dir, whatsapp_month, bank_csv)
    if error is not None:
        return _page(f'{back}<div class="error">{error}</div>')

    return render_html_report(result, nav_html=back)


# --- JSON API (consumed by the React SPA) ---------------------------------


@app.get("/api/health")
def api_health() -> dict:
    """Cheap readiness probe; also reports whether the QVAC worker is up."""
    return {
        "status": "ok",
        "qvac_available": _get_engine().is_available(),
    }


@app.get("/api/months")
def api_months() -> dict:
    """List the WhatsApp-intake months that have an accumulated dataset."""
    return {"months": _available_whatsapp_months()}


@app.post("/api/reconcile")
def api_reconcile(
    source: str = Form(...),
    receipts_dir: str = Form("data/receipts"),
    whatsapp_month: str = Form(""),
    bank_csv: str = Form("data/bank_statement.csv"),
) -> JSONResponse:
    """Run the pipeline and return the full result as JSON for the SPA."""
    result, error = _run_reconciliation(source, receipts_dir, whatsapp_month, bank_csv)
    if error is not None:
        return JSONResponse(status_code=400, content={"error": error})
    return JSONResponse(content=result_to_dict(result))


# --- Dashboard de Zira: dueño + contador ----------------------------------


def _load_income(path: str) -> pd.DataFrame:
    """Carga el CSV de ingresos (cobros a clientes). Columnas: date, amount, client."""
    p = Path(path)
    if not p.exists():
        return pd.DataFrame(columns=["date", "amount", "client", "description"])
    df = pd.read_csv(p)
    df.columns = [c.strip().lower() for c in df.columns]
    df["amount"] = (
        df["amount"].astype(str).str.replace(r"[^\d.\-]", "", regex=True).astype(float)
    )
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    if "client" not in df.columns:
        df["client"] = "Cliente"
    return df


@app.get("/api/owner/dashboard")
def api_owner_dashboard(
    income_csv: str = _DEFAULT_INCOME,
    expense_csv: str = _DEFAULT_EXPENSES,
) -> JSONResponse:
    """Vista del DUEÑO: ingresos, egresos, ganancia y rubros de gasto."""
    try:
        expense_df = load_bank_statement(Path(expense_csv))
    except BankStatementError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    income_df = _load_income(income_csv)
    return JSONResponse(content=dashboard.owner_dashboard(income_df, expense_df))


@app.get("/api/zira/dashboard")
def api_zira_dashboard(movements_csv: str = ledger.MOVEMENTS_CSV) -> JSONResponse:
    """Dashboard del dueño: dataset de ZIRA + facturas subidas por el contador.

    El agente clasifica ingreso/egreso por el rol de ZIRA y calcula
    automáticamente ingresos, egresos, ganancia y los rubros (de gasto y de
    ingreso). Todo lo que se sube en el área contable se refleja acá.
    """
    return JSONResponse(content=ledger.owner_dashboard(movements_csv))


@app.get("/api/accountant/ledger")
def api_accountant_ledger(movements_csv: str = ledger.MOVEMENTS_CSV) -> JSONResponse:
    """Vista del CONTADOR sobre el MISMO contenedor de facturas que el dueño.

    Proveedores (egresos) y clientes (ingresos), cada uno con la lista de sus
    facturas y su rubro, más las alertas para revisar. Incluye lo subido.
    """
    return JSONResponse(content=ledger.accountant_ledger(movements_csv))


@app.get("/api/invoices")
def api_invoices(movements_csv: str = ledger.MOVEMENTS_CSV) -> JSONResponse:
    """Contenedor completo de facturas (dataset + subidas), con alertas."""
    return JSONResponse(content={"invoices": ledger.all_invoices(movements_csv)})


def _ocr_uploaded(tmp_path: Path, demo_match: Path):
    """Cadena de OCR para archivos subidos: QVAC -> Tesseract -> sidecar de demo.

    Devuelve (OcrResult, engine_name) o lanza OcrEngineError si ninguno pudo.
    """
    qvac = _get_engine()
    if qvac.is_available():
        return qvac.read(tmp_path), "qvac"

    tess = TesseractOcrEngine()
    if tess.is_available():
        return tess.read(tmp_path), "tesseract"

    sidecar = SidecarOcrEngine()
    if demo_match.exists() and sidecar.has_sidecar(demo_match):
        return sidecar.read(demo_match), "sidecar"

    raise OcrEngineError(
        "No hay ningún motor de OCR disponible (ni QVAC, ni Tesseract, ni un "
        "sidecar pre-computado para este archivo)."
    )


@app.post("/api/analyze")
async def api_analyze(file: UploadFile = File(...)) -> JSONResponse:
    """Sube una foto/archivo de un comprobante y lo clasifica con IA.

    Corre OCR local (QVAC si está; si no, Tesseract; si no, sidecar de demo),
    extrae los campos y detecta si es INGRESO o EGRESO según el rol de ZIRA en
    el comprobante (emisor -> venta -> ingreso; receptor -> compra -> egreso).
    Devuelve además el rubro y un ID de contraparte estable para el libro mayor.
    """
    suffix = Path(file.filename or "upload").suffix or ".bin"
    data = await file.read()
    demo_match = Path(_DEFAULT_RECEIPTS) / (file.filename or "")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        try:
            ocr, engine_name = _ocr_uploaded(Path(tmp.name), demo_match)
        except OcrEngineError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
        receipt = parse_receipt(ocr, Path(file.filename or "upload"))

    # Detección ingreso/egreso por el rol de ZIRA en el texto del comprobante.
    detection = movements.detect_from_text(receipt.raw_text, receipt.merchant)
    direction = detection["direction"]
    counterparty = detection["counterparty"] or receipt.merchant
    cat = categorize(counterparty)
    prefix = "CLI" if direction == "ingreso" else "PROV"
    party_id = ledger._stable_id(prefix, counterparty or "desconocido")

    # Estimación de IVA (los comprobantes AR discriminan IVA al 21%).
    amount = receipt.amount or 0.0
    iva_est = round(amount - amount / 1.21, 2) if amount else 0.0

    # Persistimos la factura en el contenedor -> se refleja en dueño y contador.
    invoice = {
        "id": f"UP-{int(time.time() * 1000) % 10_000_000:07d}",
        "direction": direction,
        "date": receipt.txn_date.isoformat() if receipt.txn_date else None,
        "counterparty": counterparty or "Desconocido",
        "counterparty_cuit": (detection["cuits_found"] or [""])[0] if detection["cuits_found"] else "",
        "concept": f"Comprobante subido ({file.filename})",
        "category": cat.label,
        "category_key": cat.key,
        "category_color": cat.color,
        "amount": round(amount, 2),
        "net": round(amount - iva_est, 2),
        "iva": iva_est,
        "source": "upload",
        "fully_parsed": receipt.is_fully_parsed,
        "filename": file.filename,
    }
    ledger.append_uploaded(invoice)

    return JSONResponse(content={
        **invoice,
        "engine": engine_name,
        "direction_confidence": detection["confidence"],
        "zira_detected": detection["zira_detected"],
        "party_id": party_id,
        "role": "Cliente" if direction == "ingreso" else "Proveedor",
        "cuits_found": detection["cuits_found"],
        "raw_text": receipt.raw_text[:600],
        "registered": True,
    })


# --- Serve the built React SPA (production) -------------------------------
# `cd frontend && npm run build` emits into static/. When present, the SPA
# is served at "/"; if it hasn't been built yet, "/" falls back to a hint
# pointing at the classic no-JS form. The dev workflow uses Vite on :5173
# with a proxy to this API, so this only matters for the bundled build.

_STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", response_class=HTMLResponse)
def spa_root() -> str:
    index_file = _STATIC_DIR / "index.html"
    if index_file.exists():
        return index_file.read_text(encoding="utf-8")
    return _page(
        '<div class="card">La interfaz React no está compilada todavía. '
        "Corré <code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code>, "
        'o usá el formulario clásico en <a href="/classic">/classic</a>.</div>'
    )


if _STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"), name="assets")
