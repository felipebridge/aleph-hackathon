"""Unit tests for the OCR-text -> structured-fields extraction heuristics."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from reconciliation_agent.extractor import (
    _strip_layout_markup,
    extract_amount,
    extract_date,
    extract_merchant,
    parse_receipt,
)
from reconciliation_agent.models import OcrResult

# Captured verbatim from a real QVAC OCR_3B_MULTIMODAL_Q4_0 run against
# 01_starbucks.png: bounding-box prefixes, <table> tags around line items,
# a duplicated/hallucinated $0.00 TOTAL line before the real one, and a
# leaked self-critique sentence the model was never asked for.
OCR_3B_REAL_OUTPUT = """\
The OCR should not have output any underscores. Outputting `____` constitutes an error under Rule 2, as it hallucinates placeholder symbols where none are semantically intended. Hence, the OCR result is inconsistent with the Ground Truth.
text [50, 62, 480, 117]Starbucks Coffee
text [50, 134, 977, 190]123 Market Street, San Francisco CA
text [50, 206, 348, 261]Store #4521
table [50, 352, 912, 495]<table>Grande Latte4.25Almond Milk Sub0.50</table>
table [50, 566, 922, 621]<table>Subtotal4.75</table>
table [50, 638, 922, 692]<table>Tax0.00</table>
table [50, 709, 922, 764]<table>TOTAL$0.00</table>
table [50, 781, 922, 835]<table>TOTAL$4.75</table>
text [50, 851, 560, 903]08/10/2026 09:14 AM
text [50, 916, 658, 978]Thank you for visiting!
"""

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

    def test_handles_euro_symbol(self):
        text = "Cafe Berlin\nTOTAL   €12.50\n"
        assert extract_amount(text) == 12.50

    def test_handles_eu_thousands_and_decimal_comma(self):
        text = "Berlin Electronics\nTOTAL   1.234,56\n"
        assert extract_amount(text) == 1234.56

    def test_falls_back_to_bare_integer_total_when_no_cents_printed(self):
        text = "Corner Store\nItem A   20\nItem B   30\nTOTAL   $50\n"
        assert extract_amount(text) == 50.0

    def test_bare_integer_fallback_never_outranks_a_cents_precise_amount(self):
        text = "Diner\nTOTAL DUE (approx) 46\nTOTAL   $45.99\n"
        assert extract_amount(text) == 45.99


class TestExtractDate:
    def test_parses_slash_date(self):
        assert extract_date(STARBUCKS_TEXT) == dt.date(2026, 8, 10)

    def test_parses_iso_date(self):
        assert extract_date("Invoice\n2026-08-09\nTOTAL 89.00") == dt.date(2026, 8, 9)

    def test_parses_month_name_date(self):
        assert extract_date("Receipt\nAug 22, 2026\nTOTAL 10.00") == dt.date(2026, 8, 22)

    def test_returns_none_when_no_date_present(self):
        assert extract_date("Merchant\nTOTAL 10.00") is None

    def test_unambiguous_day_first_slash_date_overrides_us_default(self):
        assert extract_date("Receipt\n22/08/2026\nTOTAL 10.00") == dt.date(2026, 8, 22)

    def test_ambiguous_slash_date_defaults_to_us_month_day_order(self):
        assert extract_date("Receipt\n08/10/2026\nTOTAL 10.00") == dt.date(2026, 8, 10)


class TestExtractMerchant:
    def test_takes_first_meaningful_line(self):
        assert extract_merchant(STARBUCKS_TEXT) == "Starbucks Coffee"

    def test_skips_noise_lines_like_receipt_header(self):
        text = "RECEIPT\nCustomer Copy\nCostco Wholesale\nTOTAL 10.00"
        assert extract_merchant(text) == "Costco Wholesale"

    def test_skips_purely_symbolic_lines(self):
        text = "========\nUber\nTOTAL 10.00"
        assert extract_merchant(text) == "Uber"

    def test_prefers_store_name_over_leading_address_line_when_both_present(self):
        text = "123 Market Street, San Francisco CA\nStarbucks Coffee\nTOTAL 4.75"
        assert extract_merchant(text) == "Starbucks Coffee"

    def test_falls_back_to_address_line_when_nothing_better_exists(self):
        text = "123 Market Street\nTOTAL 4.75"
        assert extract_merchant(text) == "123 Market Street"

    def test_prefers_store_name_over_leaked_model_commentary_sentence(self):
        # Real QVAC OCR_3B output occasionally leaks a meta-commentary
        # sentence ahead of the actual transcription -- a full sentence is
        # never mistaken for the store name.
        text = "There is no actual character output to extract.\nShell\nTOTAL 52.00"
        assert extract_merchant(text) == "Shell"


class TestParseReceipt:
    def test_full_pipeline_produces_fully_parsed_receipt(self, tmp_path: Path):
        ocr_result = OcrResult(text=STARBUCKS_TEXT, engine_name="qvac", confidence=1.0)
        receipt = parse_receipt(ocr_result, tmp_path / "01_starbucks.png")

        assert receipt.is_fully_parsed
        assert receipt.merchant == "Starbucks Coffee"
        assert receipt.amount == 4.75
        assert receipt.txn_date == dt.date(2026, 8, 10)
        assert receipt.ocr_engine == "qvac"

    def test_partial_extraction_is_marked_not_fully_parsed(self, tmp_path: Path):
        ocr_result = OcrResult(text="Illegible smudge", engine_name="qvac")
        receipt = parse_receipt(ocr_result, tmp_path / "bad.png")

        assert not receipt.is_fully_parsed

    def test_handles_real_qvac_output_with_layout_markup_and_hallucinated_line(
        self, tmp_path: Path
    ):
        # Regression test pinned to an actual (messy) QVAC response, not a
        # hand-cleaned fixture -- see OCR_3B_REAL_OUTPUT above.
        ocr_result = OcrResult(text=OCR_3B_REAL_OUTPUT, engine_name="qvac")
        receipt = parse_receipt(ocr_result, tmp_path / "01_starbucks.png")

        assert receipt.is_fully_parsed
        assert receipt.merchant == "Starbucks Coffee"
        # The model hallucinated a spurious "TOTAL$0.00" before the real
        # total -- extract_amount's "last total line wins" rule picks the
        # correct one printed last, exactly as it would on a real receipt.
        assert receipt.amount == 4.75
        assert receipt.txn_date == dt.date(2026, 8, 10)


class TestStripLayoutMarkup:
    def test_removes_bounding_box_prefix(self):
        assert _strip_layout_markup("text [50, 62, 480, 117]Starbucks Coffee") == "Starbucks Coffee"

    def test_removes_table_tags(self):
        assert _strip_layout_markup("<table>Subtotal4.75</table>") == " Subtotal4.75 "

    def test_leaves_plain_text_untouched(self):
        assert _strip_layout_markup(STARBUCKS_TEXT) == STARBUCKS_TEXT.rstrip("\n")
