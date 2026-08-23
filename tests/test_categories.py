"""Tests de la clasificación de comercios en rubros de gasto."""

from __future__ import annotations

from reconciliation_agent.categories import categorize, category_breakdown


class TestCategorize:
    def test_uber_es_transporte(self):
        assert categorize("Uber").key == "transporte"

    def test_cabify_es_transporte(self):
        assert categorize("Cabify Viaje AR").key == "transporte"

    def test_rappi_es_comida(self):
        assert categorize("Rappi").key == "comida"

    def test_pedidosya_es_comida(self):
        assert categorize("PedidosYa Delivery").key == "comida"

    def test_petrosur_es_combustible(self):
        assert categorize("PETROSUR COMBUSTIBLES S.A.").key == "combustible"

    def test_luzsur_es_servicios(self):
        assert categorize("LuzSur Distribuidora").key == "servicios"

    def test_courier_es_logistica(self):
        assert categorize("Express Courier S.R.L.").key == "logistica"

    def test_transferencia_es_pagos(self):
        assert categorize("Transferencia").key == "pagos"

    def test_mercado_pago_es_pagos(self):
        assert categorize("Mercado Pago").key == "pagos"

    def test_afip_es_impuestos(self):
        assert categorize("AFIP MONOTRIBUTO").key == "impuestos"

    def test_desconocido_cae_en_otros(self):
        assert categorize("Comercio Rarísimo XYZ").key == "otros"

    def test_none_cae_en_otros(self):
        assert categorize(None).key == "otros"

    def test_ignora_acentos(self):
        # "envío" debe matchear la keyword "envio"
        assert categorize("Servicio de Envío Rápido").key == "logistica"


class TestCategoryBreakdown:
    def test_agrupa_y_suma_por_rubro(self):
        items = [("Uber", 1000.0), ("Cabify", 500.0), ("Rappi", 300.0)]
        breakdown = category_breakdown(items)
        transporte = next(b for b in breakdown if b["key"] == "transporte")
        assert transporte["amount"] == 1500.0

    def test_porcentajes_suman_cien(self):
        items = [("Uber", 750.0), ("Rappi", 250.0)]
        breakdown = category_breakdown(items)
        assert round(sum(b["percent"] for b in breakdown)) == 100

    def test_ordenado_de_mayor_a_menor(self):
        items = [("Rappi", 100.0), ("Uber", 900.0)]
        breakdown = category_breakdown(items)
        assert breakdown[0]["key"] == "transporte"

    def test_lista_vacia_no_rompe(self):
        assert category_breakdown([]) == []
