"""Unit tests for the local web UI (QVAC OCR mocked, no real worker needed)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from fastapi.testclient import TestClient

from reconciliation_agent import monthly_dataset as ds
from reconciliation_agent.models import OcrResult, Receipt
from reconciliation_agent.ocr_engine import QVACOcrEngine
from reconciliation_agent.webapp import app


def _bank_csv(tmp_path: Path) -> Path:
    path = tmp_path / "bank.csv"
    path.write_text(
        "transaction_id,date,amount,merchant,description\n"
        "TXN-1,2026-08-10,4.75,Starbucks,STARBUCKS STORE #4521\n",
        encoding="utf-8",
    )
    return path


class TestIndex:
    def test_root_serves_spa_or_build_hint(self):
        client = TestClient(app)
        response = client.get("/")
        assert response.status_code == 200
        # Either the built SPA shell or the "not built yet" hint -- both 200.
        assert "<div id=\"root\">" in response.text or "npm run build" in response.text

    def test_classic_form_still_available(self):
        client = TestClient(app)
        response = client.get("/classic")
        assert response.status_code == 200
        assert "Reconciliar" in response.text

    def test_lists_available_whatsapp_months(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ds, "DATA_ROOT", tmp_path)
        ds.append(
            "2026-07",
            Receipt(source_file=Path("x.jpg"), merchant="Rappi", amount=1.0, txn_date=None),
        )
        response = TestClient(app).get("/classic")
        assert "2026-07" in response.text


class TestReconcileFromFolder:
    def test_processes_receipts_dir_with_mocked_ocr(self, tmp_path, monkeypatch):
        receipts_dir = tmp_path / "receipts"
        receipts_dir.mkdir()
        (receipts_dir / "receipt.png").write_bytes(b"fake")

        monkeypatch.setattr(
            QVACOcrEngine,
            "is_available",
            lambda self: True,
        )
        monkeypatch.setattr(
            QVACOcrEngine,
            "read",
            lambda self, path: OcrResult(
                text="Starbucks\nTOTAL $4.75\n08/10/2026", engine_name="qvac"
            ),
        )

        client = TestClient(app)
        response = client.post(
            "/reconcile",
            data={
                "source": "folder",
                "receipts_dir": str(receipts_dir),
                "bank_csv": str(_bank_csv(tmp_path)),
            },
        )

        assert response.status_code == 200
        assert "Clean matches" in response.text
        assert "Nueva reconciliación" in response.text

    def test_missing_receipts_dir_shows_error_not_500(self, tmp_path):
        client = TestClient(app)
        response = client.post(
            "/reconcile",
            data={
                "source": "folder",
                "receipts_dir": str(tmp_path / "does-not-exist"),
                "bank_csv": str(_bank_csv(tmp_path)),
            },
        )
        assert response.status_code == 200
        assert "error" in response.text.lower()

    def test_qvac_unavailable_shows_actionable_error(self, tmp_path, monkeypatch):
        receipts_dir = tmp_path / "receipts"
        receipts_dir.mkdir()
        (receipts_dir / "receipt.png").write_bytes(b"fake")
        monkeypatch.setattr(QVACOcrEngine, "is_available", lambda self: False)

        client = TestClient(app)
        response = client.post(
            "/reconcile",
            data={
                "source": "folder",
                "receipts_dir": str(receipts_dir),
                "bank_csv": str(_bank_csv(tmp_path)),
            },
        )
        assert "QVAC_SDK_DIR" in response.text

    def test_falls_back_to_sidecar_when_qvac_unavailable(self, tmp_path, monkeypatch):
        # QVAC down, but a pre-computed .ocr.txt sidecar exists -> pipeline runs.
        receipts_dir = tmp_path / "receipts"
        receipts_dir.mkdir()
        (receipts_dir / "starbucks.png").write_bytes(b"fake")
        (receipts_dir / "starbucks.png.ocr.txt").write_text(
            "Starbucks\nTotal $4.75\n2026-08-10", encoding="utf-8"
        )
        monkeypatch.setattr(QVACOcrEngine, "is_available", lambda self: False)

        client = TestClient(app)
        response = client.post(
            "/api/reconcile",
            data={
                "source": "folder",
                "receipts_dir": str(receipts_dir),
                "bank_csv": str(_bank_csv(tmp_path)),
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["summary"]["clean_matches"] == 1


class TestReconcileFromWhatsapp:
    def test_reconciles_the_selected_month(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ds, "DATA_ROOT", tmp_path)
        ds.append(
            "2026-08",
            Receipt(
                source_file=Path("wamid.X_5491100000000.jpg"),
                merchant="Starbucks",
                amount=4.75,
                txn_date=dt.date(2026, 8, 10),
            ),
        )

        client = TestClient(app)
        response = client.post(
            "/reconcile",
            data={
                "source": "whatsapp",
                "whatsapp_month": "2026-08",
                "bank_csv": str(_bank_csv(tmp_path)),
            },
        )

        assert response.status_code == 200
        assert "Clean matches" in response.text

    def test_no_month_selected_shows_error(self, tmp_path):
        client = TestClient(app)
        response = client.post(
            "/reconcile",
            data={
                "source": "whatsapp",
                "whatsapp_month": "",
                "bank_csv": str(_bank_csv(tmp_path)),
            },
        )
        assert "Elegí un mes" in response.text


class TestReconcileBankCsvErrors:
    def test_missing_bank_csv_shows_error_not_500(self, tmp_path):
        client = TestClient(app)
        response = client.post(
            "/reconcile",
            data={"source": "folder", "bank_csv": str(tmp_path / "nope.csv")},
        )
        assert response.status_code == 200
        assert "error" in response.text.lower()
