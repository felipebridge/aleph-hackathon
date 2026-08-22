#!/usr/bin/env python
"""Populates several months of realistic, synthetic Argentine WhatsApp-intake
data so the web UI (Modo C) has real volume to reconcile without needing a
live QVAC worker or a real WhatsApp Business account.

This intentionally bypasses OCR: `monthly_dataset.py` stores exactly the
same thing this script writes -- an already-OCR'd `Receipt` per line, one
JSONL file per month -- so pre-building that JSONL for demo months is
faithful to the real architecture, not a shortcut around it. The one real
run driven by `scripts/simulate_whatsapp_traffic.py` (month 2026-07, real
receipts, real QVAC OCR, documented in README.md section 5) is left
untouched; this script only ever writes the earlier months below.

Run:
    python scripts/generate_whatsapp_demo_data.py
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from reconciliation_agent import monthly_dataset as ds  # noqa: E402
from reconciliation_agent.models import Receipt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

# Months this script owns. 2026-07 is reserved for the real QVAC simulator
# demo (README section 5) and is never touched here.
MONTHS = ["2026-03", "2026-04", "2026-05", "2026-06"]

_RNG_SEED = 20260822  # fixed seed -> reproducible dataset across re-runs


@dataclass(frozen=True)
class Merchant:
    name: str
    description: str
    amount_range: tuple[float, float]  # ARS


MERCHANTS = [
    Merchant("Uber", "VIAJE UBER *TRIP", (2200, 9800)),
    Merchant("Cabify", "CABIFY VIAJE APP", (2500, 8600)),
    Merchant("PedidosYa", "PEDIDOSYA DELIVERY", (4200, 15800)),
    Merchant("Rappi", "RAPPI ARGENTINA SA", (3800, 13400)),
    Merchant("PetroSur", "PETROSUR COMBUSTIBLE", (18000, 42000)),
    Merchant("LuzSur", "LUZSUR DISTRIBUIDORA ELEC", (22000, 58000)),
    Merchant("Movistar", "TELEFONICA MOVISTAR ARG", (9500, 16000)),
    Merchant("Express Courier", "EXPRESS COURIER ENVIOS", (3200, 9600)),
    Merchant("Farmacity", "FARMACITY SUCURSAL CENTRO", (5400, 21000)),
    Merchant("Carrefour", "CARREFOUR HIPERMERCADO", (28000, 96000)),
    Merchant("Coto", "COTO CICSA SUPERMERCADO", (24000, 87000)),
    Merchant("YPF", "YPF ESTACION DE SERVICIO", (16000, 45000)),
]

# Non-receipt bank movements: money that moves with no WhatsApp receipt behind
# it, on purpose, so every month also produces a couple UNACCOUNTED_CHARGE
# findings (this is what real accounting studies actually chase down).
UNRECEIPTED = [
    ("Transferencia", "TRANSFERENCIA A TERCEROS", (60000, 140000)),
    ("Mercado Pago", "PAGO MERCADO PAGO QR", (8000, 24000)),
    ("Comision Bancaria", "COMISION MANTENIMIENTO CTA", (1500, 4500)),
]


def _month_bounds(month: str) -> tuple[date, int]:
    year, mon = (int(x) for x in month.split("-"))
    days_in_month = (date(year + (mon == 12), (mon % 12) + 1, 1) - date(year, mon, 1)).days
    return date(year, mon, 1), days_in_month


def _random_date(month: str, rng: random.Random) -> date:
    start, days_in_month = _month_bounds(month)
    return start + timedelta(days=rng.randint(0, days_in_month - 1))


def _amount(merchant: Merchant, rng: random.Random) -> float:
    return round(rng.uniform(*merchant.amount_range), 2)


def _receipt(month: str, idx: int, merchant: Merchant, txn_date: date, amount: float) -> Receipt:
    phone_suffix = f"54911{idx:07d}"[:12]
    filename = f"wamid.demo_{month}_{idx:03d}_5491{phone_suffix[-8:]}.jpg"
    raw_text = (
        f"{merchant.name}\n"
        f"{merchant.description}\n"
        "--------------------------------\n"
        f"TOTAL                 ARS {amount:,.2f}\n"
        f"{txn_date.strftime('%d/%m/%Y')}"
    )
    return Receipt(
        source_file=Path(filename),
        merchant=merchant.name,
        amount=amount,
        txn_date=txn_date,
        raw_text=raw_text,
        ocr_engine="QVAC(demo-synthetic)",
        ocr_confidence=round(random.Random(idx).uniform(0.82, 0.99), 2),
    )


def build_month(month: str, rng: random.Random) -> tuple[list[Receipt], list[tuple]]:
    """Returns (whatsapp receipts to file, bank_statement rows) for one month,
    deliberately mixing in every discrepancy type the matcher detects."""
    receipts: list[Receipt] = []
    bank_rows: list[tuple] = []
    txn_seq = 1

    def next_txn_id() -> str:
        nonlocal txn_seq
        tid = f"TXN-{month.replace('-', '')}-{txn_seq:03d}"
        txn_seq += 1
        return tid

    n_clean = rng.randint(11, 15)
    n_amount_mismatch = rng.randint(2, 3)
    n_date_mismatch = rng.randint(1, 2)
    n_missing_in_bank = rng.randint(1, 2)
    n_duplicate = 1

    idx = 1
    pool = list(MERCHANTS)
    rng.shuffle(pool)

    def pick_merchant() -> Merchant:
        return pool[rng.randrange(len(pool))]

    for _ in range(n_clean):
        m = pick_merchant()
        d = _random_date(month, rng)
        amount = _amount(m, rng)
        receipts.append(_receipt(month, idx, m, d, amount))
        bank_rows.append((next_txn_id(), d.isoformat(), f"{amount:.2f}", m.name, m.description))
        idx += 1

    for _ in range(n_amount_mismatch):
        m = pick_merchant()
        d = _random_date(month, rng)
        receipt_amount = _amount(m, rng)
        bank_amount = round(receipt_amount + rng.choice([-1, 1]) * rng.uniform(500, 4000), 2)
        receipts.append(_receipt(month, idx, m, d, receipt_amount))
        bank_rows.append(
            (next_txn_id(), d.isoformat(), f"{bank_amount:.2f}", m.name, m.description)
        )
        idx += 1

    for _ in range(n_date_mismatch):
        m = pick_merchant()
        receipt_date = _random_date(month, rng)
        bank_date = receipt_date + timedelta(days=rng.choice([1, 2]))
        amount = _amount(m, rng)
        receipts.append(_receipt(month, idx, m, receipt_date, amount))
        bank_rows.append(
            (next_txn_id(), bank_date.isoformat(), f"{amount:.2f}", m.name, m.description)
        )
        idx += 1

    for _ in range(n_missing_in_bank):
        m = pick_merchant()
        d = _random_date(month, rng)
        amount = _amount(m, rng)
        receipts.append(_receipt(month, idx, m, d, amount))
        idx += 1  # no bank_rows entry -> MISSING_IN_BANK

    for _ in range(n_duplicate):
        m = pick_merchant()
        d = _random_date(month, rng)
        amount = _amount(m, rng)
        receipts.append(_receipt(month, idx, m, d, amount))
        idx += 1
        receipts.append(_receipt(month, idx, m, d, amount))  # client resent the same photo
        idx += 1
        bank_rows.append((next_txn_id(), d.isoformat(), f"{amount:.2f}", m.name, m.description))

    for name, desc, amount_range in UNRECEIPTED:
        d = _random_date(month, rng)
        amount = round(rng.uniform(*amount_range), 2)
        bank_rows.append((next_txn_id(), d.isoformat(), f"{amount:.2f}", name, desc))

    rng.shuffle(receipts)
    bank_rows.sort(key=lambda r: r[1])
    return receipts, bank_rows


def write_month(month: str, receipts: list[Receipt], bank_rows: list[tuple]) -> None:
    dataset_path = (ROOT / ds.DATA_ROOT / month / "receipts.jsonl").resolve()
    if dataset_path.exists():
        dataset_path.unlink()
    for r in receipts:
        ds.append(month, r)

    bank_csv_path = DATA_DIR / f"bank_statement_ar_{month}.csv"
    bank_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with bank_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["transaction_id", "date", "amount", "merchant", "description"])
        writer.writerows(bank_rows)

    print(
        f"{month}: {len(receipts)} recibos -> {dataset_path.relative_to(ROOT)}  |  "
        f"{len(bank_rows)} movimientos -> {bank_csv_path.relative_to(ROOT)}"
    )


def main() -> None:
    for month in MONTHS:
        rng = random.Random(f"{_RNG_SEED}-{month}")
        receipts, bank_rows = build_month(month, rng)
        write_month(month, receipts, bank_rows)

    print(f"\nDone. {len(MONTHS)} meses de datos sintéticos listos para Modo C (interfaz web).")


if __name__ == "__main__":
    main()
