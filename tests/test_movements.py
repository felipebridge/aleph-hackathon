"""Tests de la detección ingreso/egreso según el rol de ZIRA."""

from __future__ import annotations

from reconciliation_agent import movements
from reconciliation_agent.movements import classify_direction, detect_from_text, is_zira


class TestIsZira:
    def test_por_cuit(self):
        assert is_zira(cuit="30-71111111-4") is True

    def test_por_cuit_sin_guiones(self):
        assert is_zira(cuit="30711111114") is True

    def test_por_nombre(self):
        assert is_zira("ZIRA SA") is True

    def test_nombre_pegado_por_ocr(self):
        # El OCR a veces junta "ZIRA SA" -> "ZIRASA"
        assert is_zira("ZIRASA") is True

    def test_otro_no_es_zira(self):
        assert is_zira("Norte Insumos SRL", "30-70222222-5") is False


class TestClassifyDirection:
    def test_zira_emisor_es_ingreso(self):
        assert classify_direction("ZIRA SA", "Norte Insumos SRL") == "ingreso"

    def test_zira_receptor_es_egreso(self):
        assert classify_direction("Norte Insumos SRL", "ZIRA SA") == "egreso"

    def test_sin_zira_default_egreso(self):
        assert classify_direction("Uber", "Cliente X") == "egreso"

    def test_por_cuit(self):
        assert classify_direction(
            "Emisor Cualquiera", "Otro", "30-71111111-4", "30-70222222-5"
        ) == "ingreso"


class TestDetectFromText:
    def test_zira_cuit_primero_es_ingreso(self):
        text = "ZIRA SA\nCUIT: 30-71111111-4\nCliente: Norte Insumos SRL\nCUIT: 30-70222222-5"
        d = detect_from_text(text)
        assert d["direction"] == "ingreso"
        assert d["confidence"] == "alta"
        assert d["zira_detected"] is True

    def test_zira_cuit_segundo_es_egreso(self):
        text = "Norte Insumos SRL\nCUIT: 30-70222222-5\nCliente: ZIRA SA\nCUIT: 30-71111111-4"
        d = detect_from_text(text)
        assert d["direction"] == "egreso"
        assert d["confidence"] == "alta"

    def test_contraparte_no_es_zira(self):
        text = "ZIRA SA\nCUIT: 30-71111111-4\nCliente: Norte Insumos SRL\nCUIT: 30-70222222-5"
        d = detect_from_text(text)
        assert "Norte Insumos" in d["counterparty"]

    def test_sin_zira_es_egreso(self):
        d = detect_from_text("Uber\nTotal ARS 3120.00", fallback_merchant="Uber")
        assert d["direction"] == "egreso"
        assert d["zira_detected"] is False


class TestLoadAndSummarize:
    def test_dataset_zira_clasifica_bien(self, tmp_path):
        csv = tmp_path / "mov.csv"
        csv.write_text(
            "id_transaccion,tipo_movimiento,fecha_emision,emisor,cuit_emisor,"
            "receptor,cuit_receptor,concepto,monto_neto,iva,monto_total\n"
            "TX1,ingreso,01/07/2026,ZIRA SA,30-71111111-4,Cliente SRL,30-70222222-5,"
            "Venta,1000,210,1210\n"
            "TX2,egreso,02/07/2026,Prov SA,30-70333333-6,ZIRA SA,30-71111111-4,"
            "Compra,500,105,605\n",
            encoding="utf-8",
        )
        mv = movements.load_movements(str(csv))
        assert mv[0].direction == "ingreso"
        assert mv[1].direction == "egreso"
        s = movements.summarize(mv)
        assert s["income"] == 1210.0
        assert s["expense"] == 605.0
        assert s["profit"] == 605.0
