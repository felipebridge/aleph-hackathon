"""Unit tests for the bank statement CSV loader/normaliser."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from reconciliation_agent.bank_loader import BankStatementError, load_bank_statement


def _write_csv(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "bank_statement.csv"
    path.write_text(content, encoding="utf-8")
    return path


def test_loads_well_formed_statement(tmp_path: Path):
    csv_path = _write_csv(
        tmp_path,
        "transaction_id,date,amount,merchant,description\n"
        "TXN-1,2026-08-10,4.75,Starbucks,STARBUCKS STORE #4521\n",
    )
    df = load_bank_statement(csv_path)

    assert list(df.columns) == ["transaction_id", "date", "amount", "merchant", "description"]
    assert df.iloc[0]["date"] == dt.date(2026, 8, 10)
    assert df.iloc[0]["amount"] == 4.75
    assert df.iloc[0]["merchant"] == "Starbucks"


def test_accepts_common_column_aliases(tmp_path: Path):
    csv_path = _write_csv(
        tmp_path,
        "Transaction Date,Debit,Payee\n2026-08-10,4.75,Starbucks\n",
    )
    df = load_bank_statement(csv_path)

    assert df.iloc[0]["merchant"] == "Starbucks"
    assert df.iloc[0]["amount"] == 4.75


def test_missing_file_raises(tmp_path: Path):
    with pytest.raises(BankStatementError):
        load_bank_statement(tmp_path / "does_not_exist.csv")


def test_missing_required_column_raises(tmp_path: Path):
    csv_path = _write_csv(tmp_path, "date,amount\n2026-08-10,4.75\n")
    with pytest.raises(BankStatementError, match="missing required column"):
        load_bank_statement(csv_path)


def test_unparsable_date_raises(tmp_path: Path):
    csv_path = _write_csv(
        tmp_path,
        "date,amount,merchant\nnot-a-date,4.75,Starbucks\n",
    )
    with pytest.raises(BankStatementError, match="unparsable date"):
        load_bank_statement(csv_path)


def test_auto_generates_transaction_id_when_absent(tmp_path: Path):
    csv_path = _write_csv(tmp_path, "date,amount,merchant\n2026-08-10,4.75,Starbucks\n")
    df = load_bank_statement(csv_path)
    assert df.iloc[0]["transaction_id"] == "TXN-0001"
