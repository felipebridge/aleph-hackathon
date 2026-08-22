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


UBER_AR_TEXT = """\
Uber
Jul 2, 2026
8:14 AM
■ Uber One
Thanks for riding, Martina
We hope you enjoyed your ride.
Total   ARS 3,120.00
PROMO
ARS 312.00
Uber One credits earned
Trip fare   ARS 3,880.00
Booking Fee   ARS 300.00
Promotion   -ARS 650.00
Uber One Credits   -ARS 410.00
Payments
Mercado Pago
7/2/26 8:14 AM
ARS 3,120.00
"""

AFIP_FACTURA_TEXT = """\
ORIGINAL (EJEMPLO)
B
COD. 06
PETROSUR COMBUSTIBLES S.A.   FACTURA (MUESTRA)
Razón Social: PETROSUR COMBUSTIBLES S.A.
Domicilio Fiscal: Ruta Provincial 8 Km 45, Pilar, Buenos Aires
Condición frente al IVA: IVA Responsable Inscripto
Fecha de Emisión: 20/07/2026
Nafta Super -   1.00   unidades   130.79   0.00   0.00   4,630.00
Subtotal: $ 3,826.45
Importe Otros Tributos: $ 0.00
Importe Total: $ 4,630.00
"""


class TestArsAmounts:
    def test_parses_ars_prefixed_total(self):
        assert extract_amount(UBER_AR_TEXT) == 3120.00

    def test_ars_total_wins_over_larger_trip_fare(self):
        # Trip fare is 3880 > total 3120, but total-keyword line must win
        assert extract_amount(UBER_AR_TEXT) == 3120.00

    def test_afip_factura_importe_total(self):
        assert extract_amount(AFIP_FACTURA_TEXT) == 4630.00

    def test_afip_subtotal_not_returned_as_total(self):
        # Subtotal 3826.45 must be skipped; Importe Total 4630.00 wins
        assert extract_amount(AFIP_FACTURA_TEXT) != 3826.45


class TestAfipMerchantExtraction:
    def test_strips_factura_suffix_from_merchant_line(self):
        assert extract_merchant(AFIP_FACTURA_TEXT) == "Petrosur Combustibles S.A."

    def test_filters_original_ejemplo_noise_line(self):
        # "ORIGINAL (EJEMPLO)" must never be returned as merchant
        assert extract_merchant(AFIP_FACTURA_TEXT) != "Original (Ejemplo)"

    def test_filters_cod_noise_line(self):
        text = "COD. 06\nRappi\nTotal ARS 2,940.00\n07/14/2026"
        assert extract_merchant(text) == "Rappi"

    def test_uber_ar_receipt_merchant(self):
        assert extract_merchant(UBER_AR_TEXT) == "Uber"


class TestAfipDateExtraction:
    def test_parses_dd_mm_yyyy_unambiguous(self):
        # 20/07/2026 — day=20 > 12, so unambiguously DD/MM/YYYY
        assert extract_date(AFIP_FACTURA_TEXT) == dt.date(2026, 7, 20)

    def test_parses_uber_ar_short_date(self):
        # "7/2/26 8:14 AM" — ambiguous, defaults to US MM/DD → Feb 7 or Jul 2?
        # dateutil with dayfirst=False → 2026-07-02
        assert extract_date(UBER_AR_TEXT) == dt.date(2026, 7, 2)


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
