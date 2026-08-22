"""Runtime configuration for the reconciliation agent.

Centralising every tunable threshold here (instead of scattering magic
numbers through the matching logic) is what lets the Product Manager tune
the business rules -- date tolerance, fuzzy-match sensitivity, etc. --
without touching the pandas code itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    """Business-rule thresholds and paths for a single reconciliation run.

    All values have sane defaults for SME bank statements but are exposed
    on the CLI (see ``cli.py``) so they can be adjusted per engagement
    without editing code.
    """

    # --- Input/output locations ---
    receipts_dir: Path
    bank_csv: Path
    output_path: Path

    # --- OCR engine selection ---
    ocr_engine: str = "auto"  # "auto" | "qvac" | "tesseract" | "mock"

    # --- Matching tolerances (the business logic knobs) ---
    date_tolerance_days: int = 3
    """Bank posting dates commonly lag the receipt date by a few days
    (card settlement delay), so an exact-date match would create false
    positives. This is the window used when looking for a candidate
    transaction."""

    amount_tolerance: float = 0.01
    """Absolute currency tolerance (covers floating point / rounding
    noise) before two amounts are considered "different"."""

    merchant_match_threshold: float = 60.0
    """Minimum RapidFuzz token-sort-ratio (0-100) between the OCR'd
    merchant name and the bank's merchant/description field for a
    transaction to even be considered a candidate match."""

    large_unmatched_amount: float = 200.0
    """Bank charges above this amount that have no matching receipt are
    escalated to CRITICAL (larger, unreceipted charges deserve more
    scrutiny than a stray $4 vending machine transaction)."""

    verbose: bool = False

    def __post_init__(self) -> None:
        if self.date_tolerance_days < 0:
            raise ValueError("date_tolerance_days must be >= 0")
        if self.amount_tolerance < 0:
            raise ValueError("amount_tolerance must be >= 0")
        if not (0 <= self.merchant_match_threshold <= 100):
            raise ValueError("merchant_match_threshold must be within [0, 100]")
