"""Turns raw OCR text into a structured :class:`Receipt`.

This is the "NLP-to-Finance" step: receipts are unstructured, noisy text
blocks (misaligned columns, OCR typos, inconsistent layouts) and we need to
reliably pull out three fields a bank statement can be matched against:
merchant, amount, and date.

The heuristics below are intentionally conservative -- a missed field
(``None``) is far better than a confidently wrong one, since a wrong amount
or date would silently corrupt the reconciliation. Every skipped field is
still surfaced in the terminal report so a human can eyeball the source
file.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from dateutil import parser as dateutil_parser

from .models import OcrResult, Receipt

logger = logging.getLogger(__name__)

# --- Amount extraction -------------------------------------------------

# Matches currency amounts like $1,234.56 / 1234.56 / $45.99 / 45,99 (EU)
_AMOUNT_RE = re.compile(
    r"""
    (?<![\d.,])                     # not preceded by another digit/sep
    \$?\s*
    (\d{1,3}(?:[.,]\d{3})*|\d+)     # integer part, optionally thousands-grouped
    [.,](\d{2})                     # decimal part (cents)
    (?!\d)
    """,
    re.VERBOSE,
)

_TOTAL_LINE_KEYWORDS = (
    "total",
    "amount due",
    "balance due",
    "grand total",
    "amount charged",
)

_SKIP_LINE_KEYWORDS = (
    "subtotal",
    "sub-total",
    "sub total",
    "tax",
    "change",
    "cash",
    "tip",
)


def _normalize_amount(int_part: str, dec_part: str) -> float:
    int_part = int_part.replace(",", "").replace(".", "")
    return float(f"{int_part}.{dec_part}")


def extract_amount(text: str) -> float | None:
    """Best-effort extraction of the receipt's total amount.

    Strategy: prefer a number on a line that looks like a total/balance-due
    line; fall back to the largest currency-shaped number in the document
    (on a real receipt the grand total is virtually always the largest
    figure -- larger than any single line item, subtotal, or tax line).
    """
    candidates_on_total_lines: list[float] = []
    all_candidates: list[float] = []

    for line in text.splitlines():
        lowered = line.lower()
        matches = [
            _normalize_amount(m.group(1), m.group(2)) for m in _AMOUNT_RE.finditer(line)
        ]
        if not matches:
            continue

        all_candidates.extend(matches)

        if any(kw in lowered for kw in _SKIP_LINE_KEYWORDS):
            continue
        if any(kw in lowered for kw in _TOTAL_LINE_KEYWORDS):
            candidates_on_total_lines.append(max(matches))

    if candidates_on_total_lines:
        # If multiple "total-like" lines exist, the last one printed on a
        # receipt is conventionally the final grand total.
        return candidates_on_total_lines[-1]
    if all_candidates:
        return max(all_candidates)
    return None


# --- Date extraction -----------------------------------------------------

_DATE_CANDIDATE_RE = re.compile(
    r"""
    \b(
        \d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}   # 08/22/2026, 22-08-26
        |
        \d{4}-\d{1,2}-\d{1,2}                # 2026-08-22 (ISO)
        |
        [A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{2,4}  # Aug 22, 2026 / August 22 2026
    )\b
    """,
    re.VERBOSE,
)


def extract_date(text: str):
    """Best-effort extraction of the transaction date from OCR text."""
    for match in _DATE_CANDIDATE_RE.finditer(text):
        raw = match.group(1)
        try:
            parsed = dateutil_parser.parse(raw, fuzzy=True, dayfirst=False)
            return parsed.date()
        except (ValueError, OverflowError):
            continue
    return None


# --- Merchant extraction ---------------------------------------------------

_NOISE_LINE_RE = re.compile(
    r"^\s*(receipt|invoice|thank you|customer copy|order\s*#?\d*)\s*$", re.IGNORECASE
)


def extract_merchant(text: str) -> str | None:
    """Best-effort extraction of the merchant/store name.

    Physical receipts almost universally print the store name as the very
    first printed line (letterhead-style). We take the first non-empty,
    non-noise line and title-case it for consistent downstream matching.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or _NOISE_LINE_RE.match(stripped):
            continue
        # Skip lines that are only punctuation/digits (e.g. "======", phone numbers)
        if not re.search(r"[A-Za-z]{2,}", stripped):
            continue
        return stripped.title()
    return None


def parse_receipt(ocr_result: OcrResult, source_file: Path) -> Receipt:
    """Build a structured :class:`Receipt` from a raw OCR result."""
    text = ocr_result.text
    merchant = extract_merchant(text)
    amount = extract_amount(text)
    txn_date = extract_date(text)

    receipt = Receipt(
        source_file=source_file,
        merchant=merchant,
        amount=amount,
        txn_date=txn_date,
        raw_text=text,
        ocr_engine=ocr_result.engine_name,
        ocr_confidence=ocr_result.confidence,
    )

    if not receipt.is_fully_parsed:
        logger.warning(
            "Partial extraction for %s (merchant=%r, amount=%r, date=%r) -- "
            "this receipt will be flagged as needing manual review.",
            source_file.name,
            merchant,
            amount,
            txn_date,
        )
    return receipt
