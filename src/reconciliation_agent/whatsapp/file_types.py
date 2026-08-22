"""Maps a WhatsApp attachment's MIME type / filename to a file extension.

Every extension this project's OCR pipeline already handles (images via
QVAC's vision model, PDFs via pypdfium2 rasterization + QVAC) is fair game;
everything else (voice notes, contact cards, stickers, spreadsheets...) is
rejected early with a clear reason instead of failing downstream.
"""

from __future__ import annotations

from pathlib import Path

from ..ocr_engine import SUPPORTED_EXTENSIONS

_MIME_TO_EXTENSION = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/tiff": ".tiff",
    "image/bmp": ".bmp",
    "application/pdf": ".pdf",
}


def resolve_extension(mime_type: str, filename: str | None) -> str | None:
    """Best-effort file extension for an attachment, or None if unrecognized.

    A `document` message's own `filename` is the most reliable signal when
    present; `image` messages never carry one, so fall back to the MIME type.
    """
    if filename:
        suffix = Path(filename).suffix.lower()
        if suffix:
            return suffix
    return _MIME_TO_EXTENSION.get(mime_type.split(";")[0].strip().lower())


def needs_ocr(extension: str | None) -> bool:
    """True when this project's local OCR pipeline can read this file type."""
    return extension is not None and extension in SUPPORTED_EXTENSIONS
