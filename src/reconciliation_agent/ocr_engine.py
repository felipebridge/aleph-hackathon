"""Local OCR engines -- the only module allowed to touch the QVAC SDK.

Everything else talks to :class:`BaseOCREngine`, not the SDK directly, so
swapping engines never touches business logic. Every engine here runs
100% locally -- no network calls anywhere in this file.
"""

from __future__ import annotations

import abc
import asyncio
import contextlib
import logging
import tempfile
import threading
from pathlib import Path
from typing import Any

from .models import OcrResult

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf", ".tiff", ".bmp"}

_PDF_RENDER_SCALE = 2.0  # ~144 DPI: good OCR accuracy/speed tradeoff for printed receipts


class OcrEngineError(RuntimeError):
    """Raised when no OCR engine could process a given file."""


def _render_pdf_pages(file_path: Path):
    """Rasterize every page of a PDF to a Pillow image (pypdfium2, no system Poppler needed)."""
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise OcrEngineError(
            f"{file_path.name}: reading PDFs requires the `pypdfium2` package "
            "(`pip install pypdfium2`)."
        ) from exc

    pdf = pdfium.PdfDocument(str(file_path))
    try:
        return [pdf[i].render(scale=_PDF_RENDER_SCALE).to_pil() for i in range(len(pdf))]
    finally:
        pdf.close()


@contextlib.contextmanager
def _resolve_attachment_paths(file_path: Path):
    """Yield image paths to OCR: the file itself, or one temp PNG per PDF page."""
    if file_path.suffix.lower() != ".pdf":
        yield [file_path]
        return

    pages = _render_pdf_pages(file_path)
    with tempfile.TemporaryDirectory(prefix="reconciliation_agent_pdf_") as tmp_dir:
        page_paths = []
        for i, page_image in enumerate(pages):
            page_path = Path(tmp_dir) / f"{file_path.stem}_page{i + 1}.png"
            page_image.save(page_path)
            page_paths.append(page_path)
        yield page_paths


class BaseOCREngine(abc.ABC):
    """Common interface every OCR backend must implement."""

    name: str = "base"

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Cheap check: can this engine actually run on this machine?"""

    @abc.abstractmethod
    def read(self, file_path: Path) -> OcrResult:
        """Run OCR on a single receipt file and return the raw text."""


class QVACOcrEngine(BaseOCREngine):
    """Offline OCR + NLP via Tether's local `tetherto-qvac-sdk`.

    The SDK's client spawns a local worker process and talks RPC to it --
    no network socket involved. Its public surface is a general LLM client
    (`Client`, `load_model`, `completion`), not a dedicated `run_ocr()`, so
    OCR happens by loading a small on-device vision model and sending the
    receipt image as a chat attachment alongside a transcription prompt.

    The SDK is async; the rest of this CLI isn't. Rather than dragging
    asyncio through every module, this class runs a background event-loop
    thread and marshals calls onto it, keeping the worker process and
    loaded model warm across every receipt instead of restarting per file.
    """

    name = "qvac"
    DEFAULT_MODEL_SRC = "SMOLVLM2_500M_MULTIMODAL_Q8_0"  # override via model_src=...

    OCR_PROMPT = (
        "You are a receipt-scanning OCR engine. Transcribe every line of "
        "text visible in this receipt image exactly as printed -- store "
        "name, items, subtotal, tax, and the final TOTAL amount -- "
        "preserving line breaks. Output only the transcribed text, "
        "nothing else, no commentary."
    )

    def __init__(self, model_src: Any = None) -> None:
        self._model_src = model_src
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._client = None
        self._model_id: str | None = None

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            loop = asyncio.new_event_loop()
            thread = threading.Thread(target=loop.run_forever, daemon=True, name="qvac-sdk-loop")
            thread.start()
            self._loop, self._thread = loop, thread
        return self._loop

    def _run(self, coro):
        loop = self._ensure_loop()
        return asyncio.run_coroutine_threadsafe(coro, loop).result()

    def close(self) -> None:
        """Release the worker process/event-loop thread. Safe to call multiple times."""
        if self._loop is None:
            return
        if self._client is not None:
            try:
                self._run(self._client.close())
            except Exception:  # pragma: no cover - best-effort cleanup, never fatal
                logger.debug("Error closing QVAC client", exc_info=True)
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._loop, self._thread, self._client, self._model_id = None, None, None, None

    async def _ensure_client(self):
        if self._client is None:
            from tetherto.qvac_sdk import Client

            client = Client()
            await client.connect()
            self._client = client
        return self._client

    async def _ensure_model(self) -> str:
        client = await self._ensure_client()
        if self._model_id is None:
            from tetherto.qvac_sdk import load_model
            from tetherto.qvac_sdk import models as qvac_models

            model_src = self._model_src or getattr(qvac_models, self.DEFAULT_MODEL_SRC)
            self._model_id = await load_model(client.transport, model_src=model_src)
        return self._model_id

    async def _read_async(self, file_path: Path) -> OcrResult:
        from tetherto.qvac_sdk import completion

        client = await self._ensure_client()
        model_id = await self._ensure_model()

        # Multi-page PDF -> one attachment per rasterized page in one call.
        with _resolve_attachment_paths(file_path) as attachment_paths:
            run = completion(
                client.transport,
                model_id=model_id,
                stream=False,
                history=[
                    {
                        "role": "user",
                        "content": self.OCR_PROMPT,
                        "attachments": [{"path": str(p.resolve())} for p in attachment_paths],
                    }
                ],
            )
            final = await run.final
        return OcrResult(text=final.content_text, engine_name=self.name, confidence=1.0)

    def is_available(self) -> bool:
        try:
            self._run(self._ensure_client())
            return True
        except Exception:  # pragma: no cover - best-effort availability probe
            logger.debug("QVAC engine unavailable", exc_info=True)
            return False

    def read(self, file_path: Path) -> OcrResult:
        try:
            return self._run(self._read_async(file_path))
        except Exception as exc:  # converted to a domain-specific OcrEngineError below
            raise OcrEngineError(
                f"QVAC OCR failed for {file_path.name}: {exc}. Install with "
                "`pip install tetherto-qvac-sdk` and ensure its local worker "
                "binary is available, or select a fallback engine with "
                "--ocr-engine tesseract|mock."
            ) from exc


class TesseractOCREngine(BaseOCREngine):
    """Fallback OCR using the local Tesseract binary via pytesseract."""

    name = "tesseract"

    def is_available(self) -> bool:
        try:
            import pytesseract
            from PIL import Image  # noqa: F401 -- import-tested, not used directly here

            pytesseract.get_tesseract_version()
            return True
        except Exception:  # noqa: BLE001 -- best-effort availability probe, any failure means "no"
            return False

    def read(self, file_path: Path) -> OcrResult:
        import pytesseract
        from PIL import Image

        # A PDF is rasterized to one image per page (via pypdfium2, still
        # fully local/offline) and OCR'd page by page; a plain image is
        # OCR'd directly. Either way the result is one merged text block.
        with _resolve_attachment_paths(file_path) as page_paths:
            page_texts = []
            for page_path in page_paths:
                with Image.open(page_path) as img:
                    page_texts.append(pytesseract.image_to_string(img))

        text = "\n\n".join(page_texts)
        return OcrResult(text=text, engine_name=self.name, confidence=0.85)


class SidecarMockEngine(BaseOCREngine):
    """Reads a `<receipt>.ocr.txt` sidecar instead of doing real OCR -- keeps the
    pipeline demoable without Tesseract or a QVAC worker installed."""

    name = "mock"

    def is_available(self) -> bool:
        return True

    def read(self, file_path: Path) -> OcrResult:
        sidecar = file_path.with_suffix(file_path.suffix + ".ocr.txt")
        if not sidecar.exists():
            raise OcrEngineError(
                f"No mock OCR sidecar found for {file_path.name} "
                f"(expected {sidecar.name}). Run "
                "`python scripts/generate_sample_data.py` or choose a real "
                "OCR engine with --ocr-engine tesseract."
            )
        text = sidecar.read_text(encoding="utf-8")
        return OcrResult(text=text, engine_name=self.name, confidence=1.0)


_ENGINES: dict[str, type[BaseOCREngine]] = {
    "qvac": QVACOcrEngine,
    "tesseract": TesseractOCREngine,
    "mock": SidecarMockEngine,
}


def get_ocr_engine(name: str = "auto") -> BaseOCREngine:
    """Resolve an engine name to a ready instance. "auto" degrades QVAC -> Tesseract -> mock."""
    if name != "auto":
        cls = _ENGINES.get(name)
        if cls is None:
            raise ValueError(
                f"Unknown OCR engine '{name}'. Choose from: auto, {', '.join(_ENGINES)}"
            )
        engine = cls()
        if not engine.is_available():
            raise OcrEngineError(f"Requested OCR engine '{name}' is not available on this machine.")
        return engine

    for engine_name in ("qvac", "tesseract", "mock"):
        engine = _ENGINES[engine_name]()
        if engine.is_available():
            logger.info("Using OCR engine: %s", engine_name)
            return engine

    # SidecarMockEngine.is_available() always returns True, so this branch
    # is unreachable in practice -- kept as an explicit, honest failure mode.
    raise OcrEngineError("No OCR engine available (not even the mock fallback).")
