"""Unit tests for the WhatsApp Graph API media client.

Uses httpx.MockTransport to simulate Meta's two-step media download
handshake without making a real network call.
"""

from __future__ import annotations

import httpx
import pytest

from reconciliation_agent.whatsapp.media_client import (
    MediaDownloadError,
    WhatsAppConfigError,
    download_media,
)

LOOKASIDE_URL = "https://lookaside.fbsbx.com/whatsapp_media/signed-download"


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


class TestDownloadMedia:
    def test_missing_access_token_raises_config_error(self, monkeypatch):
        monkeypatch.delenv("WHATSAPP_ACCESS_TOKEN", raising=False)
        with pytest.raises(WhatsAppConfigError):
            download_media("MEDIA-1")

    def test_successful_two_step_download(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["Authorization"] == "Bearer test-token"
            if str(request.url).endswith("/MEDIA-1"):
                return httpx.Response(200, json={"url": LOOKASIDE_URL, "mime_type": "image/jpeg"})
            if str(request.url) == LOOKASIDE_URL:
                return httpx.Response(200, content=b"fake-jpeg-bytes")
            raise AssertionError(f"unexpected URL: {request.url}")

        result = download_media("MEDIA-1", client=_client(handler))
        assert result == b"fake-jpeg-bytes"

    def test_lookup_failure_raises_download_error(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text="not found")

        with pytest.raises(MediaDownloadError, match="Failed to resolve"):
            download_media("MEDIA-1", client=_client(handler))

    def test_lookup_without_url_field_raises_download_error(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"mime_type": "image/jpeg"})

        with pytest.raises(MediaDownloadError, match="no 'url' field"):
            download_media("MEDIA-1", client=_client(handler))

    def test_content_download_failure_raises_download_error(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")

        def handler(request: httpx.Request) -> httpx.Response:
            if str(request.url).endswith("/MEDIA-1"):
                return httpx.Response(200, json={"url": LOOKASIDE_URL})
            return httpx.Response(410, text="expired")

        with pytest.raises(MediaDownloadError, match="HTTP 410"):
            download_media("MEDIA-1", client=_client(handler))
