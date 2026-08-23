"""QVAC-backed local OCR. This is the only module that touches the SDK.

Everything else talks to :class:`OcrResult`, not the SDK directly, so the
business logic never depends on how the pixels turned into text. Inference
runs entirely on-device via QVAC's local worker process -- no cloud calls,
no other model provider anywhere in this file.
"""

from __future__ import annotations

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
    """Raised when the QVAC engine could not process a given file."""


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


class QVACOcrEngine:
    """Offline OCR + NLP via Tether's local `tetherto-qvac-sdk`.

    The SDK's client spawns a local worker process and talks RPC to it --
    no network socket involved. Its public surface is a general LLM client
    (`Client`, `load_model`, `completion`), not a dedicated `run_ocr()`, so
    OCR happens by loading an on-device vision model and sending the receipt
    image as a chat attachment alongside a transcription prompt.

    The SDK is async; the rest of this CLI isn't. Rather than dragging
    asyncio through every module, this class runs a background event-loop
    thread and marshals calls onto it, keeping the worker process and
    loaded model warm across every receipt instead of restarting per file.
    """

    name = "qvac"
    DEFAULT_MODEL_SRC = "OCR_3B_MULTIMODAL_Q4_0"  # override via model_src=...
    # Vision models need a paired "projection" model to actually read images;
    # without it the worker rejects attachments with "Media not supported by
    # text-only models". Only auto-paired when using the default model above.
    DEFAULT_PROJECTION_MODEL_SRC = "MMPROJ_OCR_3B_MULTIMODAL_Q8_0"

    # Deliberately minimal: this OCR-specialized model is sensitive to extra
    # phrasing. Adding "store name, items, subtotal, TOTAL..." hints, or a
    # "plain text only, no bounding boxes" instruction, both made it return
    # an empty completion instead of transcribing anything -- tested against
    # the real worker, not guessed. It already outputs its own layout markup
    # (bounding boxes, <table> tags) unprompted; extractor.py strips that.
    OCR_PROMPT = (
        "Transcribe every line of text visible in this receipt image "
        "exactly as printed, preserving line breaks."
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

            model_config = None
            if self._model_src is None:
                projection_src = getattr(qvac_models, self.DEFAULT_PROJECTION_MODEL_SRC).src
                model_config = {"projectionModelSrc": projection_src}
            model_src = self._model_src or getattr(qvac_models, self.DEFAULT_MODEL_SRC)
            self._model_id = await load_model(
                client.transport, model_src=model_src, model_config=model_config
            )
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
            raise OcrEngineError(f"QVAC OCR failed for {file_path.name}: {exc}") from exc


def get_ocr_engine() -> QVACOcrEngine:
    """Construct the QVAC engine; fails loudly (never silently) if the local worker isn't set up."""
    engine = QVACOcrEngine()
    if not engine.is_available():
        raise OcrEngineError(
            "QVAC worker not found. Install it with `npm install -g @qvac/sdk@0.17.1`, "
            "set QVAC_SDK_DIR to the installed package directory, and see "
            "https://docs.qvac.tether.io/system-requirements/ for supported platforms."
        )
    return engine


class TesseractOcrEngine:
    """OCR local vía Tesseract, para leer imágenes/PDF arbitrarios cuando el
    worker de QVAC no está disponible.

    Corre 100% en la máquina (binario local, sin red), así que preserva la
    propiedad de privacidad del proyecto. Se usa como respaldo del OCR primario
    (QVAC) para el flujo de "subir una foto cualquiera" del contador.
    """

    name = "tesseract"

    def is_available(self) -> bool:
        try:
            import pytesseract

            pytesseract.get_tesseract_version()
            return True
        except Exception:  # noqa: BLE001 -- cualquier fallo => no disponible
            return False

    def read(self, file_path: Path) -> OcrResult:
        import pytesseract
        from PIL import Image

        # PDF -> una imagen por página (pypdfium2, local); imagen -> directo.
        with _resolve_attachment_paths(file_path) as page_paths:
            texts = []
            for page_path in page_paths:
                with Image.open(page_path) as img:
                    # Español + inglés: los comprobantes AR mezclan ambos.
                    try:
                        texts.append(pytesseract.image_to_string(img, lang="spa+eng"))
                    except pytesseract.TesseractError:
                        texts.append(pytesseract.image_to_string(img))
        return OcrResult(text="\n\n".join(texts), engine_name=self.name, confidence=0.8)

    def close(self) -> None:  # simetría con QVACOcrEngine
        pass


class SidecarOcrEngine:
    """Deterministic OCR fallback for demos when the QVAC worker isn't installed.

    Reads a pre-computed `<receipt>.ocr.txt` sidecar next to each file instead
    of running a live vision model. This is NOT a substitute for real OCR --
    the sidecar text was itself produced offline -- but it keeps the web demo
    and the pipeline runnable end-to-end on a machine without the ~2.2 GB QVAC
    worker set up. QVAC remains the primary engine; this only kicks in when it
    is unavailable and a sidecar exists.
    """

    name = "sidecar"

    @staticmethod
    def sidecar_path(file_path: Path) -> Path:
        return file_path.with_suffix(file_path.suffix + ".ocr.txt")

    def has_sidecar(self, file_path: Path) -> bool:
        return self.sidecar_path(file_path).exists()

    def is_available(self) -> bool:
        return True

    def read(self, file_path: Path) -> OcrResult:
        sidecar = self.sidecar_path(file_path)
        if not sidecar.exists():
            raise OcrEngineError(
                f"No OCR sidecar found for {file_path.name} (expected {sidecar.name})."
            )
        return OcrResult(text=sidecar.read_text(encoding="utf-8"), engine_name=self.name)

    def close(self) -> None:  # symmetry with QVACOcrEngine; nothing to release
        pass
