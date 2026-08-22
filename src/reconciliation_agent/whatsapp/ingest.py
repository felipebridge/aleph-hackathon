"""Turns one incoming WhatsApp attachment into a structured Receipt filed
into its month's dataset -- the same OCR + extraction pipeline the
local-folder CLI uses, just fed one file at a time as messages arrive.

Takes already-downloaded bytes rather than calling media_client itself, so
the same code path serves both the real webhook (which downloads from
Meta) and the simulator (which reads a local sample file) identically.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from pathlib import Path

from .. import monthly_dataset
from ..extractor import parse_receipt
from ..ocr_engine import OcrEngineError, QVACOcrEngine
from .file_types import needs_ocr, resolve_extension
from .schemas import IncomingAttachment

logger = logging.getLogger(__name__)

_SANITIZE_RE = re.compile(r"[^A-Za-z0-9_.-]")


class UnsupportedAttachmentError(RuntimeError):
    """Raised when the attachment's file type isn't something we can OCR."""


def month_from_timestamp(unix_timestamp: str) -> str:
    """WhatsApp timestamps are Unix seconds as a string -- "YYYY-MM" for filing."""
    return dt.datetime.fromtimestamp(int(unix_timestamp), tz=dt.timezone.utc).strftime("%Y-%m")


def _attachment_filename(attachment: IncomingAttachment, extension: str) -> str:
    """`<message_id>_<sender>.<ext>`, sanitized -- keeps the audit trail (who
    sent what, and which WhatsApp message it came from) in the filename itself
    instead of adding WhatsApp-specific fields to the shared Receipt model."""
    safe_id = _SANITIZE_RE.sub("", attachment.message_id) or "unknown"
    safe_from = _SANITIZE_RE.sub("", attachment.from_number) or "unknown"
    return f"{safe_id}_{safe_from}{extension}"


def ingest_attachment(
    attachment: IncomingAttachment, file_bytes: bytes, engine: QVACOcrEngine
) -> Path:
    """Save, OCR, extract, and file one attachment into its month's dataset.
    Returns the dataset .jsonl path it was appended to."""
    extension = resolve_extension(attachment.mime_type, attachment.filename)
    if not needs_ocr(extension):
        raise UnsupportedAttachmentError(
            f"{attachment.message_id}: unsupported attachment type "
            f"(mime={attachment.mime_type!r}, filename={attachment.filename!r})"
        )

    month = month_from_timestamp(attachment.timestamp)
    dest_dir = monthly_dataset.attachments_dir(month)
    dest_dir.mkdir(parents=True, exist_ok=True)
    saved_path = dest_dir / _attachment_filename(attachment, extension)
    saved_path.write_bytes(file_bytes)

    try:
        ocr_result = engine.read(saved_path)
    except OcrEngineError as exc:
        raise UnsupportedAttachmentError(f"{attachment.message_id}: OCR failed: {exc}") from exc

    receipt = parse_receipt(ocr_result, saved_path)
    logger.info(
        "Ingested %s from %s: merchant=%r amount=%r date=%r",
        attachment.message_id,
        attachment.from_number,
        receipt.merchant,
        receipt.amount,
        receipt.txn_date,
    )
    return monthly_dataset.append(month, receipt)
