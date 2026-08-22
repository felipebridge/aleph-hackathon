"""Unit tests for the OCR engine abstraction and its deterministic mock."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from reconciliation_agent.ocr_engine import (
    OcrEngineError,
    SidecarMockEngine,
    TesseractOCREngine,
    _resolve_attachment_paths,
    get_ocr_engine,
)


def test_sidecar_mock_engine_reads_companion_text_file(tmp_path: Path):
    image = tmp_path / "receipt.png"
    image.write_bytes(b"not a real image, contents are irrelevant")
    sidecar = tmp_path / "receipt.png.ocr.txt"
    sidecar.write_text("Starbucks Coffee\nTOTAL $4.75\n", encoding="utf-8")

    engine = SidecarMockEngine()
    result = engine.read(image)

    assert result.engine_name == "mock"
    assert "Starbucks Coffee" in result.text
    assert result.confidence == 1.0


def test_sidecar_mock_engine_raises_when_sidecar_missing(tmp_path: Path):
    image = tmp_path / "receipt.png"
    image.write_bytes(b"irrelevant")

    engine = SidecarMockEngine()
    with pytest.raises(OcrEngineError):
        engine.read(image)


def test_get_ocr_engine_mock_is_always_available():
    engine = get_ocr_engine("mock")
    assert engine.name == "mock"


def test_get_ocr_engine_rejects_unknown_name():
    with pytest.raises(ValueError):
        get_ocr_engine("not-a-real-engine")


def test_get_ocr_engine_auto_always_resolves_to_something():
    # `auto` must never fail outright: SidecarMockEngine.is_available() is
    # always True, so the auto-degrade chain always terminates successfully.
    engine = get_ocr_engine("auto")
    assert engine.name in {"qvac", "tesseract", "mock"}


class TestPdfRasterization:
    """PDF support is implemented once, shared by both real OCR engines, on
    top of pypdfium2 -- a pure-wheel local renderer with no system Poppler/
    PDF binary dependency. These tests cover the shared rasterization path
    directly; TesseractOCREngine.read() is covered below with a stubbed
    pytesseract, since the Tesseract *binary* isn't assumed to be installed
    wherever these tests run.
    """

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


class TestTesseractPdfSupport:
    def test_reads_multi_page_pdf_and_merges_page_text(self, tmp_path: Path, monkeypatch):
        import pytesseract

        pdf_path = tmp_path / "invoice.pdf"
        page1 = Image.new("RGB", (200, 100), "white")
        page2 = Image.new("RGB", (200, 100), "white")
        page1.save(pdf_path, save_all=True, append_images=[page2])

        seen_sizes = []

        def fake_image_to_string(img):
            seen_sizes.append(img.size)
            return f"page {len(seen_sizes)} text"

        # The Tesseract *binary* isn't assumed to be on PATH in the test
        # environment -- stub pytesseract's call so only our rasterization
        # + per-page-merge logic is under test, not the binary itself.
        monkeypatch.setattr(pytesseract, "image_to_string", fake_image_to_string)

        result = TesseractOCREngine().read(pdf_path)

        assert len(seen_sizes) == 2  # one call per rasterized page
        assert "page 1 text" in result.text
        assert "page 2 text" in result.text
        assert result.engine_name == "tesseract"
