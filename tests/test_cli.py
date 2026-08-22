"""Focused test for cli.run()'s WhatsApp-intake code path.

--whatsapp-month must skip the receipts-dir scan and OCR engine entirely --
the dataset was already OCR'd at ingestion time (see monthly_dataset.py).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from reconciliation_agent import monthly_dataset as ds
from reconciliation_agent.cli import run
from reconciliation_agent.config import Settings
from reconciliation_agent.models import Receipt


def test_run_with_whatsapp_month_reconciles_without_touching_ocr(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "DATA_ROOT", tmp_path / "whatsapp_intake")
    ds.append(
        "2026-07",
        Receipt(
            source_file=Path("wamid.X_5491100000000.jpg"),
            merchant="Rappi",
            amount=2940.0,
            txn_date=dt.date(2026, 7, 5),
        ),
    )

    bank_csv = tmp_path / "bank.csv"
    bank_csv.write_text(
        "transaction_id,date,amount,merchant,description\n"
        "AR-002,2026-07-05,2940.00,Rappi,RAPPI PEDIDO AR\n",
        encoding="utf-8",
    )

    settings = Settings(
        receipts_dir=tmp_path / "unused-when-whatsapp-month-is-set",
        bank_csv=bank_csv,
        output_path=tmp_path / "out" / "report.txt",
        whatsapp_month="2026-07",
    )

    exit_code = run(settings)

    assert exit_code == 0  # clean match, no critical alerts
    assert (tmp_path / "out" / "report.txt").exists()
    assert (tmp_path / "out" / "report.html").exists()


def test_run_with_whatsapp_month_and_no_data_reports_zero_receipts(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "DATA_ROOT", tmp_path / "whatsapp_intake")
    bank_csv = tmp_path / "bank.csv"
    bank_csv.write_text("transaction_id,date,amount,merchant,description\n", encoding="utf-8")

    settings = Settings(
        receipts_dir=tmp_path / "unused",
        bank_csv=bank_csv,
        output_path=tmp_path / "out" / "report.txt",
        whatsapp_month="2026-06",
    )

    assert run(settings) == 0
