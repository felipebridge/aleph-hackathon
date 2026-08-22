"""Unit tests for the OCR engine abstraction and its deterministic mock."""

from __future__ import annotations

from pathlib import Path

import pytest

from reconciliation_agent.ocr_engine import (
    OcrEngineError,
    SidecarMockEngine,
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
