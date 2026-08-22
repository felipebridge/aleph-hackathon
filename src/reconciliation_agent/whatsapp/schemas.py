"""Parses WhatsApp Business Cloud API webhook payloads.

Real shape (per Meta's docs): a POST body is
`{"entry": [{"changes": [{"value": {"messages": [...]}, "field": "messages"}]}]}`.
We only care about `image`/`document` messages -- text, audio, location,
status-update callbacks, etc. are silently skipped, not errors.
"""

from __future__ import annotations

from dataclasses import dataclass

# Message types that can carry a receipt/invoice attachment worth OCR'ing.
_ATTACHMENT_TYPES = {"image", "document"}


@dataclass(slots=True, frozen=True)
class IncomingAttachment:
    """One receipt-shaped attachment pulled out of a webhook payload."""

    message_id: str
    from_number: str
    media_id: str
    mime_type: str
    filename: str | None  # only "document" messages carry an original filename
    timestamp: str


def parse_webhook_attachments(payload: dict) -> list[IncomingAttachment]:
    """Extract every image/document attachment from a webhook POST body."""
    attachments: list[IncomingAttachment] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                msg_type = message.get("type")
                if msg_type not in _ATTACHMENT_TYPES:
                    continue
                media = message.get(msg_type, {})
                media_id = media.get("id")
                if not media_id:
                    continue
                attachments.append(
                    IncomingAttachment(
                        message_id=message.get("id", ""),
                        from_number=message.get("from", ""),
                        media_id=media_id,
                        mime_type=media.get("mime_type", "application/octet-stream"),
                        filename=media.get("filename"),
                        timestamp=message.get("timestamp", ""),
                    )
                )
    return attachments


def verify_webhook_challenge(
    mode: str | None, token: str | None, challenge: str | None, expected_token: str
) -> str | None:
    """Meta's GET /webhook handshake: echo `challenge` back iff mode+token match."""
    if mode == "subscribe" and token == expected_token and challenge is not None:
        return challenge
    return None
