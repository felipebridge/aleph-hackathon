"""Unit tests for the QVAC OCR engine and its PDF rasterization support."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from reconciliation_agent.ocr_engine import (
    OcrEngineError,
    QVACOcrEngine,
    SidecarOcrEngine,
    _resolve_attachment_paths,
    get_ocr_engine,
)


def test_get_ocr_engine_returns_ready_instance_when_available(monkeypatch):
    monkeypatch.setattr(QVACOcrEngine, "is_available", lambda self: True)
    engine = get_ocr_engine()
    assert isinstance(engine, QVACOcrEngine)


def test_get_ocr_engine_raises_with_setup_instructions_when_unavailable(monkeypatch):
    monkeypatch.setattr(QVACOcrEngine, "is_available", lambda self: False)
    with pytest.raises(OcrEngineError, match="QVAC worker not found"):
        get_ocr_engine()


class TestPdfRasterization:
    """Covers the pypdfium2 rasterization path QVACOcrEngine sends as attachments."""

    def test_plain_image_passes_through_unchanged(self, tmp_path: Path):
        image_path = tmp_path / "receipt.png"
        Image.new("RGB", (100, 50), "white").save(image_path)

        with _resolve_attachment_paths(image_path) as paths:
            assert paths == [image_path]

    def test_single_page_pdf_rasterizes_to_one_image(self, tmp_path: Path):
        pdf_path = tmp_path / "receipt.pdf"
        Image.new("RGB", (200, 100), "white").save(pdf_path, "PDF")

        with _resolve_attachment_paths(pdf_path) as paths:
            assert len(paths) == 1
            assert paths[0].suffix == ".png"
            assert paths[0].exists()
        # Temp files are cleaned up once the context manager exits.
        assert not paths[0].exists()

    def test_multi_page_pdf_rasterizes_one_image_per_page(self, tmp_path: Path):
        pdf_path = tmp_path / "invoice.pdf"
        page1 = Image.new("RGB", (200, 100), "white")
        page2 = Image.new("RGB", (200, 100), "white")
        page1.save(pdf_path, save_all=True, append_images=[page2])

        with _resolve_attachment_paths(pdf_path) as paths:
            assert len(paths) == 2
            assert all(p.exists() for p in paths)


class TestSidecarOcrEngine:
    def test_reads_sidecar_text_when_present(self, tmp_path: Path):
        receipt = tmp_path / "uber.pdf"
        receipt.write_bytes(b"%PDF-1.4 fake")
        (tmp_path / "uber.pdf.ocr.txt").write_text("Uber\nTotal ARS 3,120.00", encoding="utf-8")

        engine = SidecarOcrEngine()
        assert engine.is_available() is True
        assert engine.has_sidecar(receipt) is True
        result = engine.read(receipt)
        assert "3,120.00" in result.text
        assert result.engine_name == "sidecar"

    def test_missing_sidecar_raises(self, tmp_path: Path):
        receipt = tmp_path / "no_sidecar.jpg"
        receipt.write_bytes(b"fake")
        engine = SidecarOcrEngine()
        assert engine.has_sidecar(receipt) is False
        with pytest.raises(OcrEngineError):
            engine.read(receipt)
