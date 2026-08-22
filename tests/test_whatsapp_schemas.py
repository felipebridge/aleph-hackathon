"""Unit tests for parsing WhatsApp Business Cloud API webhook payloads."""

from __future__ import annotations

from reconciliation_agent.whatsapp.schemas import (
    parse_webhook_attachments,
    verify_webhook_challenge,
)

IMAGE_MESSAGE_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "WABA_ID",
            "changes": [
                {
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "PHONE_ID"},
                        "contacts": [{"profile": {"name": "Martina"}, "wa_id": "5491122334455"}],
                        "messages": [
                            {
                                "from": "5491122334455",
                                "id": "wamid.ABC123",
                                "timestamp": "1755870000",
                                "type": "image",
                                "image": {
                                    "mime_type": "image/jpeg",
                                    "sha256": "deadbeef",
                                    "id": "MEDIA-1",
                                },
                            }
                        ],
                    },
                    "field": "messages",
                }
            ],
        }
    ],
}

DOCUMENT_MESSAGE_PAYLOAD = {
    "entry": [
        {
            "changes": [
                {
                    "value": {
                        "messages": [
                            {
                                "from": "5491133445566",
                                "id": "wamid.DEF456",
                                "timestamp": "1755870100",
                                "type": "document",
                                "document": {
                                    "filename": "factura_petrosur.pdf",
                                    "mime_type": "application/pdf",
                                    "id": "MEDIA-2",
                                },
                            }
                        ]
                    },
                    "field": "messages",
                }
            ]
        }
    ]
}

TEXT_ONLY_PAYLOAD = {
    "entry": [
        {
            "changes": [
                {
                    "value": {
                        "messages": [
                            {
                                "from": "5491100000000",
                                "id": "wamid.TXT",
                                "timestamp": "1755870200",
                                "type": "text",
                                "text": {"body": "hola, ahi te mando el recibo"},
                            }
                        ]
                    },
                    "field": "messages",
                }
            ]
        }
    ]
}

STATUS_CALLBACK_PAYLOAD = {
    "entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.X", "status": "delivered"}]}}]}]
}


class TestParseWebhookAttachments:
    def test_extracts_image_attachment(self):
        attachments = parse_webhook_attachments(IMAGE_MESSAGE_PAYLOAD)

        assert len(attachments) == 1
        a = attachments[0]
        assert a.message_id == "wamid.ABC123"
        assert a.from_number == "5491122334455"
        assert a.media_id == "MEDIA-1"
        assert a.mime_type == "image/jpeg"
        assert a.filename is None

    def test_extracts_document_attachment_with_filename(self):
        attachments = parse_webhook_attachments(DOCUMENT_MESSAGE_PAYLOAD)

        assert len(attachments) == 1
        assert attachments[0].filename == "factura_petrosur.pdf"
        assert attachments[0].mime_type == "application/pdf"

    def test_text_only_message_yields_no_attachments(self):
        assert parse_webhook_attachments(TEXT_ONLY_PAYLOAD) == []

    def test_status_callback_yields_no_attachments(self):
        assert parse_webhook_attachments(STATUS_CALLBACK_PAYLOAD) == []

    def test_empty_payload_yields_no_attachments(self):
        assert parse_webhook_attachments({}) == []

    def test_multiple_entries_all_extracted(self):
        combined = {"entry": IMAGE_MESSAGE_PAYLOAD["entry"] + DOCUMENT_MESSAGE_PAYLOAD["entry"]}
        assert len(parse_webhook_attachments(combined)) == 2


class TestVerifyWebhookChallenge:
    def test_matching_token_echoes_challenge(self):
        result = verify_webhook_challenge("subscribe", "secret", "12345", expected_token="secret")
        assert result == "12345"

    def test_wrong_token_returns_none(self):
        result = verify_webhook_challenge("subscribe", "wrong", "12345", expected_token="secret")
        assert result is None

    def test_wrong_mode_returns_none(self):
        result = verify_webhook_challenge("unsubscribe", "secret", "12345", expected_token="secret")
        assert result is None
