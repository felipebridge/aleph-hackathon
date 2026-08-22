"""Unit tests for the OCR-text -> structured-fields extraction heuristics."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from reconciliation_agent.extractor import (
    extract_amount,
    extract_date,
    extract_merchant,
    parse_receipt,
)
from reconciliation_agent.models import OcrResult

STARBUCKS_TEXT = """\
Starbucks Coffee
123 Market Street, San Francisco CA
Store #4521
--------------------------------
Grande Latte                4.25
Almond Milk Sub              0.50
--------------------------------
Subtotal                     4.75
Tax                          0.00
TOTAL                       $4.75
08/10/2026 09:14 AM
Thank you for visiting!
"""


class TestExtractAmount:
    def test_prefers_total_line_over_line_items(self):
        assert extract_amount(STARBUCKS_TEXT) == 4.75

    def test_falls_back_to_largest_amount_when_no_total_keyword(self):
        text = "Some Store\nItem A   10.00\nItem B   25.50\n"
        assert extract_amount(text) == 25.50

    def test_ignores_subtotal_and_tax_lines_when_total_present(self):
        text = "Shop\nSubtotal   999.99\nTax   1.00\nTOTAL   45.00\n"
        assert extract_amount(text) == 45.00

    def test_returns_none_when_no_amount_present(self):
        assert extract_amount("No numbers here at all") is None

    def test_handles_thousands_separator(self):
        text = "Wire Transfer\nTOTAL   $1,200.00\n"
        assert extract_amount(text) == 1200.00


class TestExtractDate:
    def test_parses_slash_date(self):
        assert extract_date(STARBUCKS_TEXT) == dt.date(2026, 8, 10)

    def test_parses_iso_date(self):
        assert extract_date("Invoice\n2026-08-09\nTOTAL 89.00") == dt.date(2026, 8, 9)

    def test_parses_month_name_date(self):
        assert extract_date("Receipt\nAug 22, 2026\nTOTAL 10.00") == dt.date(2026, 8, 22)

    def test_returns_none_when_no_date_present(self):
        assert extract_date("Merchant\nTOTAL 10.00") is None


class TestExtractMerchant:
    def test_takes_first_meaningful_line(self):
        assert extract_merchant(STARBUCKS_TEXT) == "Starbucks Coffee"

    def test_skips_noise_lines_like_receipt_header(self):
        text = "RECEIPT\nCustomer Copy\nCostco Wholesale\nTOTAL 10.00"
        assert extract_merchant(text) == "Costco Wholesale"

    def test_skips_purely_symbolic_lines(self):
        text = "========\nUber\nTOTAL 10.00"
        assert extract_merchant(text) == "Uber"


class TestParseReceipt:
    def test_full_pipeline_produces_fully_parsed_receipt(self, tmp_path: Path):
        ocr_result = OcrResult(text=STARBUCKS_TEXT, engine_name="mock", confidence=1.0)
        receipt = parse_receipt(ocr_result, tmp_path / "01_starbucks.png")

        assert receipt.is_fully_parsed
        assert receipt.merchant == "Starbucks Coffee"
        assert receipt.amount == 4.75
        assert receipt.txn_date == dt.date(2026, 8, 10)
        assert receipt.ocr_engine == "mock"

    def test_partial_extraction_is_marked_not_fully_parsed(self, tmp_path: Path):
        ocr_result = OcrResult(text="Illegible smudge", engine_name="mock")
        receipt = parse_receipt(ocr_result, tmp_path / "bad.png")

        assert not receipt.is_fully_parsed
