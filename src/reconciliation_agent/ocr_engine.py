"""Local OCR engines.

This is the ONLY module that is allowed to touch the Tether QVAC SDK. That
isolation is deliberate: every other module in the pipeline talks to the
:class:`BaseOCREngine` interface, not to the SDK directly, so

  1. the business logic (matcher.py) never depends on how the pixels turned
     into text, and
  2. we can develop and demo the full reconciliation pipeline even before/
     without the exact QVAC SDK call signature being finalised, by swapping
     in a fallback engine -- with zero changes anywhere else.

Every engine implemented here runs 100% locally. Nothing in this file makes
a network call; that is the privacy guarantee the whole project rests on.
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

#: DPI-equivalent scale used when rasterizing a PDF page to an image.
#: 2.0 (~144 DPI at PDFium's 72-DPI base) is a good OCR-accuracy/speed
#: tradeoff for printed receipts/invoices -- higher mostly just slows down
#: Tesseract without meaningfully improving recognition on clean text.
_PDF_RENDER_SCALE = 2.0


class OcrEngineError(RuntimeError):
    """Raised when no OCR engine could process a given file."""


def _render_pdf_pages(file_path: Path):
    """Rasterize every page of a local PDF to a Pillow image.

    Uses `pypdfium2`, which bundles Google's PDFium renderer as a native
    wheel -- no system-installed PDF/Poppler binary required, keeping PDF
    support consistent with the rest of this project's "100% local, no
    extra install steps" story.
    """
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
    """Yield the list of local image paths an OCR engine should read for
    `file_path` -- the file itself for a plain image, or one temporary PNG
    per page for a PDF (cleaned up on exit).

    Centralising this means both the QVAC engine (multi-attachment chat)
    and the Tesseract engine (one `image_to_string` call per page) treat a
    multi-page PDF identically instead of duplicating rasterization logic.
    """
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
    """Wraps Tether's local `tetherto-qvac-sdk` for offline OCR + NLP.

    QVAC's client spawns (or attaches to) a local worker process and talks
    to it over an RPC transport -- there is no network socket to the
    outside world involved at any point, which is precisely why it is the
    primary engine for this project (see README for the privacy rationale).

    Integration approach: the SDK's public surface is a general local LLM
    inference client (`Client`, `load_model`, `completion(...)`), not a
    dedicated `run_ocr()` call. We get OCR + "NLP-to-Finance" in a single
    step by loading a small on-device multimodal (vision-capable) model and
    sending the receipt image as a chat `attachment` alongside a
    transcription prompt -- confirmed against the installed SDK's generated
    schema (`CompletionStreamRequestHistoryItem.attachments[].path`).

    The SDK's public API is fully async (`async with Client() as client`),
    while the rest of this pipeline is a small synchronous CLI script. To
    avoid dragging asyncio through every other module, this class owns a
    single background event loop thread and marshals calls onto it -- the
    Client, the RPC worker process, and the loaded model are all kept alive
    and reused across every receipt in the run instead of paying
    worker-startup + model-load cost per file.
    """

    name = "qvac"

    #: Small local vision-language model good enough to transcribe printed
    #: receipt text. Override via QVACOcrEngine(model_src=...) to swap in a
    #: larger/more accurate model available in your QVAC model registry.
    DEFAULT_MODEL_SRC = "SMOLVLM2_500M_MULTIMODAL_Q8_0"

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

    # --- background event-loop plumbing -----------------------------------

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

    # --- SDK plumbing -------------------------------------------------------

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

        # A multi-page PDF becomes one attachment per rasterized page --
        # the model reads the whole document in a single completion call.
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

    # --- BaseOCREngine interface --------------------------------------------

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
    """Fallback local OCR using Tesseract via pytesseract + Pillow.

    Fully offline (Tesseract is a local binary, no API calls). Used when
    the QVAC SDK is unavailable in the current dev environment, or
    explicitly requested with --ocr-engine tesseract.
    """

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
    """Deterministic OCR stand-in used for demos and unit tests.

    Reads a `<receipt>.ocr.txt` file placed next to the receipt image
    (produced by `scripts/generate_sample_data.py`) instead of doing real
    computer vision. This guarantees the end-to-end pipeline is
    demonstrable on any machine, with or without Tesseract/QVAC installed,
    which matters a lot with a 24h clock running.
    """

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
    """Resolve the requested engine name to a ready-to-use instance.

    ``auto`` (the default) tries the real, on-device AI engine first and
    transparently degrades: QVAC -> Tesseract -> deterministic mock. This
    keeps `python main.py` working out of the box during the hackathon
    regardless of which machine/demo laptop it runs on.
    """
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
