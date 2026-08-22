"""CLI entry point: receipts dir -> OCR -> extractor -> matcher (+ bank CSV) -> report."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

from .bank_loader import BankStatementError, load_bank_statement
from .config import Settings
from .extractor import parse_receipt
from .matcher import reconcile
from .models import Receipt
from .ocr_engine import SUPPORTED_EXTENSIONS, OcrEngineError, get_ocr_engine
from .report import render_terminal, write_text_report
from .report_html import write_html_report

logger = logging.getLogger("reconciliation_agent")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reconciliation-agent",
        description=(
            "Privacy-first, 100%% offline reconciliation of physical receipts "
            "against a bank statement export."
        ),
    )
    parser.add_argument(
        "--receipts-dir",
        type=Path,
        default=Path("data/receipts"),
        help="Directory containing receipt images/PDFs (default: data/receipts)",
    )
    parser.add_argument(
        "--bank-csv",
        type=Path,
        default=Path("data/bank_statement.csv"),
        help="Path to the bank statement CSV export (default: data/bank_statement.csv)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/reconciliation_report.txt"),
        help=(
            "Where to write the .txt discrepancy report "
            "(default: reports/reconciliation_report.txt)"
        ),
    )
    parser.add_argument(
        "--date-tolerance-days",
        type=int,
        default=3,
        help=(
            "Max days between receipt date and bank posting date to still be "
            "a candidate match (default: 3)"
        ),
    )
    parser.add_argument(
        "--amount-tolerance",
        type=float,
        default=0.01,
        help="Max absolute $ difference before two amounts count as mismatched (default: 0.01)",
    )
    parser.add_argument(
        "--merchant-threshold",
        type=float,
        default=60.0,
        help="Minimum fuzzy merchant-name match score, 0-100 (default: 60)",
    )
    parser.add_argument(
        "--large-unmatched-amount",
        type=float,
        default=200.0,
        help=(
            "Unmatched bank charges at/above this amount are CRITICAL "
            "instead of WARNING (default: 200)"
        ),
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    return parser


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(message)s",
        handlers=[RichHandler(show_time=False, show_path=False)],
    )


def _discover_receipt_files(receipts_dir: Path) -> list[Path]:
    if not receipts_dir.exists():
        raise FileNotFoundError(f"Receipts directory not found: {receipts_dir}")
    files = sorted(
        p
        for p in receipts_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    return files


def load_receipts(receipts_dir: Path, console: Console) -> list[Receipt]:
    """Run QVAC OCR + extraction over every receipt file in the directory."""
    files = _discover_receipt_files(receipts_dir)
    if not files:
        console.print(f"[yellow]No receipt files found in {receipts_dir}[/yellow]")
        return []

    engine = get_ocr_engine()
    console.print(f"[dim]OCR engine: {engine.name}[/dim] ({len(files)} receipt file(s))\n")

    receipts: list[Receipt] = []
    try:
        for path in files:
            try:
                ocr_result = engine.read(path)
            except OcrEngineError as exc:
                logger.warning("Skipping %s: %s", path.name, exc)
                continue
            receipts.append(parse_receipt(ocr_result, path))
    finally:
        engine.close()
    return receipts


def run(settings: Settings) -> int:
    """Execute the full pipeline. Returns a process exit code."""
    console = Console()

    try:
        receipts = load_receipts(settings.receipts_dir, console)
    except (FileNotFoundError, OcrEngineError) as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        return 1

    try:
        bank_df = load_bank_statement(settings.bank_csv)
    except BankStatementError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        return 1

    result = reconcile(receipts, bank_df, settings)

    render_terminal(result, console=console)
    report_path = write_text_report(result, settings.output_path)
    html_path = write_html_report(result, settings.output_path.with_suffix(".html"))
    console.print(f"\n[dim]Full report written to {report_path} and {html_path}[/dim]")

    # Exit non-zero when critical issues are found -- lets this slot into a
    # CI/cron job that alerts on `echo $?` without parsing the report text.
    return 2 if result.critical_count else 0


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    settings = Settings(
        receipts_dir=args.receipts_dir,
        bank_csv=args.bank_csv,
        output_path=args.output,
        date_tolerance_days=args.date_tolerance_days,
        amount_tolerance=args.amount_tolerance,
        merchant_match_threshold=args.merchant_threshold,
        large_unmatched_amount=args.large_unmatched_amount,
        verbose=args.verbose,
    )
    return run(settings)


if __name__ == "__main__":
    sys.exit(main())
