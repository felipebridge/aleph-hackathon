"""Loads and normalises the bank statement CSV export.

Kept deliberately separate from the matching logic so the "what does a
valid bank export look like" concern lives in one place, and so the
matcher can be unit-tested against plain lists of :class:`BankTransaction`
without touching pandas or the filesystem at all.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .models import BankTransaction

REQUIRED_COLUMNS = {"date", "amount", "merchant"}

# Common column-name variants seen across different banks' CSV/Excel exports.
_COLUMN_ALIASES = {
    "transaction_date": "date",
    "posting_date": "date",
    "txn_date": "date",
    "value": "amount",
    "debit": "amount",
    "amount_usd": "amount",
    "payee": "merchant",
    "vendor": "merchant",
    "description": "description",
    "memo": "description",
    "id": "transaction_id",
    "txn_id": "transaction_id",
    "reference": "transaction_id",
}


class BankStatementError(ValueError):
    """Raised when the bank CSV is missing required data."""


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={c: c.strip().lower().replace(" ", "_") for c in df.columns})
    df = df.rename(columns={k: v for k, v in _COLUMN_ALIASES.items() if k in df.columns})
    return df


def load_bank_statement(csv_path: Path) -> pd.DataFrame:
    """Load a bank statement CSV into a normalised, validated DataFrame.

    Returns a DataFrame with (at least) the columns:
    ``transaction_id, date (datetime64), amount (float), merchant (str),
    description (str)``.
    """
    if not csv_path.exists():
        raise BankStatementError(f"Bank statement not found: {csv_path}")

    df = pd.read_csv(csv_path)
    df = _normalize_columns(df)

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise BankStatementError(
            f"Bank statement {csv_path.name} is missing required column(s): "
            f"{', '.join(sorted(missing))}. Found columns: {', '.join(df.columns)}"
        )

    if "transaction_id" not in df.columns:
        df["transaction_id"] = [f"TXN-{i:04d}" for i in range(1, len(df) + 1)]
    if "description" not in df.columns:
        df["description"] = ""

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df["amount"] = (
        df["amount"]
        .astype(str)
        .str.replace(r"[^\d.\-]", "", regex=True)
        .replace("", "0")
        .astype(float)
    )
    df["merchant"] = df["merchant"].fillna("").astype(str).str.strip()
    df["description"] = df["description"].fillna("").astype(str).str.strip()
    df["transaction_id"] = df["transaction_id"].astype(str)

    bad_dates = df["date"].isna().sum()
    if bad_dates:
        raise BankStatementError(
            f"Bank statement {csv_path.name} has {bad_dates} row(s) with an unparsable date."
        )

    return df[["transaction_id", "date", "amount", "merchant", "description"]]


def to_transactions(df: pd.DataFrame) -> list[BankTransaction]:
    """Convert the normalised DataFrame into typed :class:`BankTransaction` rows."""
    return [
        BankTransaction(
            transaction_id=row.transaction_id,
            txn_date=row.date,
            amount=row.amount,
            merchant=row.merchant,
            description=row.description,
        )
        for row in df.itertuples(index=False)
    ]
