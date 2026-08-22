"""Monthly accumulation of WhatsApp-ingested receipts ("dataset previsorio mensual").

Each incoming attachment is OCR'd once, at ingestion time, and its
structured Receipt appended here -- reconciliation later just reads it
back, no repeated OCR. One JSONL file per calendar month: human-inspectable
and consistent with the rest of this project's "plain files, no database"
style. Sender phone number and WhatsApp message id are encoded into the
saved attachment's filename rather than added to the core Receipt model,
so this stays the only module that knows a receipt came from WhatsApp.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .models import Receipt

DATA_ROOT = Path("data/whatsapp_intake")


def attachments_dir(month: str) -> Path:
    """`month` is "YYYY-MM". Where downloaded attachments are archived for audit."""
    return DATA_ROOT / month / "attachments"


def _dataset_path(month: str) -> Path:
    return DATA_ROOT / month / "receipts.jsonl"


def _to_json(receipt: Receipt) -> dict:
    d = asdict(receipt)
    d["source_file"] = str(receipt.source_file)
    d["txn_date"] = receipt.txn_date.isoformat() if receipt.txn_date else None
    return d


def _from_json(d: dict) -> Receipt:
    return Receipt(
        source_file=Path(d["source_file"]),
        merchant=d["merchant"],
        amount=d["amount"],
        txn_date=date.fromisoformat(d["txn_date"]) if d["txn_date"] else None,
        raw_text=d.get("raw_text", ""),
        ocr_engine=d.get("ocr_engine", "unknown"),
        ocr_confidence=d.get("ocr_confidence", 1.0),
    )


def append(month: str, receipt: Receipt) -> Path:
    """Append one receipt to the given month's dataset. Returns the dataset path."""
    path = _dataset_path(month)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(_to_json(receipt)) + "\n")
    return path


def load(month: str) -> list[Receipt]:
    """Load every receipt accumulated for the given month, in ingestion order."""
    path = _dataset_path(month)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [_from_json(json.loads(line)) for line in f if line.strip()]
