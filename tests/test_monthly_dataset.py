"""Unit tests for the monthly WhatsApp-intake dataset (append/load round-trip)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from reconciliation_agent import monthly_dataset as ds
from reconciliation_agent.models import Receipt


def _receipt(name: str = "wamid.ABC_5491122334455.jpg") -> Receipt:
    return Receipt(
        source_file=Path(name),
        merchant="Rappi",
        amount=2940.0,
        txn_date=dt.date(2026, 8, 5),
        raw_text="Rappi\nTotal ARS 2,940.00",
        ocr_engine="qvac",
        ocr_confidence=1.0,
    )


def test_load_empty_month_returns_empty_list(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ds, "DATA_ROOT", tmp_path)
    assert ds.load("2026-08") == []


def test_append_then_load_round_trips(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ds, "DATA_ROOT", tmp_path)
    ds.append("2026-08", _receipt())

    loaded = ds.load("2026-08")

    assert len(loaded) == 1
    assert loaded[0].merchant == "Rappi"
    assert loaded[0].amount == 2940.0
    assert loaded[0].txn_date == dt.date(2026, 8, 5)
    assert loaded[0].source_file == Path("wamid.ABC_5491122334455.jpg")


def test_multiple_appends_accumulate_in_order(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ds, "DATA_ROOT", tmp_path)
    ds.append("2026-08", _receipt("first.jpg"))
    ds.append("2026-08", _receipt("second.jpg"))

    loaded = ds.load("2026-08")

    assert [r.source_file.name for r in loaded] == ["first.jpg", "second.jpg"]


def test_months_are_isolated_from_each_other(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ds, "DATA_ROOT", tmp_path)
    ds.append("2026-07", _receipt("july.jpg"))
    ds.append("2026-08", _receipt("august.jpg"))

    assert [r.source_file.name for r in ds.load("2026-07")] == ["july.jpg"]
    assert [r.source_file.name for r in ds.load("2026-08")] == ["august.jpg"]


def test_receipt_with_no_date_round_trips_as_none(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ds, "DATA_ROOT", tmp_path)
    receipt = Receipt(source_file=Path("unclear.jpg"), merchant=None, amount=None, txn_date=None)
    ds.append("2026-08", receipt)

    loaded = ds.load("2026-08")
    assert loaded[0].txn_date is None
    assert loaded[0].merchant is None


def test_attachments_dir_is_scoped_per_month(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ds, "DATA_ROOT", tmp_path)
    assert ds.attachments_dir("2026-08") == tmp_path / "2026-08" / "attachments"
