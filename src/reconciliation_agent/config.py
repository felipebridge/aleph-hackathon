"""Runtime configuration: tunable business-rule thresholds for a reconciliation run."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass(frozen=True, slots=True)
class Settings:
    """Thresholds and paths for one reconciliation run; all exposed on the CLI."""

    receipts_dir: Path
    bank_csv: Path
    output_path: Path

    output_html: Optional[Path] = None

    date_tolerance_days: int = 3  # bank posting can lag the receipt date by this many days
    amount_tolerance: float = 0.01  # $ tolerance for rounding noise
    merchant_match_threshold: float = 60.0  # min RapidFuzz score (0-100) to be a candidate
    large_unmatched_amount: float = 200.0  # unreceipted bank charges above this are CRITICAL

    verbose: bool = False

    def __post_init__(self) -> None:
        if self.date_tolerance_days < 0:
            raise ValueError("date_tolerance_days must be >= 0")
        if self.amount_tolerance < 0:
            raise ValueError("amount_tolerance must be >= 0")
        if not (0 <= self.merchant_match_threshold <= 100):
            raise ValueError("merchant_match_threshold must be within [0, 100]")
