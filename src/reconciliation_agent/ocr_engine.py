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
import logging
import threading
from pathlib import Path
from typing import Any

from .models import OcrResult

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf", ".tiff", ".bmp"}


class OcrEngineError(RuntimeError):
    """Raised when no OCR engine could process a given file."""


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
            except Exception:  # pragma: no cover - best-effort cleanup
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
        run = completion(
            client.transport,
            model_id=model_id,
            stream=False,
            history=[
                {
                    "role": "user",
                    "content": self.OCR_PROMPT,
                    "attachments": [{"path": str(file_path.resolve())}],
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
        except Exception:  # pragma: no cover - depends on optional local SDK/worker
            logger.debug("QVAC engine unavailable", exc_info=True)
            return False

    def read(self, file_path: Path) -> OcrResult:
        try:
            return self._run(self._read_async(file_path))
        except Exception as exc:
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
            import pytesseract  # noqa: F401
            from PIL import Image  # noqa: F401

            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def read(self, file_path: Path) -> OcrResult:
        import pytesseract
        from PIL import Image

        if file_path.suffix.lower() == ".pdf":
            raise OcrEngineError(
                f"{file_path.name}: PDF input requires the QVAC engine or a "
                "pre-rasterised image; the Tesseract fallback only reads "
                "raster images (png/jpg/tiff/bmp)."
            )

        with Image.open(file_path) as img:
            text = pytesseract.image_to_string(img)
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
            raise ValueError(f"Unknown OCR engine '{name}'. Choose from: auto, {', '.join(_ENGINES)}")
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
