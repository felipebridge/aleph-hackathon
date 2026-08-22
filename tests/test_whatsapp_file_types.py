"""Unit tests for WhatsApp attachment file-type resolution."""

from __future__ import annotations

from reconciliation_agent.whatsapp.file_types import needs_ocr, resolve_extension


class TestResolveExtension:
    def test_image_message_uses_mime_type(self):
        assert resolve_extension("image/jpeg", None) == ".jpg"

    def test_document_message_prefers_filename_over_mime(self):
        assert resolve_extension("application/octet-stream", "factura.pdf") == ".pdf"

    def test_pdf_mime_type_without_filename(self):
        assert resolve_extension("application/pdf", None) == ".pdf"

    def test_unrecognized_mime_and_no_filename_returns_none(self):
        assert resolve_extension("audio/ogg", None) is None

    def test_mime_type_with_charset_suffix_still_resolves(self):
        assert resolve_extension("image/png; charset=binary", None) == ".png"


class TestNeedsOcr:
    def test_jpg_needs_ocr(self):
        assert needs_ocr(".jpg") is True

    def test_pdf_needs_ocr(self):
        assert needs_ocr(".pdf") is True

    def test_unknown_extension_does_not_need_ocr(self):
        assert needs_ocr(".ogg") is False

    def test_none_extension_does_not_need_ocr(self):
        assert needs_ocr(None) is False
