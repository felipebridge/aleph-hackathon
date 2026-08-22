"""Unit tests for the core reconciliation business logic.

These are the tests that matter most for the Product Manager's business
rules: they pin down exactly what counts as a clean match vs. each flavour
of discrepancy, using small hand-built fixtures instead of the sample data
generator so each scenario is isolated and easy to reason about.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from reconciliation_agent.config import Settings
from reconciliation_agent.matcher import reconcile
from reconciliation_agent.models import DiscrepancyType, Receipt, Severity


def make_settings(**overrides) -> Settings:
    defaults = dict(
        receipts_dir=Path("data/receipts"),
        bank_csv=Path("data/bank_statement.csv"),
        output_path=Path("reports/out.txt"),
    )
    defaults.update(overrides)
    return Settings(**defaults)


def make_bank_df(rows: list[dict]) -> pd.DataFrame:
    columns = ["transaction_id", "date", "amount", "merchant", "description"]
    if not rows:
        return pd.DataFrame(columns=columns)
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def make_receipt(merchant: str, amount: float, txn_date: dt.date, filename: str = "r.png") -> Receipt:
    return Receipt(
        source_file=Path(filename),
        merchant=merchant,
        amount=amount,
        txn_date=txn_date,
        raw_text="",
        ocr_engine="mock",
    )


class TestCleanMatch:
    def test_exact_match_produces_no_discrepancy(self):
        bank_df = make_bank_df(
            [
                dict(
                    transaction_id="TXN-1",
                    date="2026-08-10",
                    amount=4.75,
                    merchant="Starbucks",
                    description="STARBUCKS STORE #4521",
                )
            ]
        )
        receipt = make_receipt("Starbucks Coffee", 4.75, dt.date(2026, 8, 10))

        result = reconcile([receipt], bank_df, make_settings())

        assert len(result.matched) == 1
        assert result.discrepancies == []

    def test_date_within_tolerance_matches_with_a_note(self):
        bank_df = make_bank_df(
            [dict(transaction_id="TXN-1", date="2026-08-17", amount=610.0, merchant="Delta Air Lines", description="")]
        )
        receipt = make_receipt("Delta Air Lines", 610.0, dt.date(2026, 8, 14))

        result = reconcile([receipt], bank_df, make_settings(date_tolerance_days=3))

        assert len(result.matched) == 1
        assert result.matched[0].date_diff_days == 3
        assert result.matched[0].notes  # date drift explanation present
        assert result.discrepancies == []

    def test_date_outside_tolerance_does_not_match(self):
        bank_df = make_bank_df(
            [dict(transaction_id="TXN-1", date="2026-08-20", amount=610.0, merchant="Delta Air Lines", description="")]
        )
        receipt = make_receipt("Delta Air Lines", 610.0, dt.date(2026, 8, 14))

        result = reconcile([receipt], bank_df, make_settings(date_tolerance_days=3))

        assert result.matched == []
        types = [d.type for d in result.discrepancies]
        # The receipt has no candidate within tolerance, AND the untouched
        # bank row is itself now unaccounted-for -- both are correct findings.
        assert DiscrepancyType.MISSING_IN_BANK in types
        assert DiscrepancyType.UNACCOUNTED_CHARGE in types


class TestAmountMismatch:
    def test_transposed_amount_flagged_critical(self):
        bank_df = make_bank_df(
            [dict(transaction_id="TXN-1", date="2026-08-11", amount=459.90, merchant="Office Depot", description="")]
        )
        receipt = make_receipt("Office Depot", 45.99, dt.date(2026, 8, 11))

        result = reconcile([receipt], bank_df, make_settings())

        assert result.matched == []
        assert len(result.discrepancies) == 1
        d = result.discrepancies[0]
        assert d.type is DiscrepancyType.AMOUNT_MISMATCH
        assert d.severity is Severity.CRITICAL
        assert d.delta_amount == pytest.approx(459.90 - 45.99)
        assert "45.99" in d.message and "459.90" in d.message

    def test_amount_within_tolerance_is_not_a_mismatch(self):
        bank_df = make_bank_df(
            [dict(transaction_id="TXN-1", date="2026-08-11", amount=45.995, merchant="Office Depot", description="")]
        )
        receipt = make_receipt("Office Depot", 45.99, dt.date(2026, 8, 11))

        result = reconcile([receipt], bank_df, make_settings(amount_tolerance=0.01))

        assert len(result.matched) == 1
        assert result.discrepancies == []


class TestMissingInBank:
    def test_receipt_with_no_bank_charge_flagged_warning(self):
        bank_df = make_bank_df([])  # nothing on the statement at all
        receipt = make_receipt("Amazon Web Services", 89.00, dt.date(2026, 8, 9))

        result = reconcile([receipt], bank_df, make_settings())

        assert len(result.discrepancies) == 1
        assert result.discrepancies[0].type is DiscrepancyType.MISSING_IN_BANK
        assert result.discrepancies[0].severity is Severity.WARNING

    def test_partially_parsed_receipt_is_flagged_not_matched(self):
        bank_df = make_bank_df([])
        unparsed = Receipt(
            source_file=Path("blurry.png"), merchant=None, amount=None, txn_date=None, raw_text="???"
        )

        result = reconcile([unparsed], bank_df, make_settings())

        assert result.matched == []
        assert len(result.discrepancies) == 1
        assert "manual review" in result.discrepancies[0].message


class TestUnaccountedCharge:
    def test_large_unmatched_bank_charge_is_critical(self):
        bank_df = make_bank_df(
            [dict(transaction_id="TXN-1", date="2026-08-16", amount=1200.0, merchant="Wire Transfer", description="")]
        )
        result = reconcile([], bank_df, make_settings(large_unmatched_amount=200.0))

        assert len(result.discrepancies) == 1
        d = result.discrepancies[0]
        assert d.type is DiscrepancyType.UNACCOUNTED_CHARGE
        assert d.severity is Severity.CRITICAL

    def test_small_unmatched_bank_charge_is_warning(self):
        bank_df = make_bank_df(
            [dict(transaction_id="TXN-1", date="2026-08-18", amount=6.50, merchant="Vending Co", description="")]
        )
        result = reconcile([], bank_df, make_settings(large_unmatched_amount=200.0))

        assert result.discrepancies[0].severity is Severity.WARNING


class TestDuplicateReceipt:
    def test_second_identical_receipt_flagged_as_duplicate(self):
        bank_df = make_bank_df(
            [dict(transaction_id="TXN-1", date="2026-08-15", amount=52.0, merchant="Shell", description="")]
        )
        first = make_receipt("Shell", 52.0, dt.date(2026, 8, 15), "07_shell.png")
        second = make_receipt("Shell", 52.0, dt.date(2026, 8, 15), "08_shell_dup.png")

        result = reconcile([first, second], bank_df, make_settings())

        assert len(result.matched) == 1
        assert result.matched[0].receipt is first
        assert len(result.discrepancies) == 1
        assert result.discrepancies[0].type is DiscrepancyType.DUPLICATE_RECEIPT
        assert result.discrepancies[0].severity is Severity.CRITICAL
        assert result.discrepancies[0].receipt is second


class TestFullScenario:
    """Mirrors scripts/generate_sample_data.py end to end at the matcher level."""

    def test_mixed_scenario_counts(self):
        bank_df = make_bank_df(
            [
                dict(transaction_id="TXN-1001", date="2026-08-10", amount=4.75, merchant="Starbucks", description=""),
                dict(transaction_id="TXN-1002", date="2026-08-11", amount=459.90, merchant="Office Depot", description=""),
                dict(transaction_id="TXN-1006", date="2026-08-15", amount=52.0, merchant="Shell", description=""),
                dict(transaction_id="TXN-1007", date="2026-08-16", amount=1200.0, merchant="Wire Transfer", description=""),
                dict(transaction_id="TXN-1008", date="2026-08-18", amount=6.50, merchant="Vending Co", description=""),
            ]
        )
        receipts = [
            make_receipt("Starbucks Coffee", 4.75, dt.date(2026, 8, 10), "01.png"),
            make_receipt("Office Depot", 45.99, dt.date(2026, 8, 11), "02.png"),
            make_receipt("Amazon Web Services", 89.00, dt.date(2026, 8, 9), "04.png"),
            make_receipt("Shell", 52.0, dt.date(2026, 8, 15), "07.png"),
            make_receipt("Shell", 52.0, dt.date(2026, 8, 15), "08.png"),
        ]

        result = reconcile(receipts, bank_df, make_settings())

        types = sorted(d.type.value for d in result.discrepancies)
        assert types == sorted(
            [
                DiscrepancyType.AMOUNT_MISMATCH.value,
                DiscrepancyType.MISSING_IN_BANK.value,
                DiscrepancyType.DUPLICATE_RECEIPT.value,
                DiscrepancyType.UNACCOUNTED_CHARGE.value,
                DiscrepancyType.UNACCOUNTED_CHARGE.value,
            ]
        )
        assert len(result.matched) == 2  # Starbucks + first Shell receipt
        assert result.critical_count == 3  # amount mismatch + duplicate + wire transfer
        assert result.warning_count == 2  # missing-in-bank (AWS) + small unaccounted (vending)
