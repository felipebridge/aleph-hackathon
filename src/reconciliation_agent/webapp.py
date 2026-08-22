"""Local web UI for the reconciliation agent.

One FastAPI app, server-rendered HTML -- no JS framework, no build step.
It's a thin HTTP layer over the exact same pipeline the CLI uses
(bank_loader, ocr_engine, extractor, matcher, report_html); nothing here
duplicates business logic. The extra surface versus a bare form --
discovering available receipt sources/bank CSVs, exposing the matcher's
thresholds, keeping a history of past runs -- is presentation only, built
entirely on top of that same pipeline.
"""

from __future__ import annotations

import datetime as dt
import html
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

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

DATA_DIR = Path("data")
REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

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
app.mount("/report-files", StaticFiles(directory=str(REPORTS_DIR)), name="report-files")

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #f4f6f9; --ink: #2c3e50; --muted: #7f8c8d; --line: #e3e8ee;
  --card: #fff; --accent: #2980b9; --accent-dark: #21618c;
  --green: #27ae60; --green-bg: #eafaf1; --red: #c0392b; --red-bg: #fdf2f2;
  --yellow: #d68910; --yellow-bg: #fef9e7;
}
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: var(--bg); color: var(--ink); padding: 32px 20px 60px; }
.container { max-width: 880px; margin: 0 auto; }
header.top { background: linear-gradient(135deg, #1a252f, #212f3d); color: #fff;
         border-radius: 12px; padding: 30px 34px; margin-bottom: 24px; }
header.top h1 { font-size: 1.55rem; font-weight: 700; margin-bottom: 6px; display: flex;
            align-items: center; gap: 10px; }
header.top p  { font-size: 0.85rem; color: #aab7b8; line-height: 1.5; }
.badge { display: inline-block; background: var(--green); color: #fff;
         font-size: 0.68rem; font-weight: 700; padding: 3px 10px;
         border-radius: 20px; vertical-align: middle; letter-spacing: .03em; }
.grid { display: grid; grid-template-columns: 1fr; gap: 20px; }
@media (min-width: 760px) { .grid.two { grid-template-columns: 1.4fr 1fr; align-items: start; } }
.card { background: var(--card); border-radius: 12px; padding: 26px 28px;
        box-shadow: 0 1px 4px rgba(0,0,0,.07); border: 1px solid var(--line); }
.card h2 { font-size: 0.78rem; font-weight: 700; color: var(--muted);
           text-transform: uppercase; letter-spacing: .06em; margin-bottom: 16px; }
.field { margin-bottom: 20px; }
.field:last-child { margin-bottom: 0; }
label.field-label { display: block; font-size: 0.78rem; font-weight: 700; color: #566573;
        text-transform: uppercase; letter-spacing: .04em; margin-bottom: 8px; }
.hint { font-size: 0.78rem; color: var(--muted); margin-top: 6px; line-height: 1.4; }
.source-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
                gap: 10px; margin-bottom: 4px; }
.tile { position: relative; display: block; border: 1.5px solid var(--line); border-radius: 10px;
        padding: 14px 14px 12px; cursor: pointer; transition: border-color .12s, background .12s; }
.tile:hover { border-color: #b9c4cf; }
.tile input { position: absolute; opacity: 0; }
.tile .tile-title { font-weight: 700; font-size: 0.88rem; margin-bottom: 3px; }
.tile .tile-sub { font-size: 0.76rem; color: var(--muted); }
.tile input:checked ~ .tile-check { display: block; }
.tile-check { display: none; position: absolute; top: 10px; right: 10px; width: 16px; height: 16px;
              border-radius: 50%; background: var(--accent); }
.tile-check::after { content: ''; position: absolute; left: 5px; top: 2px; width: 4px; height: 8px;
                      border: solid #fff; border-width: 0 2px 2px 0; transform: rotate(45deg); }
.tile.selected { border-color: var(--accent); background: #f3f9fd; }
.tile.empty { opacity: .55; cursor: not-allowed; }
input[type=text], input[type=number], select {
       width: 100%; padding: 10px 12px; border: 1px solid #dfe4ea;
       border-radius: 7px; font-size: 0.88rem; font-family: inherit; background: #fff; }
input[list] { width: 100%; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
button.primary { width: 100%; background: var(--accent); color: #fff; border: none;
         border-radius: 8px; padding: 14px; font-size: 0.95rem; font-weight: 700;
         cursor: pointer; margin-top: 18px; letter-spacing: .01em; }
button.primary:hover { background: var(--accent-dark); }
button.primary:disabled { background: #95a5a6; cursor: wait; }
details.adv { margin-top: 4px; border-top: 1px solid var(--line); padding-top: 14px; }
details.adv summary { cursor: pointer; font-size: 0.8rem; font-weight: 700; color: var(--accent);
                       list-style: none; user-select: none; }
details.adv summary::-webkit-details-marker { display: none; }
details.adv summary::before { content: '\\25B8  '; }
details.adv[open] summary::before { content: '\\25BE  '; }
details.adv .adv-body { padding-top: 16px; }
.error { background: var(--red-bg); border: 1px solid var(--red); color: #922b21;
         border-radius: 10px; padding: 16px 20px; margin-bottom: 20px; font-size: 0.9rem; }
.nav-back { display: inline-block; margin-bottom: 16px; color: var(--accent);
            text-decoration: none; font-size: 0.85rem; font-weight: 600; }
.nav-back:hover { text-decoration: underline; }
.empty-state { font-size: 0.82rem; color: var(--muted); padding: 10px 2px; line-height: 1.6; }
.empty-state code { background: #eef1f4; padding: 1px 5px; border-radius: 4px; }
ul.report-list { list-style: none; }
ul.report-list li { padding: 11px 0; border-bottom: 1px solid var(--line); }
ul.report-list li:last-child { border-bottom: none; }
ul.report-list a { color: var(--ink); font-weight: 600; font-size: 0.86rem; text-decoration: none; }
ul.report-list a:hover { color: var(--accent); }
ul.report-list .meta { display: block; font-size: 0.74rem; color: var(--muted); margin-top: 2px; }
.stat-row { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 4px; }
.stat-pill { background: #eef1f4; border-radius: 20px; padding: 4px 12px; font-size: 0.72rem;
             font-weight: 700; color: #566573; }
"""

_JS = """
function selectSource(el) {
  document.querySelectorAll('.tile[data-group="source"]').forEach(t => t.classList.remove('selected'));
  el.classList.add('selected');
  const val = el.querySelector('input').value;
  document.getElementById('folder-fields').style.display = val === 'folder' ? 'block' : 'none';
  document.getElementById('whatsapp-fields').style.display = val === 'whatsapp' ? 'block' : 'none';
}
function selectFolderTile(el) {
  document.querySelectorAll('.tile[data-group="folder"]').forEach(t => t.classList.remove('selected'));
  el.classList.add('selected');
  document.getElementById('receipts_dir').value = el.querySelector('input').value;
}
function onSubmitForm() {
  const b = document.getElementById('btn');
  b.disabled = true;
  b.textContent = 'Procesando… puede tardar un minuto';
  return true;
}
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
<script>{_JS}</script>
</body>
</html>"""


_SUPPORTED_EXT = {".png", ".jpg", ".jpeg", ".pdf", ".tiff", ".bmp"}


def _discover_receipt_sources() -> list[dict]:
    """Any top-level data/ subfolder (besides the WhatsApp intake) that holds
    at least one receipt-shaped file. Built from disk, not hardcoded, so a
    freshly generated dataset just shows up."""
    sources = []
    if not DATA_DIR.exists():
        return sources
    for entry in sorted(DATA_DIR.iterdir()):
        if not entry.is_dir() or entry.name == "whatsapp_intake":
            continue
        count = sum(1 for f in entry.iterdir() if f.is_file() and f.suffix.lower() in _SUPPORTED_EXT)
        if count:
            sources.append({"path": str(entry).replace("\\", "/"), "label": entry.name, "count": count})
    return sources


def _discover_bank_csvs() -> list[dict]:
    if not DATA_DIR.exists():
        return []
    options = []
    for f in sorted(DATA_DIR.glob("*.csv")):
        try:
            rows = max(sum(1 for _ in f.open(encoding="utf-8")) - 1, 0)
        except OSError:
            rows = None
        options.append({"path": str(f).replace("\\", "/"), "rows": rows})
    return options


def _available_whatsapp_months() -> list[dict]:
    if not monthly_dataset.DATA_ROOT.exists():
        return []
    months = []
    for p in sorted(monthly_dataset.DATA_ROOT.iterdir(), reverse=True):
        if not p.is_dir():
            continue
        count = len(monthly_dataset.load(p.name))
        months.append({"month": p.name, "count": count})
    return months


_REPORT_NAME_RE = re.compile(r"^reconciliation_(?P<tag>.+)_(?P<ts>\d{8}_\d{6})\.html$")


def _recent_reports(limit: int = 8) -> list[dict]:
    if not REPORTS_DIR.exists():
        return []
    files = sorted(
        (p for p in REPORTS_DIR.glob("reconciliation_*.html") if p.name != "reconciliation_report.html"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    out = []
    for f in files[:limit]:
        m = _REPORT_NAME_RE.match(f.name)
        when = dt.datetime.fromtimestamp(f.stat().st_mtime)
        label = m.group("tag").replace("_", " ") if m else f.stem
        out.append({
            "name": f.name,
            "label": label,
            "when": when.strftime("%d/%m/%Y %H:%M"),
        })
    return out


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "run"


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    sources = _discover_receipt_sources()
    bank_csvs = _discover_bank_csvs()
    months = _available_whatsapp_months()
    reports = _recent_reports()

    if sources:
        default_folder = sources[0]["path"]
        folder_tiles = "".join(
            f'''<label class="tile{" selected" if i == 0 else ""}" data-group="folder" onclick="selectFolderTile(this)">
                  <input type="radio" name="source_folder_pick" value="{html.escape(s["path"])}" {"checked" if i == 0 else ""}>
                  <div class="tile-title">📁 {html.escape(s["label"])}</div>
                  <div class="tile-sub">{s["count"]} archivo{"s" if s["count"] != 1 else ""}</div>
                  <div class="tile-check"></div>
                </label>'''
            for i, s in enumerate(sources)
        )
    else:
        default_folder = "data/receipts"
        folder_tiles = '<div class="empty-state">No hay carpetas con recibos en <code>data/</code> todavía.</div>'

    folder_datalist = "".join(f'<option value="{html.escape(s["path"])}">' for s in sources)

    if bank_csvs:
        default_bank_csv = bank_csvs[0]["path"]
    else:
        default_bank_csv = "data/bank_statement.csv"
    bank_datalist = "".join(
        f'<option value="{html.escape(b["path"])}">{b["rows"]} filas</option>' for b in bank_csvs
    )

    if months:
        month_options = "".join(
            f'<option value="{m["month"]}">{m["month"]} &middot; {m["count"]} recibos</option>'
            for m in months
        )
    else:
        month_options = '<option value="" disabled selected>(no hay meses cargados -- corré el simulador o generate_whatsapp_demo_data.py)</option>'

    if reports:
        reports_html = "<ul class=\"report-list\">" + "".join(
            f'''<li><a href="/report-files/{html.escape(r["name"])}" target="_blank">{html.escape(r["label"])}</a>
                  <span class="meta">{r["when"]}</span></li>'''
            for r in reports
        ) + "</ul>"
    else:
        reports_html = '<div class="empty-state">Todavía no corriste ninguna reconciliación. El historial va a aparecer acá.</div>'

    total_receipts = sum(s["count"] for s in sources) + sum(m["count"] for m in months)

    return _page(f"""
<header class="top">
  <h1>Agente de Reconciliación <span class="badge">100% local</span></h1>
  <p>El OCR y el cruce contra el banco corren en esta máquina vía QVAC -- nada de esto sale de tu red.
     Elegí de dónde vienen los recibos y reconciliá contra un extracto bancario.</p>
</header>

<div class="grid two">
  <form class="card" method="post" action="/reconcile" onsubmit="return onSubmitForm();">
    <h2>Fuente de recibos</h2>
    <div class="field">
      <div class="source-tiles">
        <label class="tile selected" data-group="source" onclick="selectSource(this)">
          <input type="radio" name="source" value="folder" checked>
          <div class="tile-title">📁 Carpeta local</div>
          <div class="tile-sub">{len(sources)} carpeta{"s" if len(sources) != 1 else ""} disponible{"s" if len(sources) != 1 else ""}</div>
          <div class="tile-check"></div>
        </label>
        <label class="tile" data-group="source" onclick="selectSource(this)">
          <input type="radio" name="source" value="whatsapp">
          <div class="tile-title">💬 WhatsApp (mensual)</div>
          <div class="tile-sub">{len(months)} mes{"es" if len(months) != 1 else ""} cargado{"s" if len(months) != 1 else ""}</div>
          <div class="tile-check"></div>
        </label>
      </div>
    </div>

    <div id="folder-fields" class="field">
      <label class="field-label" for="receipts_dir">Carpeta de recibos</label>
      <input type="text" id="receipts_dir" name="receipts_dir" value="{html.escape(default_folder)}"
             list="folder-options" placeholder="data/receipts">
      <datalist id="folder-options">{folder_datalist}</datalist>
      <div class="source-tiles" style="margin-top:10px">{folder_tiles}</div>
    </div>

    <div id="whatsapp-fields" class="field" style="display:none">
      <label class="field-label" for="whatsapp_month">Mes del dataset</label>
      <select id="whatsapp_month" name="whatsapp_month">{month_options}</select>
      <div class="hint">Recibos ya procesados por QVAC al momento de la ingesta -- esta reconciliación no vuelve a correr OCR.</div>
    </div>

    <div class="field">
      <label class="field-label" for="bank_csv">Extracto bancario (CSV)</label>
      <input type="text" id="bank_csv" name="bank_csv" value="{html.escape(default_bank_csv)}"
             list="bank-options" placeholder="data/bank_statement.csv">
      <datalist id="bank-options">{bank_datalist}</datalist>
    </div>

    <details class="adv">
      <summary>Configuración avanzada de matching</summary>
      <div class="adv-body">
        <div class="two-col">
          <div class="field">
            <label class="field-label" for="date_tolerance_days">Tolerancia de fecha (días)</label>
            <input type="number" id="date_tolerance_days" name="date_tolerance_days" value="3" min="0" max="30">
          </div>
          <div class="field">
            <label class="field-label" for="amount_tolerance">Tolerancia de monto ($)</label>
            <input type="number" id="amount_tolerance" name="amount_tolerance" value="0.01" min="0" step="0.01">
          </div>
          <div class="field">
            <label class="field-label" for="merchant_match_threshold">Umbral fuzzy-match comercio (0-100)</label>
            <input type="number" id="merchant_match_threshold" name="merchant_match_threshold" value="60" min="0" max="100">
          </div>
          <div class="field">
            <label class="field-label" for="large_unmatched_amount">Cargo sin recibo = CRITICAL desde</label>
            <input type="number" id="large_unmatched_amount" name="large_unmatched_amount" value="200" min="0" step="1">
          </div>
        </div>
        <div class="hint">Si tu extracto está en ARS (o cualquier moneda de montos grandes), subí el último valor -- si no, casi todo cargo sin recibo va a salir CRITICAL.</div>
      </div>
    </details>

    <button id="btn" type="submit" class="primary">Reconciliar</button>
  </form>

  <div class="grid" style="gap:20px">
    <div class="card">
      <h2>Estado de los datos</h2>
      <div class="stat-row">
        <span class="stat-pill">{len(sources)} carpetas locales</span>
        <span class="stat-pill">{len(months)} meses WhatsApp</span>
        <span class="stat-pill">{len(bank_csvs)} extractos bancarios</span>
        <span class="stat-pill">{total_receipts} recibos en total</span>
      </div>
      <div class="hint">Generá más datos de prueba con <code>python scripts/generate_sample_data.py</code> (carpeta local) o
        <code>python scripts/generate_whatsapp_demo_data.py</code> (varios meses de WhatsApp, sin necesitar QVAC corriendo).</div>
    </div>
    <div class="card">
      <h2>Reportes recientes</h2>
      {reports_html}
    </div>
  </div>
</div>
""")


@app.post("/reconcile", response_class=HTMLResponse)
def do_reconcile(
    source: str = Form(...),
    receipts_dir: str = Form("data/receipts"),
    whatsapp_month: str = Form(""),
    bank_csv: str = Form("data/bank_statement.csv"),
    date_tolerance_days: int = Form(3),
    amount_tolerance: float = Form(0.01),
    merchant_match_threshold: float = Form(60.0),
    large_unmatched_amount: float = Form(200.0),
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
        tag = whatsapp_month
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
        tag = Path(receipts_dir).name or "carpeta"

    try:
        settings = Settings(
            receipts_dir=Path(receipts_dir),
            bank_csv=Path(bank_csv),
            output_path=Path("reports/reconciliation_report.txt"),
            date_tolerance_days=date_tolerance_days,
            amount_tolerance=amount_tolerance,
            merchant_match_threshold=merchant_match_threshold,
            large_unmatched_amount=large_unmatched_amount,
        )
    except ValueError as exc:
        return _page(f'{back}<div class="error">Configuración avanzada inválida: {exc}</div>')

    result = reconcile(receipts, bank_df, settings)

    run_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_base = REPORTS_DIR / f"reconciliation_{_slugify(tag)}_{run_id}"
    write_text_report(result, output_base.with_suffix(".txt"))
    write_html_report(result, output_base.with_suffix(".html"))
    # Also keep the fixed CLI-documented path pointing at the latest run.
    write_text_report(result, Path("reports/reconciliation_report.txt"))
    write_html_report(result, Path("reports/reconciliation_report.html"))

    return render_html_report(result, nav_html=back)
