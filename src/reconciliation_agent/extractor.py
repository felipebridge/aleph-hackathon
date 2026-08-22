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

# Matches currency amounts with cents, e.g. $1,234.56 / 1234.56 / $45.99 /
# 45,99 (EU decimal comma) / 1.234,56 (EU thousands+decimal) / €12.50.
_AMOUNT_RE = re.compile(
    r"""
    (?<![\d.,])                     # not preceded by another digit/sep
    [$€£]?\s*
    (\d{1,3}(?:[.,]\d{3})*|\d+)     # integer part, optionally thousands-grouped
    [.,](\d{2})                     # decimal part (cents)
    (?!\d)
    """,
    re.VERBOSE,
)

# Fallback for receipts that print a whole-currency total with no cents at
# all (e.g. "TOTAL $50" instead of "TOTAL $50.00") -- only ever consulted
# when _AMOUNT_RE finds nothing anywhere in the document, so it can't
# accidentally steal a match from a properly-formatted amount.
_AMOUNT_INT_RE = re.compile(r"(?<![\d.,])[$€£]?\s*(\d{1,6})(?!\d)")

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


def _is_total_line(lowered: str) -> bool:
    return any(kw in lowered for kw in _TOTAL_LINE_KEYWORDS)


def _is_skip_line(lowered: str) -> bool:
    return any(kw in lowered for kw in _SKIP_LINE_KEYWORDS)


def extract_amount(text: str) -> float | None:
    """Best-effort extraction of the receipt's total amount.

    Strategy, in order:
      1. A cents-precise amount on a line that looks like a total/balance-due
         line (last one wins if several -- the final grand total is
         conventionally printed last).
      2. The largest cents-precise amount anywhere in the document (on a
         real receipt the grand total is virtually always the largest
         figure -- larger than any single line item, subtotal, or tax line).
      3. A bare whole-number amount on a total line, for receipts that omit
         cents entirely (e.g. "TOTAL $50"). Only used when nothing above
         matched anything, so it never outranks a properly formatted amount.
    """
    candidates_on_total_lines: list[float] = []
    all_candidates: list[float] = []
    int_candidates_on_total_lines: list[float] = []

    for line in text.splitlines():
        lowered = line.lower()
        skip = _is_skip_line(lowered)
        on_total_line = _is_total_line(lowered)

        matches = [_normalize_amount(m.group(1), m.group(2)) for m in _AMOUNT_RE.finditer(line)]
        if matches:
            all_candidates.extend(matches)
            if on_total_line and not skip:
                candidates_on_total_lines.append(max(matches))
            continue  # a cents-precise match takes priority over the int fallback on this line

        if on_total_line and not skip:
            int_matches = [float(m.group(1)) for m in _AMOUNT_INT_RE.finditer(line)]
            if int_matches:
                int_candidates_on_total_lines.append(max(int_matches))

    if candidates_on_total_lines:
        return candidates_on_total_lines[-1]
    if all_candidates:
        return max(all_candidates)
    if int_candidates_on_total_lines:
        return int_candidates_on_total_lines[-1]
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


_SLASH_DATE_RE = re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})$")


def _parse_date_token(raw: str):
    """Parse one candidate date substring, resolving day/month ambiguity.

    Receipts aren't all printed MM/DD/YYYY (US) -- plenty of POS systems
    print DD/MM/YYYY (most everywhere else). For an unambiguous token (an
    ISO date, or a slash-date where one component is > 12) we trust the
    unambiguous reading; for a genuinely ambiguous "08/09/2026" we default
    to the US convention, which matches the sample bank data's format.
    """
    slash_match = _SLASH_DATE_RE.match(raw)
    if slash_match:
        first, second = int(slash_match.group(1)), int(slash_match.group(2))
        if first > 12 >= second:
            dayfirst = True
        elif second > 12 >= first:
            dayfirst = False
        else:
            dayfirst = False  # ambiguous -- default to US month/day order
        try:
            return dateutil_parser.parse(raw, fuzzy=True, dayfirst=dayfirst).date()
        except (ValueError, OverflowError):
            return None

    try:
        return dateutil_parser.parse(raw, fuzzy=True, dayfirst=False).date()
    except (ValueError, OverflowError):
        return None


def extract_date(text: str):
    """Best-effort extraction of the transaction date from OCR text."""
    for match in _DATE_CANDIDATE_RE.finditer(text):
        parsed = _parse_date_token(match.group(1))
        if parsed is not None:
            return parsed
    return None


# --- Merchant extraction ---------------------------------------------------

_NOISE_LINE_RE = re.compile(
    r"^\s*(receipt|invoice|thank you|customer copy|order\s*#?\d*)\s*$", re.IGNORECASE
)

_LEADING_DIGITS_RE = re.compile(r"^\d")

# How many leading non-noise lines we're willing to consider as the store
# name. Real receipts put it on line 1, but OCR sometimes mangles a logo
# into garbage that gets filtered out as noise first -- looking a little
# further down catches those without wandering into the middle of the
# itemized list.
_MERCHANT_SEARCH_WINDOW = 6


def _merchant_candidate_score(line: str, position: int) -> float:
    """Higher is more likely to be the store name; used to pick among the
    first few plausible lines instead of blindly trusting line 1.

    Address and phone lines ("123 Market Street", "(415) 555-0199") are the
    most common false positive when the true first line got OCR'd into
    noise and filtered out, so both are penalised heavily.
    """
    score = 100.0 - position * 5  # earlier lines are more likely the header
    if _LEADING_DIGITS_RE.match(line):
        score -= 60  # "123 Main St", "(415) 555-0199", phone/address lines
    digit_ratio = sum(ch.isdigit() for ch in line) / len(line)
    score -= digit_ratio * 80
    if not (2 <= len(line) <= 50):
        score -= 30
    return score


def extract_merchant(text: str) -> str | None:
    """Best-effort extraction of the merchant/store name.

    Physical receipts almost universally print the store name as the very
    first printed line (letterhead-style). We scan the first few
    non-empty, non-noise lines and score each one, so a garbled first line
    (common with real photographed receipts) doesn't cause an address or
    phone-number line to be mistaken for the store name.
    """
    candidates: list[tuple[str, float]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or _NOISE_LINE_RE.match(stripped):
            continue
        # Skip lines that are only punctuation/digits (e.g. "======", phone numbers)
        if not re.search(r"[A-Za-z]{2,}", stripped):
            continue
        # Skip item/price/total lines -- a line with a currency-shaped
        # amount, or a total/tax/subtotal keyword, is never the store name.
        lowered = stripped.lower()
        if _AMOUNT_RE.search(stripped) or _is_total_line(lowered) or _is_skip_line(lowered):
            continue
        candidates.append((stripped, _merchant_candidate_score(stripped, len(candidates))))
        if len(candidates) >= _MERCHANT_SEARCH_WINDOW:
            break

    if not candidates:
        return None

    best_line, _ = max(candidates, key=lambda pair: pair[1])
    return best_line.title()


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
