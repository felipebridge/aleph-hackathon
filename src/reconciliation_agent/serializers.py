"""JSON serialization for the reconciliation domain objects.

Turns the dataclass-based `ReconciliationResult` into plain JSON-safe dicts
for the web API, so the React frontend and the server-rendered HTML report
share one canonical shape. No business logic here -- pure translation.
"""

from __future__ import annotations

from .models import (
    BankTransaction,
    Discrepancy,
    MatchedPair,
    Receipt,
    ReconciliationResult,
)

_TYPE_LABEL = {
    "AMOUNT_MISMATCH": "Monto no coincide",
    "DATE_MISMATCH": "Fecha no coincide",
    "MISSING_IN_BANK": "Falta en el banco",
    "UNACCOUNTED_CHARGE": "Cargo sin recibo",
    "DUPLICATE_RECEIPT": "Recibo duplicado",
}


def _receipt_to_dict(receipt: Receipt | None) -> dict | None:
    if receipt is None:
        return None
    return {
        "source_file": receipt.display_name,
        "merchant": receipt.merchant,
        "amount": receipt.amount,
        "txn_date": receipt.txn_date.isoformat() if receipt.txn_date else None,
        "ocr_engine": receipt.ocr_engine,
        "ocr_confidence": receipt.ocr_confidence,
    }


def _bank_txn_to_dict(bank_txn: BankTransaction | None) -> dict | None:
    if bank_txn is None:
        return None
    return {
        "transaction_id": bank_txn.transaction_id,
        "txn_date": bank_txn.txn_date.isoformat() if bank_txn.txn_date else None,
        "amount": bank_txn.amount,
        "merchant": bank_txn.merchant,
        "description": bank_txn.description,
    }


def _discrepancy_to_dict(d: Discrepancy) -> dict:
    return {
        "type": d.type.value,
        "type_label": _TYPE_LABEL.get(d.type.value, d.type.value),
        "severity": d.severity.value,
        "message": d.message,
        "delta_amount": d.delta_amount,
        "receipt": _receipt_to_dict(d.receipt),
        "bank_txn": _bank_txn_to_dict(d.bank_txn),
    }


def _matched_to_dict(m: MatchedPair) -> dict:
    return {
        "receipt": _receipt_to_dict(m.receipt),
        "bank_txn": _bank_txn_to_dict(m.bank_txn),
        "date_diff_days": m.date_diff_days,
        "notes": m.notes,
    }


def result_to_dict(result: ReconciliationResult) -> dict:
    """Serialize a full reconciliation run into a JSON-safe dict."""
    return {
        "summary": {
            "receipts_processed": result.receipts_processed,
            "bank_transactions_total": result.bank_transactions_total,
            "clean_matches": len(result.matched),
            "critical_count": result.critical_count,
            "warning_count": result.warning_count,
            "info_count": result.info_count,
        },
        "discrepancies": [_discrepancy_to_dict(d) for d in result.discrepancies],
        "matched": [_matched_to_dict(m) for m in result.matched],
    }
