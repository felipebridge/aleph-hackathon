"""Renders a :class:`ReconciliationResult` as a terminal report and a
plain-text file, per the hackathon brief: "a terminal log or .txt report
flagging ONLY the discrepancies."

Two outputs, one source of truth:
  * A rich, colour-coded terminal view for the live demo.
  * A plain-text file (no ANSI codes) meant to be attached to an email /
    filed as an audit artifact -- so it has to render sensibly with just
    `cat`/Notepad too.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .models import Discrepancy, ReconciliationResult, Severity

_SEVERITY_STYLE = {
    Severity.CRITICAL: "bold red",
    Severity.WARNING: "bold yellow",
    Severity.INFO: "cyan",
}


def render_terminal(result: ReconciliationResult, console: Console | None = None) -> None:
    """Print a colour-coded summary + discrepancy table to the terminal."""
    console = console or Console()

    console.print(
        Panel.fit(
            "[bold]Privacy-First AI Financial Reconciliation Agent[/bold]\n"
            "100% offline -- no receipt or bank data leaves this machine.",
            border_style="blue",
        )
    )

    summary = Table.grid(padding=(0, 2))
    summary.add_column(justify="right", style="bold")
    summary.add_column()
    summary.add_row("Receipts processed:", str(result.receipts_processed))
    summary.add_row("Bank transactions:", str(result.bank_transactions_total))
    summary.add_row("Clean matches:", f"[green]{len(result.matched)}[/green]")
    summary.add_row("Critical alerts:", f"[bold red]{result.critical_count}[/bold red]")
    summary.add_row("Warnings:", f"[bold yellow]{result.warning_count}[/bold yellow]")
    console.print(summary)
    console.print()

    if not result.discrepancies:
        console.print(
            Panel.fit(
                "[bold green]No discrepancies found.[/bold green] "
                "Every receipt reconciles cleanly against the bank statement.",
                border_style="green",
            )
        )
        return

    table = Table(title="Discrepancies", show_lines=True, expand=True)
    table.add_column("Severity", no_wrap=True)
    table.add_column("Type", no_wrap=True)
    table.add_column("Details", ratio=1)

    for d in result.discrepancies:
        style = _SEVERITY_STYLE.get(d.severity, "")
        table.add_row(f"[{style}]{d.severity.value}[/{style}]", d.type.value, d.message)

    console.print(table)


def render_text_report(result: ReconciliationResult, generated_at: dt.datetime | None = None) -> str:
    """Build the plain-text (.txt) report body."""
    generated_at = generated_at or dt.datetime.now()
    lines: list[str] = []
    add = lines.append

    add("=" * 72)
    add("PRIVACY-FIRST AI FINANCIAL RECONCILIATION AGENT")
    add("100% offline run -- no data left this machine.")
    add(f"Generated: {generated_at.isoformat(timespec='seconds')}")
    add("=" * 72)
    add("")
    add("SUMMARY")
    add("-" * 72)
    add(f"Receipts processed:     {result.receipts_processed}")
    add(f"Bank transactions:      {result.bank_transactions_total}")
    add(f"Clean matches:          {len(result.matched)}")
    add(f"CRITICAL alerts:        {result.critical_count}")
    add(f"WARNING alerts:         {result.warning_count}")
    add(f"INFO notes:             {result.info_count}")
    add("")

    if not result.discrepancies:
        add("No discrepancies found. Every receipt reconciles cleanly against")
        add("the bank statement.")
        add("")
        return "\n".join(lines)

    add("DISCREPANCIES (most severe first)")
    add("-" * 72)
    for i, d in enumerate(result.discrepancies, start=1):
        add(f"[{i}] {d.severity.value} - {d.type.value}")
        add(f"    {d.message}")
        if d.receipt is not None:
            add(f"    Source receipt: {d.receipt.source_file}")
        add("")

    if result.matched:
        add("RECONCILED (informational, no action needed)")
        add("-" * 72)
        for m in result.matched:
            add(
                f"OK  {m.receipt.merchant!r} ${m.receipt.amount:,.2f}  "
                f"<-> txn {m.bank_txn.transaction_id} (${m.bank_txn.amount:,.2f})"
            )
            for note in m.notes:
                add(f"    note: {note}")
        add("")

    return "\n".join(lines)


def write_text_report(result: ReconciliationResult, output_path: Path) -> Path:
    """Write the plain-text report to disk, creating parent dirs as needed."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_text_report(result), encoding="utf-8")
    return output_path
