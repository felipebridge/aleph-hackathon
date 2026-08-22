"""Unit tests for the plain-text and HTML report renderers."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from reconciliation_agent.models import (
    BankTransaction,
    Discrepancy,
    DiscrepancyType,
    MatchedPair,
    Receipt,
    ReconciliationResult,
    Severity,
)
from reconciliation_agent.report import render_text_report, write_text_report
from reconciliation_agent.report_html import render_html_report, write_html_report


def _sample_result() -> ReconciliationResult:
    receipt = Receipt(
        source_file=Path("02_office_depot.png"),
        merchant="Office Depot",
        amount=45.99,
        txn_date=dt.date(2026, 8, 11),
    )
    bank_txn = BankTransaction(
        transaction_id="TXN-1002",
        txn_date=dt.date(2026, 8, 11),
        amount=459.90,
        merchant="Office Depot",
        description="OFFICE DEPOT #221",
    )
    matched_receipt = Receipt(
        source_file=Path("01_starbucks.png"),
        merchant="Starbucks",
        amount=4.75,
        txn_date=dt.date(2026, 8, 10),
    )
    matched_bank_txn = BankTransaction(
        transaction_id="TXN-1001",
        txn_date=dt.date(2026, 8, 10),
        amount=4.75,
        merchant="Starbucks",
        description="STARBUCKS STORE #4521",
    )
    return ReconciliationResult(
        matched=[MatchedPair(receipt=matched_receipt, bank_txn=matched_bank_txn, date_diff_days=0)],
        discrepancies=[
            Discrepancy(
                type=DiscrepancyType.AMOUNT_MISMATCH,
                severity=Severity.CRITICAL,
                message=(
                    "ALERT: Receipt from 'Office Depot' indicates $45.99, "
                    "but bank statement charged $459.90."
                ),
                receipt=receipt,
                bank_txn=bank_txn,
                delta_amount=413.91,
            )
        ],
        receipts_processed=2,
        bank_transactions_total=2,
    )


class TestTextReport:
    def test_includes_summary_counts_and_discrepancy_message(self):
        text = render_text_report(_sample_result())

        assert "Receipts processed:     2" in text
        assert "CRITICAL alerts:        1" in text
        assert "$45.99" in text and "$459.90" in text

    def test_no_discrepancies_renders_a_clean_bill(self):
        text = render_text_report(
            ReconciliationResult(receipts_processed=1, bank_transactions_total=1)
        )
        assert "No discrepancies found" in text

    def test_write_text_report_creates_file(self, tmp_path: Path):
        out_path = write_text_report(_sample_result(), tmp_path / "out" / "report.txt")
        assert out_path.exists()
        assert "AMOUNT_MISMATCH" in out_path.read_text(encoding="utf-8")


class TestHtmlReport:
    def test_includes_summary_counts_and_is_valid_shell(self):
        html_text = render_html_report(_sample_result())

        assert html_text.startswith("<!DOCTYPE html>")
        assert "<html" in html_text and "</html>" in html_text
        assert "Office Depot" in html_text

    def test_escapes_message_content(self):
        result = _sample_result()
        result.discrepancies[0].message = "<script>alert(1)</script>"
        html_text = render_html_report(result)
        assert "<script>alert(1)</script>" not in html_text
        assert "&lt;script&gt;" in html_text

    def test_write_html_report_creates_file(self, tmp_path: Path):
        out_path = write_html_report(_sample_result(), tmp_path / "out" / "report.html")
        assert out_path.exists()
        assert "<!DOCTYPE html>" in out_path.read_text(encoding="utf-8")
