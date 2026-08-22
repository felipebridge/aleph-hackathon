"""Downloads a WhatsApp message attachment via Meta's Graph API.

Two-step handshake per Meta's docs: GET /{media-id} returns a short-lived
signed URL, then GET that URL (same Bearer token) returns the raw bytes.
This is the ONLY module in the whole project that makes an outbound
network call -- everything downstream (OCR, extraction, matching) is
unaffected by it and runs 100% locally once the bytes land on disk.
"""

from __future__ import annotations

import os

import httpx

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


class WhatsAppConfigError(RuntimeError):
    """Raised when required WhatsApp credentials aren't configured."""


class MediaDownloadError(RuntimeError):
    """Raised when the Graph API lookup or download call fails."""


def access_token() -> str:
    token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    if not token:
        raise WhatsAppConfigError(
            "WHATSAPP_ACCESS_TOKEN is not set -- get a token from your Meta app's "
            "WhatsApp > API Setup page and export it before running the webhook server."
        )
    return token


def download_media(media_id: str, *, client: httpx.Client | None = None) -> bytes:
    """Fetch the raw bytes of a WhatsApp media attachment by its id."""
    headers = {"Authorization": f"Bearer {access_token()}"}
    owns_client = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        lookup = client.get(f"{GRAPH_API_BASE}/{media_id}", headers=headers)
        if lookup.status_code != 200:
            raise MediaDownloadError(f"Failed to resolve media {media_id}: {lookup.text}")
        media_url = lookup.json().get("url")
        if not media_url:
            raise MediaDownloadError(f"Graph API response for {media_id} had no 'url' field")

        content = client.get(media_url, headers=headers)
        if content.status_code != 200:
            raise MediaDownloadError(
                f"Failed to download media {media_id}: HTTP {content.status_code}"
            )
        return content.content
    finally:
        if owns_client:
            client.close()
