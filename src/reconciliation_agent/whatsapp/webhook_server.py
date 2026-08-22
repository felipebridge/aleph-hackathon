"""FastAPI receiver for WhatsApp Business Cloud API webhooks.

GET /webhook  -- Meta's subscription verification handshake.
POST /webhook -- incoming message notifications; each image/document
                 attachment is downloaded and OCR'd via the same local QVAC
                 pipeline the CLI uses, then filed into that month's dataset.

Endpoints are sync `def`s, not `async def`: FastAPI runs sync handlers in a
thread pool automatically, which sidesteps mixing QVACOcrEngine's own
internal event-loop thread with the request's async loop -- not worth the
complexity for a single-tenant demo server.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from ..ocr_engine import QVACOcrEngine
from .ingest import UnsupportedAttachmentError, ingest_attachment
from .media_client import MediaDownloadError, WhatsAppConfigError, download_media
from .schemas import parse_webhook_attachments, verify_webhook_challenge

logger = logging.getLogger(__name__)

_engine: QVACOcrEngine | None = None


def _get_engine() -> QVACOcrEngine:
    global _engine
    if _engine is None:
        _engine = QVACOcrEngine()
    return _engine


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    yield
    if _engine is not None:
        _engine.close()


app = FastAPI(title="Reconciliation Agent -- WhatsApp intake", lifespan=_lifespan)


@app.get("/")
def health() -> dict:
    return {"status": "ok"}


@app.get("/webhook")
def verify(request: Request) -> Response:
    expected_token = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
    challenge = verify_webhook_challenge(
        request.query_params.get("hub.mode"),
        request.query_params.get("hub.verify_token"),
        request.query_params.get("hub.challenge"),
        expected_token=expected_token,
    )
    if challenge is None:
        return Response(status_code=403)
    return PlainTextResponse(challenge)


@app.post("/webhook")
def receive(payload: dict) -> JSONResponse:
    results = []
    for attachment in parse_webhook_attachments(payload):
        try:
            file_bytes = download_media(attachment.media_id)
            dataset_path = ingest_attachment(attachment, file_bytes, _get_engine())
            results.append(
                {"message_id": attachment.message_id, "status": "ok", "dataset": str(dataset_path)}
            )
        except (WhatsAppConfigError, MediaDownloadError, UnsupportedAttachmentError) as exc:
            logger.warning("Failed to process %s: %s", attachment.message_id, exc)
            results.append(
                {"message_id": attachment.message_id, "status": "error", "reason": str(exc)}
            )
    return JSONResponse({"processed": results})
