"""Tests del contenedor de facturas y las vistas de dueño/contador."""

from __future__ import annotations

import pytest

from reconciliation_agent import ledger


@pytest.fixture
def movements_csv(tmp_path):
    csv = tmp_path / "mov.csv"
    csv.write_text(
        "id_transaccion,tipo_movimiento,fecha_emision,emisor,cuit_emisor,"
        "receptor,cuit_receptor,concepto,monto_neto,iva,monto_total\n"
        "TX1,ingreso,02/07/2026,ZIRA SA,30-71111111-4,Cliente Uno SRL,30-70222222-5,"
        "Venta de software,1000,210,1210\n"
        "TX2,egreso,05/07/2026,Proveedor Dos SA,30-70333333-6,ZIRA SA,30-71111111-4,"
        "Compra de insumos,500,105,605\n"
        "TX3,egreso,08/07/2026,Proveedor Dos SA,30-70333333-6,ZIRA SA,30-71111111-4,"
        "Pago de fletes,800,168,968\n",
        encoding="utf-8",
    )
    return str(csv)


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Cada test usa su propio contenedor de facturas subidas."""
    monkeypatch.setattr(ledger, "UPLOAD_STORE", tmp_path / "uploaded.jsonl")


class TestInvoiceContainer:
    def test_dataset_invoices_clasifica(self, movements_csv):
        invs = ledger.dataset_invoices(movements_csv)
        assert len(invs) == 3
        ingresos = [i for i in invs if i["direction"] == "ingreso"]
        egresos = [i for i in invs if i["direction"] == "egreso"]
        assert len(ingresos) == 1 and len(egresos) == 2

    def test_append_uploaded_persiste(self, movements_csv):
        ledger.append_uploaded({
            "id": "UP-1", "direction": "egreso", "date": "2026-07-10",
            "counterparty": "Nuevo Prov SA", "amount": 300.0, "iva": 52.0,
            "concept": "test", "category": "Otros", "category_key": "otros",
            "category_color": "#000", "source": "upload", "fully_parsed": True,
        })
        all_inv = ledger.all_invoices(movements_csv)
        assert len(all_inv) == 4
        assert any(i["id"] == "UP-1" for i in all_inv)


class TestOwnerDashboard:
    def test_totales_incluyen_subidas(self, movements_csv):
        d = ledger.owner_dashboard(movements_csv)
        assert d["kpis"]["income"] == 1210.0
        assert d["kpis"]["expense"] == 605.0 + 968.0
        assert d["kpis"]["profit"] == 1210.0 - (605.0 + 968.0)

    def test_tiene_ambos_breakdowns(self, movements_csv):
        d = ledger.owner_dashboard(movements_csv)
        assert d["income_breakdown"] and d["expense_breakdown"]

    def test_subida_actualiza_ingreso(self, movements_csv):
        antes = ledger.owner_dashboard(movements_csv)["kpis"]["income"]
        ledger.append_uploaded({
            "id": "UP-2", "direction": "ingreso", "date": "2026-07-11",
            "counterparty": "Cliente Nuevo SA", "amount": 500.0, "iva": 86.0,
            "concept": "venta", "category": "Otros", "category_key": "otros",
            "category_color": "#000", "source": "upload", "fully_parsed": True,
        })
        despues = ledger.owner_dashboard(movements_csv)["kpis"]["income"]
        assert despues == antes + 500.0


class TestAccountantLedger:
    def test_agrupa_proveedores_con_facturas(self, movements_csv):
        led = ledger.accountant_ledger(movements_csv)
        prov = next(p for p in led["providers"] if "Dos" in p["name"])
        assert prov["count"] == 2  # TX2 y TX3
        assert prov["total"] == 605.0 + 968.0

    def test_cliente_con_sus_facturas(self, movements_csv):
        led = ledger.accountant_ledger(movements_csv)
        assert len(led["clients"]) == 1
        assert led["clients"][0]["invoices"][0]["id"] == "TX1"

    def test_detecta_duplicado_como_alerta(self, movements_csv):
        # Subimos una factura idéntica a TX1 -> alerta de duplicado.
        ledger.append_uploaded({
            "id": "UP-DUP", "direction": "ingreso", "date": "2026-07-02",
            "counterparty": "Cliente Uno SRL", "amount": 1210.0, "iva": 210.0,
            "concept": "dup", "category": "Otros", "category_key": "otros",
            "category_color": "#000", "source": "upload", "fully_parsed": True,
        })
        led = ledger.accountant_ledger(movements_csv)
        assert any("duplicado" in (a["alert"] or "").lower() for a in led["alerts"])
