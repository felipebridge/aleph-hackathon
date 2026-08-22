"""Unit tests for the WhatsApp traffic simulator (OCR mocked)."""

from __future__ import annotations

from pathlib import Path

from reconciliation_agent import monthly_dataset as ds
from reconciliation_agent.models import OcrResult
from reconciliation_agent.ocr_engine import QVACOcrEngine
from reconciliation_agent.whatsapp.simulator import SimulatedMessage, run_simulation


def test_simulation_ingests_existing_files_into_the_monthly_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(
        QVACOcrEngine,
        "read",
        lambda self, path: OcrResult(
            text="Rappi\nTotal ARS 2,940.00\n07/14/2026", engine_name="qvac"
        ),
    )

    receipt_file = tmp_path / "recibo.jpg"
    receipt_file.write_bytes(b"fake-bytes")
    messages = [SimulatedMessage(receipt_file, "5491100000000", day=5)]

    dataset_paths = run_simulation(messages)

    assert len(dataset_paths) == 1
    [receipt] = ds.load("2026-07")
    assert receipt.merchant == "Rappi"


def test_missing_file_is_skipped_not_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "DATA_ROOT", tmp_path)
    messages = [SimulatedMessage(tmp_path / "does_not_exist.jpg", "5491100000000", day=1)]

    dataset_paths = run_simulation(messages)

    assert dataset_paths == []


def test_default_messages_reference_files_under_data_dir():
    from reconciliation_agent.whatsapp.simulator import DEFAULT_MESSAGES

    assert len(DEFAULT_MESSAGES) > 0
    for message in DEFAULT_MESSAGES:
        assert isinstance(message.file_path, Path)
        assert message.from_number.startswith("549")  # Argentine mobile prefix
