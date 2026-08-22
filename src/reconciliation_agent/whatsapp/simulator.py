"""Simulates customers sending receipts over WhatsApp, for demos without a
real Meta Business account (see README "Demo sin API real de WhatsApp").

Feeds real sample files straight through the exact same `ingest_attachment`
the live webhook calls -- only the "message arrived via WhatsApp" transport
hop is faked; OCR, extraction, and dataset filing are the real thing.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from ..ocr_engine import QVACOcrEngine
from .ingest import UnsupportedAttachmentError, ingest_attachment
from .schemas import IncomingAttachment

ROOT = Path(__file__).resolve().parents[3]

_MIME_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


@dataclass(frozen=True)
class SimulatedMessage:
    file_path: Path
    from_number: str
    day: int  # day of month -- spreads timestamps believably across the month


# Real Argentine receipts already checked into data/, paired with fake
# senders and dated to match data/bank_statement_ar.csv (July 2026).
DEFAULT_MESSAGES = [
    SimulatedMessage(ROOT / "data" / "Uber_receipt_5.pdf", "5491122334455", 2),
    SimulatedMessage(ROOT / "data" / "Rappi_recibo_1.jpg", "5491133445566", 5),
    SimulatedMessage(ROOT / "data" / "PetroSur_combustible_1.pdf", "5491144556677", 8),
    SimulatedMessage(ROOT / "data" / "PeYA_muestra_1.pdf", "5491155667788", 10),
    SimulatedMessage(ROOT / "data" / "LuzSur_electricidad_1.pdf", "5491166778899", 12),
    SimulatedMessage(ROOT / "data" / "Cabify_recibo_1.pdf", "5491177889900", 15),
    SimulatedMessage(ROOT / "data" / "ExpressCourier_envio_1.jpg", "5491188990011", 18),
]


def _build_attachment(message: SimulatedMessage, index: int) -> IncomingAttachment:
    extension = message.file_path.suffix.lower()
    timestamp = int(dt.datetime(2026, 7, message.day, 10, 0, tzinfo=dt.timezone.utc).timestamp())
    return IncomingAttachment(
        message_id=f"wamid.SIMULATED{index:03d}",
        from_number=message.from_number,
        media_id=f"SIM-MEDIA-{index:03d}",
        mime_type=_MIME_BY_EXTENSION.get(extension, "application/octet-stream"),
        filename=message.file_path.name if extension == ".pdf" else None,
        timestamp=str(timestamp),
    )


def run_simulation(
    messages: list[SimulatedMessage] | None = None, console: Console | None = None
) -> list[Path]:
    """Feed each simulated message through the real ingestion pipeline.
    Returns the monthly dataset paths that were written to."""
    console = console or Console()
    messages = DEFAULT_MESSAGES if messages is None else messages
    engine = QVACOcrEngine()
    dataset_paths: list[Path] = []
    try:
        for i, message in enumerate(messages, start=1):
            attachment = _build_attachment(message, i)
            console.print(
                f"[dim]->[/dim] Simulando WhatsApp de {message.from_number} "
                f"con {message.file_path.name}"
            )
            if not message.file_path.exists():
                console.print(f"  [yellow]Saltado: no se encontró {message.file_path}[/yellow]")
                continue
            try:
                dataset_path = ingest_attachment(attachment, message.file_path.read_bytes(), engine)
                dataset_paths.append(dataset_path)
                console.print("  [green]OK[/green] agregado al dataset mensual")
            except UnsupportedAttachmentError as exc:
                console.print(f"  [red]Error:[/red] {exc}")
    finally:
        engine.close()
    return dataset_paths
