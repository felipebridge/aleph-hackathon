"""Unit tests for WhatsApp attachment ingestion (OCR mocked, no real QVAC worker)."""

from __future__ import annotations

import pytest

from reconciliation_agent import monthly_dataset as ds
from reconciliation_agent.models import OcrResult
from reconciliation_agent.ocr_engine import OcrEngineError, QVACOcrEngine
from reconciliation_agent.whatsapp.ingest import (
    UnsupportedAttachmentError,
    ingest_attachment,
    month_from_timestamp,
)
from reconciliation_agent.whatsapp.schemas import IncomingAttachment


def _attachment(mime_type="image/jpeg", filename=None, timestamp="1755100800"):
    return IncomingAttachment(
        message_id="wamid.ABC123",
        from_number="5491122334455",
        media_id="MEDIA-1",
        mime_type=mime_type,
        filename=filename,
        timestamp=timestamp,
    )


class TestMonthFromTimestamp:
    def test_converts_unix_seconds_to_year_month(self):
        assert month_from_timestamp("1755100800") == "2025-08"


class TestIngestAttachment:
    def test_unsupported_mime_type_raises_before_touching_ocr(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ds, "DATA_ROOT", tmp_path)
        attachment = _attachment(mime_type="audio/ogg")

        with pytest.raises(UnsupportedAttachmentError, match="unsupported attachment type"):
            ingest_attachment(attachment, b"irrelevant", QVACOcrEngine())

    def test_saves_attachment_and_appends_extracted_receipt(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ds, "DATA_ROOT", tmp_path)
        monkeypatch.setattr(
            QVACOcrEngine,
            "read",
            lambda self, path: OcrResult(
                text="Rappi\nTotal ARS 2,940.00\n07/14/2026", engine_name="qvac"
            ),
        )

        dataset_path = ingest_attachment(_attachment(), b"fake-jpeg-bytes", QVACOcrEngine())

        assert dataset_path.exists()
        saved_attachments = list(ds.attachments_dir("2025-08").glob("*.jpg"))
        assert len(saved_attachments) == 1
        assert saved_attachments[0].read_bytes() == b"fake-jpeg-bytes"

        [receipt] = ds.load("2025-08")
        assert receipt.merchant == "Rappi"
        assert receipt.amount == 2940.0

    def test_ocr_failure_raises_unsupported_attachment_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ds, "DATA_ROOT", tmp_path)

        def _raise(self, path):
            raise OcrEngineError("worker unavailable")

        monkeypatch.setattr(QVACOcrEngine, "read", _raise)

        with pytest.raises(UnsupportedAttachmentError, match="OCR failed"):
            ingest_attachment(_attachment(), b"bytes", QVACOcrEngine())

    def test_attachment_filename_encodes_sender_and_message_id(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ds, "DATA_ROOT", tmp_path)
        monkeypatch.setattr(
            QVACOcrEngine,
            "read",
            lambda self, path: OcrResult(text="Uber\nTOTAL 23.50\n08/12/2026", engine_name="qvac"),
        )

        ingest_attachment(_attachment(), b"x", QVACOcrEngine())

        [saved] = list(ds.attachments_dir("2025-08").glob("*.jpg"))
        assert "wamid.ABC123" in saved.name
        assert "5491122334455" in saved.name

    def test_document_message_uses_filename_extension(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ds, "DATA_ROOT", tmp_path)
        monkeypatch.setattr(
            QVACOcrEngine,
            "read",
            lambda self, path: OcrResult(
                text="PetroSur\nTOTAL 4630.00\n07/20/2026", engine_name="qvac"
            ),
        )

        attachment = _attachment(mime_type="application/pdf", filename="factura.pdf")
        ingest_attachment(attachment, b"%PDF-fake", QVACOcrEngine())

        saved = list(ds.attachments_dir("2025-08").glob("*.pdf"))
        assert len(saved) == 1
