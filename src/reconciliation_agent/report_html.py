"""Generates a self-contained HTML reconciliation report.

No external CSS/JS dependencies — everything is inline so the file can be
opened offline on any machine, emailed as an attachment, or archived.
"""

from __future__ import annotations

import datetime as dt
import html
from pathlib import Path

from .models import DiscrepancyType, ReconciliationResult, Severity

_SEVERITY_COLOR = {
    Severity.CRITICAL: "#c0392b",
    Severity.WARNING: "#d68910",
    Severity.INFO: "#1a5276",
}

_SEVERITY_BG = {
    Severity.CRITICAL: "#fdf2f2",
    Severity.WARNING: "#fef9e7",
    Severity.INFO: "#eaf4fb",
}

_TYPE_LABEL = {
    DiscrepancyType.AMOUNT_MISMATCH: "Amount Mismatch",
    DiscrepancyType.DATE_MISMATCH: "Date Mismatch",
    DiscrepancyType.MISSING_IN_BANK: "Missing in Bank",
    DiscrepancyType.UNACCOUNTED_CHARGE: "Unaccounted Charge",
    DiscrepancyType.DUPLICATE_RECEIPT: "Duplicate Receipt",
}

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #f4f6f9; color: #2c3e50; padding: 32px 24px; }
.container { max-width: 960px; margin: 0 auto; }
header { background: #1a252f; color: #fff; border-radius: 10px;
         padding: 28px 32px; margin-bottom: 28px; }
header h1 { font-size: 1.5rem; font-weight: 700; margin-bottom: 6px; }
header p  { font-size: 0.85rem; color: #aab7b8; }
.badge { display: inline-block; background: #27ae60; color: #fff;
         font-size: 0.7rem; font-weight: 600; padding: 2px 8px;
         border-radius: 20px; margin-left: 8px; vertical-align: middle; }
.summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
           gap: 16px; margin-bottom: 28px; }
.stat { background: #fff; border-radius: 8px; padding: 20px 24px;
        box-shadow: 0 1px 4px rgba(0,0,0,.08); text-align: center; }
.stat .value { font-size: 2rem; font-weight: 700; line-height: 1; }
.stat .label { font-size: 0.75rem; color: #7f8c8d; margin-top: 4px; text-transform: uppercase; }
.stat.green .value  { color: #27ae60; }
.stat.red .value    { color: #c0392b; }
.stat.yellow .value { color: #d68910; }
.stat.blue .value   { color: #2980b9; }
section { margin-bottom: 28px; }
section h2 { font-size: 1rem; font-weight: 700; margin-bottom: 12px;
             color: #566573; text-transform: uppercase; letter-spacing: .05em; }
table { width: 100%; border-collapse: collapse; background: #fff;
        border-radius: 8px; overflow: hidden;
        box-shadow: 0 1px 4px rgba(0,0,0,.08); }
th { background: #2c3e50; color: #fff; text-align: left;
     padding: 12px 16px; font-size: 0.8rem; text-transform: uppercase; letter-spacing: .04em; }
td { padding: 12px 16px; font-size: 0.875rem; border-bottom: 1px solid #eaecee; vertical-align: top; }
tr:last-child td { border-bottom: none; }
.sev { font-weight: 700; font-size: 0.75rem; padding: 3px 10px;
       border-radius: 20px; white-space: nowrap; display: inline-block; }
.matched-table td { color: #2e7d52; }
.matched-table tr:nth-child(even) { background: #f9fef9; }
footer { text-align: center; font-size: 0.75rem; color: #aab7b8; margin-top: 16px; }
"""


def _sev_badge(severity: Severity) -> str:
    color = _SEVERITY_COLOR[severity]
    bg = _SEVERITY_BG[severity]
    return (
        f'<span class="sev" style="color:{color};background:{bg};border:1px solid {color}88">'
        f"{html.escape(severity.value)}</span>"
    )


def render_html_report(
    result: ReconciliationResult,
    generated_at: dt.datetime | None = None,
) -> str:
    generated_at = generated_at or dt.datetime.now()
    ts = generated_at.strftime("%Y-%m-%d %H:%M:%S")

    disc_rows = ""
    for d in result.discrepancies:
        source = html.escape(d.receipt.display_name) if d.receipt else "—"
        txn_id = html.escape(d.bank_txn.transaction_id) if d.bank_txn else "—"
        delta = ""
        if d.delta_amount is not None:
            delta = f'<br><small style="color:#7f8c8d">Δ ${d.delta_amount:+,.2f}</small>'
        disc_rows += (
            f"<tr>"
            f"<td>{_sev_badge(d.severity)}</td>"
            f"<td>{html.escape(_TYPE_LABEL.get(d.type, d.type.value))}</td>"
            f"<td>{html.escape(d.message)}{delta}</td>"
            f"<td>{source}</td>"
            f"<td>{txn_id}</td>"
            f"</tr>\n"
        )

    disc_section = ""
    if disc_rows:
        disc_section = f"""
<section>
  <h2>Discrepancies ({len(result.discrepancies)})</h2>
  <table>
    <thead><tr>
      <th>Severity</th><th>Type</th><th>Details</th><th>Receipt file</th><th>Bank txn</th>
    </tr></thead>
    <tbody>{disc_rows}</tbody>
  </table>
</section>"""
    else:
        disc_section = """
<section>
  <div style="background:#eafaf1;border:1px solid #27ae60;border-radius:8px;padding:20px 24px;color:#1e8449;">
    <strong>No discrepancies found.</strong> Every receipt reconciles cleanly against the bank statement.
  </div>
</section>"""

    matched_rows = ""
    for m in result.matched:
        notes = "; ".join(m.notes) if m.notes else "—"
        matched_rows += (
            f"<tr>"
            f"<td>{html.escape(m.receipt.merchant or '—')}</td>"
            f"<td>${m.receipt.amount:,.2f}</td>"
            f"<td>{html.escape(m.bank_txn.transaction_id)}</td>"
            f"<td>${m.bank_txn.amount:,.2f}</td>"
            f"<td>{html.escape(str(m.bank_txn.txn_date))}</td>"
            f"<td>{html.escape(notes)}</td>"
            f"</tr>\n"
        )

    matched_section = ""
    if matched_rows:
        matched_section = f"""
<section>
  <h2>Clean matches ({len(result.matched)})</h2>
  <table class="matched-table">
    <thead><tr>
      <th>Merchant</th><th>Receipt $</th><th>Bank txn</th><th>Bank $</th><th>Date</th><th>Notes</th>
    </tr></thead>
    <tbody>{matched_rows}</tbody>
  </table>
</section>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Reconciliation Report — {ts}</title>
  <style>{_CSS}</style>
</head>
<body>
<div class="container">
  <header>
    <h1>Financial Reconciliation Report
      <span class="badge">100% offline</span>
    </h1>
    <p>Generated: {ts} &nbsp;·&nbsp; No receipt or bank data left this machine.</p>
  </header>

  <div class="summary">
    <div class="stat blue">
      <div class="value">{result.receipts_processed}</div>
      <div class="label">Receipts</div>
    </div>
    <div class="stat blue">
      <div class="value">{result.bank_transactions_total}</div>
      <div class="label">Bank txns</div>
    </div>
    <div class="stat green">
      <div class="value">{len(result.matched)}</div>
      <div class="label">Clean matches</div>
    </div>
    <div class="stat red">
      <div class="value">{result.critical_count}</div>
      <div class="label">Critical alerts</div>
    </div>
    <div class="stat yellow">
      <div class="value">{result.warning_count}</div>
      <div class="label">Warnings</div>
    </div>
  </div>

  {disc_section}
  {matched_section}

  <footer>Privacy-First AI Financial Reconciliation Agent &nbsp;·&nbsp; {ts}</footer>
</div>
</body>
</html>"""


def write_html_report(result: ReconciliationResult, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html_report(result), encoding="utf-8")
    return output_path
