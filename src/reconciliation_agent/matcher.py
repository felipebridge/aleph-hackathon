"""Core reconciliation logic: receipts vs. bank statement.

Pure Python/pandas, no OCR or I/O, so it's easy to unit test with
hand-built fixtures. See `reconcile()` for the matching algorithm.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta

import pandas as pd
from rapidfuzz import fuzz

from .config import Settings
from .models import (
    BankTransaction,
    Discrepancy,
    DiscrepancyType,
    MatchedPair,
    Receipt,
    ReconciliationResult,
    Severity,
)

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}

# Strips store numbers, phone/reference digit runs, and punctuation before
# fuzzy matching -- lets "Starbucks Coffee" score well against "STARBUCKS STORE #4521".
_MERCHANT_NOISE_RE = re.compile(r"#\d+|\bstore\b|\b\d{3,}\b|[^a-z0-9 ]", re.IGNORECASE)


def _normalize_merchant_name(value: str) -> str:
    normalized = _MERCHANT_NOISE_RE.sub(" ", value.lower())
    return re.sub(r"\s+", " ", normalized).strip()


def _merchant_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    normalized_a, normalized_b = _normalize_merchant_name(a), _normalize_merchant_name(b)
    if not normalized_a or not normalized_b:
        return 0.0
    return fuzz.token_sort_ratio(normalized_a, normalized_b)


def _date_window(receipt: Receipt, settings: Settings) -> tuple:
    lo = receipt.txn_date - timedelta(days=settings.date_tolerance_days)
    hi = receipt.txn_date + timedelta(days=settings.date_tolerance_days)
    return lo, hi


def _find_best_candidate(
    receipt: Receipt,
    bank_df: pd.DataFrame,
    claimed: set[str],
    settings: Settings,
) -> tuple[pd.Series | None, float]:
    """Return (best matching unclaimed bank row, similarity score) or (None, 0)."""
    date_lo, date_hi = _date_window(receipt, settings)

    candidates = bank_df[
        (~bank_df["transaction_id"].isin(claimed))
        & (bank_df["date"] >= date_lo)
        & (bank_df["date"] <= date_hi)
    ].copy()

    if candidates.empty:
        return None, 0.0

    candidates["_merchant_score"] = candidates.apply(
        lambda row: max(
            _merchant_similarity(receipt.merchant, row["merchant"]),
            _merchant_similarity(receipt.merchant, row["description"]),
        ),
        axis=1,
    )
    candidates = candidates[candidates["_merchant_score"] >= settings.merchant_match_threshold]
    if candidates.empty:
        return None, 0.0

    candidates["_amount_diff"] = (candidates["amount"] - receipt.amount).abs()
    candidates = candidates.sort_values(
        by=["_merchant_score", "_amount_diff"], ascending=[False, True]
    )
    best = candidates.iloc[0]
    return best, float(best["_merchant_score"])


def _find_amount_date_only_match(
    receipt: Receipt,
    bank_df: pd.DataFrame,
    claimed: set[str],
    settings: Settings,
) -> pd.Series | None:
    """Fallback for garbled merchant OCR: match on amount+date alone, but only
    if that pins down exactly one unclaimed bank row -- never guess between ties."""
    date_lo, date_hi = _date_window(receipt, settings)

    candidates = bank_df[
        (~bank_df["transaction_id"].isin(claimed))
        & (bank_df["date"] >= date_lo)
        & (bank_df["date"] <= date_hi)
        & ((bank_df["amount"] - receipt.amount).abs() <= settings.amount_tolerance)
    ]
    return candidates.iloc[0] if len(candidates) == 1 else None


def _find_prior_duplicate(
    receipt: Receipt, claimed_by: dict[str, Receipt], settings: Settings
) -> Receipt | None:
    """Check whether an already-matched receipt looks like the same purchase."""
    for other in claimed_by.values():
        if other is receipt:
            continue
        same_amount = abs((other.amount or 0) - (receipt.amount or 0)) <= settings.amount_tolerance
        same_merchant = (
            _merchant_similarity(other.merchant or "", receipt.merchant or "")
            >= settings.merchant_match_threshold
        )
        same_date = (
            other.txn_date is not None
            and receipt.txn_date is not None
            and abs((other.txn_date - receipt.txn_date).days) <= settings.date_tolerance_days
        )
        if same_amount and same_merchant and same_date:
            return other
    return None


def reconcile(
    receipts: list[Receipt],
    bank_df: pd.DataFrame,
    settings: Settings,
) -> ReconciliationResult:
    """Cross-reference extracted receipts against the bank statement.

    Returns a :class:`ReconciliationResult` with clean matches and every
    discrepancy found, ready to hand to the report layer.
    """
    result = ReconciliationResult(
        receipts_processed=len(receipts),
        bank_transactions_total=len(bank_df),
    )
    claimed: set[str] = set()
    claimed_by: dict[str, Receipt] = {}

    for receipt in receipts:
        if not receipt.is_fully_parsed:
            result.discrepancies.append(
                Discrepancy(
                    type=DiscrepancyType.MISSING_IN_BANK,
                    severity=Severity.WARNING,
                    message=(
                        f"Could not reliably read {receipt.display_name} "
                        f"(merchant={receipt.merchant!r}, amount={receipt.amount!r}, "
                        f"date={receipt.txn_date!r}) -- skipped, needs manual review."
                    ),
                    receipt=receipt,
                )
            )
            continue

        best, _merchant_score = _find_best_candidate(receipt, bank_df, claimed, settings)
        low_confidence_match = False

        if best is None:
            best = _find_amount_date_only_match(receipt, bank_df, claimed, settings)
            low_confidence_match = best is not None

        if best is None:
            # An already-claimed receipt with the same merchant/amount/date
            # means this one is a duplicate submission, not a plain miss.
            duplicate_of = _find_prior_duplicate(receipt, claimed_by, settings)
            if duplicate_of is not None:
                result.discrepancies.append(
                    Discrepancy(
                        type=DiscrepancyType.DUPLICATE_RECEIPT,
                        severity=Severity.CRITICAL,
                        message=(
                            f"{receipt.display_name} looks like a duplicate of "
                            f"{duplicate_of.display_name} (same merchant/amount/date) -- "
                            "only one matching bank charge exists. Possible duplicate "
                            "submission or double billing attempt."
                        ),
                        receipt=receipt,
                    )
                )
            else:
                result.discrepancies.append(
                    Discrepancy(
                        type=DiscrepancyType.MISSING_IN_BANK,
                        severity=Severity.WARNING,
                        message=(
                            f"Receipt from '{receipt.merchant}' for ${receipt.amount:,.2f} "
                            f"on {receipt.txn_date} has no matching charge on the bank "
                            f"statement within {settings.date_tolerance_days} day(s)."
                        ),
                        receipt=receipt,
                    )
                )
            continue

        bank_txn = BankTransaction(
            transaction_id=best["transaction_id"],
            txn_date=best["date"],
            amount=best["amount"],
            merchant=best["merchant"],
            description=best["description"],
        )
        claimed.add(bank_txn.transaction_id)
        claimed_by[bank_txn.transaction_id] = receipt

        amount_delta = round(bank_txn.amount - receipt.amount, 2)
        date_diff_days = abs((bank_txn.txn_date - receipt.txn_date).days)

        if abs(amount_delta) > settings.amount_tolerance:
            result.discrepancies.append(
                Discrepancy(
                    type=DiscrepancyType.AMOUNT_MISMATCH,
                    severity=Severity.CRITICAL,
                    message=(
                        f"ALERT: Receipt from '{receipt.merchant}' "
                        f"({receipt.display_name}) indicates ${receipt.amount:,.2f}, "
                        f"but bank statement charged ${bank_txn.amount:,.2f} "
                        f"(txn {bank_txn.transaction_id}, {bank_txn.txn_date})."
                    ),
                    receipt=receipt,
                    bank_txn=bank_txn,
                    delta_amount=amount_delta,
                )
            )
            continue

        notes = []
        if low_confidence_match:
            notes.append(
                f"Merchant name on the receipt ('{receipt.merchant}') did not clearly "
                f"match the bank record ('{bank_txn.merchant}' / '{bank_txn.description}') -- "
                "matched by amount + date alone because exactly one unclaimed "
                "transaction fit that window. Verify the merchant manually."
            )
        if date_diff_days > 0:
            notes.append(
                f"Posted {date_diff_days} day(s) after the receipt date "
                f"(receipt {receipt.txn_date} vs. bank {bank_txn.txn_date}) -- "
                "within tolerance, likely normal settlement delay."
            )
        result.matched.append(
            MatchedPair(
                receipt=receipt,
                bank_txn=bank_txn,
                date_diff_days=date_diff_days,
                notes=notes,
            )
        )

    # Bank rows nobody claimed are money that moved with no paper trail.
    for row in bank_df.itertuples(index=False):
        if row.transaction_id in claimed:
            continue
        severity = (
            Severity.CRITICAL if row.amount >= settings.large_unmatched_amount else Severity.WARNING
        )
        result.discrepancies.append(
            Discrepancy(
                type=DiscrepancyType.UNACCOUNTED_CHARGE,
                severity=severity,
                message=(
                    f"ALERT: Bank statement shows a charge of ${row.amount:,.2f} from "
                    f"'{row.merchant}' on {row.date} (txn {row.transaction_id}) with "
                    "NO matching receipt on file."
                ),
                bank_txn=BankTransaction(
                    transaction_id=row.transaction_id,
                    txn_date=row.date,
                    amount=row.amount,
                    merchant=row.merchant,
                    description=row.description,
                ),
            )
        )

    result.discrepancies.sort(key=lambda d: _SEVERITY_ORDER[d.severity])
    return result
