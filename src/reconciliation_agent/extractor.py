"""Turns raw OCR text into a structured :class:`Receipt`.

Heuristics are conservative on purpose: a missing field (``None``) beats a
confidently wrong one, since a bad amount or date would silently corrupt
the reconciliation.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from dateutil import parser as dateutil_parser

from .models import OcrResult, Receipt

logger = logging.getLogger(__name__)

# Some vision-OCR models annotate output with layout markup (a bounding-box
# prefix per line, <table> tags around tabular content) instead of plain
# text. Strip it before running the regex heuristics below.
_LAYOUT_PREFIX_RE = re.compile(r"^(?:text|table)\s*\[\d+,\s*\d+,\s*\d+,\s*\d+\]\s*", re.IGNORECASE)
_TABLE_TAG_RE = re.compile(r"</?table>", re.IGNORECASE)


def _strip_layout_markup(text: str) -> str:
    lines = [_TABLE_TAG_RE.sub(" ", _LAYOUT_PREFIX_RE.sub("", line)) for line in text.splitlines()]
    return "\n".join(lines)


# --- Amount extraction -------------------------------------------------

# Matches currency amounts with cents.
# Handles: $1,234.56 / ARS 2,820.00 / €12.50 / 1.234,56 (EU) / -ARS 940.00
# The currency prefix group is optional so bare numbers also match.
_AMOUNT_RE = re.compile(
    r"""
    (?<![\d.,])                          # not preceded by another digit/sep
    (?:ARS|USD|EUR|[$€£])?\s*            # optional currency symbol or ISO code
    (\d{1,3}(?:[.,]\d{3})*|\d+)          # integer part, optionally thousands-grouped
    [.,](\d{2})                          # decimal part (cents)
    (?!\d)
    """,
    re.VERBOSE,
)

# Fallback for whole-currency totals with no cents (e.g. "TOTAL $50").
_AMOUNT_INT_RE = re.compile(r"(?<![\d.,])(?:ARS|USD|EUR|[$€£])?\s*(\d{1,6})(?!\d)")

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
    """Total amount: prefer a cents-precise total-line match, else the
    largest cents-precise number in the doc, else a bare int on a total line."""
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
    """Parse a candidate date, preferring an unambiguous day/month reading
    (component > 12 can only be the day) over the US MM/DD default."""
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
    r"^\s*(" r"receipt|invoice|thank you|customer copy|order\s*#?\d*"
    # AFIP fiscal document headers (Argentine facturas)
    r"|original(?:\s*\(.*?\))?"  # "ORIGINAL (EJEMPLO)"
    r"|cod\.?\s*\d*"  # "COD. 06"
    r"|muestra(?:\s+—.*)?$"  # "MUESTRA — DATOS FICTICIOS ..."
    r"|e\-?ticket\s*receipt"  # "E-Ticket Receipt" (airline)
    r")\s*$",
    re.IGNORECASE,
)

# Strips Argentine fiscal document type from lines where the company name and
# document type appear together, e.g. "PETROSUR S.A.  FACTURA (MUESTRA)".
_FISCAL_DOC_SUFFIX_RE = re.compile(
    r"\s+(?:FACTURA|REMITO|NOTA\s+DE\s+CR[EÉ]DITO|NOTA\s+DE\s+D[EÉ]BITO)" r"(?:\s*\(.*?\))?\s*$",
    re.IGNORECASE,
)

_LEADING_DIGITS_RE = re.compile(r"^\d")

# Store name is almost always the first printed line, but a garbled logo
# can knock it a few lines down -- look this far before giving up.
_MERCHANT_SEARCH_WINDOW = 6


def _merchant_candidate_score(line: str, position: int) -> float:
    """Higher = more likely the store name. Penalizes address/phone lines
    (leading digits, high digit ratio) and full-sentence lines -- some
    vision-OCR models occasionally leak a meta-commentary sentence (e.g.
    "There is no actual character output to extract.") instead of, or
    alongside, the real transcription; a store name is never a sentence."""
    score = 100.0 - position * 5
    if _LEADING_DIGITS_RE.match(line):
        score -= 60
    digit_ratio = sum(ch.isdigit() for ch in line) / len(line)
    score -= digit_ratio * 80
    if not (2 <= len(line) <= 50):
        score -= 30
    if line.rstrip()[-1:] in ".!?" and len(line.split()) >= 4:
        score -= 60
    return score


def extract_merchant(text: str) -> str | None:
    """Store name: score the first few non-noise lines and take the best,
    instead of blindly trusting line 1 (which OCR often garbles)."""
    candidates: list[tuple[str, float]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or _NOISE_LINE_RE.match(stripped):
            continue
        if not re.search(r"[A-Za-z]{2,}", stripped):  # e.g. "======", phone numbers
            continue
        lowered = stripped.lower()
        if _AMOUNT_RE.search(stripped) or _is_total_line(lowered) or _is_skip_line(lowered):
            continue
        # Strip Argentine fiscal document type suffix that appears on the same
        # line as the company name: "PETROSUR S.A.  FACTURA (MUESTRA)" → "PETROSUR S.A."
        cleaned = _FISCAL_DOC_SUFFIX_RE.sub("", stripped).strip()
        if not cleaned:
            continue
        candidates.append((cleaned, _merchant_candidate_score(cleaned, len(candidates))))
        if len(candidates) >= _MERCHANT_SEARCH_WINDOW:
            break

    if not candidates:
        return None

    best_line, _ = max(candidates, key=lambda pair: pair[1])
    return best_line.title()


def parse_receipt(ocr_result: OcrResult, source_file: Path) -> Receipt:
    """Build a structured :class:`Receipt` from a raw OCR result."""
    text = _strip_layout_markup(ocr_result.text)
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
