"""Unit tests for the WhatsApp webhook FastAPI server.

QVAC OCR and the Graph API media download are both mocked -- these tests
cover the HTTP surface (verification handshake, attachment dispatch,
error handling), not a live WhatsApp/QVAC integration.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from reconciliation_agent import monthly_dataset as ds
from reconciliation_agent.models import OcrResult
from reconciliation_agent.ocr_engine import QVACOcrEngine
from reconciliation_agent.whatsapp import webhook_server

IMAGE_PAYLOAD = {
    "entry": [
        {
            "changes": [
                {
                    "value": {
                        "messages": [
                            {
                                "from": "5491122334455",
                                "id": "wamid.ABC123",
                                "timestamp": "1755100800",
                                "type": "image",
                                "image": {"mime_type": "image/jpeg", "id": "MEDIA-1"},
                            }
                        ]
                    }
                }
            ]
        }
    ]
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "DATA_ROOT", tmp_path)
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "secret-token")
    return TestClient(webhook_server.app)


class TestVerifyEndpoint:
    def test_correct_token_echoes_challenge(self, client):
        response = client.get(
            "/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "secret-token",
                "hub.challenge": "12345",
            },
        )
        assert response.status_code == 200
        assert response.text == "12345"

    def test_wrong_token_is_rejected(self, client):
        response = client.get(
            "/webhook",
            params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "12345"},
        )
        assert response.status_code == 403


class TestHealthCheck:
    def test_root_returns_ok(self, client):
        assert client.get("/").json() == {"status": "ok"}


class TestReceiveEndpoint:
    def test_processes_image_attachment_end_to_end(self, client, monkeypatch):
        monkeypatch.setattr(
            webhook_server, "download_media", lambda media_id, **kw: b"fake-jpeg-bytes"
        )
        monkeypatch.setattr(
            QVACOcrEngine,
            "read",
            lambda self, path: OcrResult(
                text="Rappi\nTotal ARS 2,940.00\n07/14/2026", engine_name="qvac"
            ),
        )

        response = client.post("/webhook", json=IMAGE_PAYLOAD)

        assert response.status_code == 200
        [result] = response.json()["processed"]
        assert result["status"] == "ok"
        [receipt] = ds.load("2025-08")
        assert receipt.merchant == "Rappi"

    def test_download_failure_reported_as_error_not_500(self, client, monkeypatch):
        from reconciliation_agent.whatsapp.media_client import MediaDownloadError

        def _fail(media_id, **kw):
            raise MediaDownloadError("Graph API is down")

        monkeypatch.setattr(webhook_server, "download_media", _fail)

        response = client.post("/webhook", json=IMAGE_PAYLOAD)

        assert response.status_code == 200
        [result] = response.json()["processed"]
        assert result["status"] == "error"

    def test_non_attachment_message_yields_empty_processed_list(self, client):
        text_payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {"from": "1", "id": "wamid.X", "timestamp": "1", "type": "text"}
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        response = client.post("/webhook", json=text_payload)
        assert response.json() == {"processed": []}
