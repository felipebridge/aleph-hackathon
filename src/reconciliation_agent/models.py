"""Typed domain objects shared across the pipeline.

Keeping these as explicit dataclasses (instead of passing raw dicts or
DataFrame rows around) is what makes the OCR layer, the matcher, and the
report generator independently testable and easy to reason about.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path


class Severity(str, Enum):
    """How urgently a human should look at a given finding."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class DiscrepancyType(str, Enum):
    """The taxonomy of reconciliation outcomes we can detect."""

    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    DATE_MISMATCH = "DATE_MISMATCH"  # referenced by report_html.py's type-label map
    MISSING_IN_BANK = "MISSING_IN_BANK"  # receipt with no bank charge
    UNACCOUNTED_CHARGE = "UNACCOUNTED_CHARGE"  # bank charge with no receipt
    DUPLICATE_RECEIPT = "DUPLICATE_RECEIPT"  # two receipts, one bank charge


@dataclass(slots=True)
class OcrResult:
    """Raw output of the OCR engine before any financial parsing happens."""

    text: str
    engine_name: str
    confidence: float = 1.0  # 0.0-1.0, engines that can't estimate default to 1.0


@dataclass(slots=True)
class Receipt:
    """Structured financial data extracted from a single physical receipt."""

    source_file: Path
    merchant: str | None
    amount: float | None
    txn_date: date | None
    raw_text: str = ""
    ocr_engine: str = "unknown"
    ocr_confidence: float = 1.0

    @property
    def is_fully_parsed(self) -> bool:
        """True when we extracted every field the matcher needs."""
        return self.merchant is not None and self.amount is not None and self.txn_date is not None

    @property
    def display_name(self) -> str:
        return self.source_file.name


@dataclass(slots=True)
class BankTransaction:
    """A single row from the bank statement export, normalised."""

    transaction_id: str
    txn_date: date
    amount: float
    merchant: str
    description: str = ""


@dataclass(slots=True)
class Discrepancy:
    """A single, human-readable reconciliation finding."""

    type: DiscrepancyType
    severity: Severity
    message: str
    receipt: Receipt | None = None
    bank_txn: BankTransaction | None = None
    delta_amount: float | None = None


@dataclass(slots=True)
class MatchedPair:
    """A receipt successfully reconciled against a bank transaction."""

    receipt: Receipt
    bank_txn: BankTransaction
    date_diff_days: int
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ReconciliationResult:
    """Everything the report layer needs to render a full run summary."""

    matched: list[MatchedPair] = field(default_factory=list)
    discrepancies: list[Discrepancy] = field(default_factory=list)
    receipts_processed: int = 0
    bank_transactions_total: int = 0

    @property
    def critical_count(self) -> int:
        return sum(1 for d in self.discrepancies if d.severity is Severity.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for d in self.discrepancies if d.severity is Severity.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for d in self.discrepancies if d.severity is Severity.INFO)
