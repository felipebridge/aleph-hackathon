"""Tests de la agregación del dashboard: KPIs del dueño y libro mayor del contador."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from reconciliation_agent import dashboard
from reconciliation_agent.models import (
    BankTransaction,
    Discrepancy,
    DiscrepancyType,
    MatchedPair,
    Receipt,
    ReconciliationResult,
    Severity,
)


def _expense_df():
    return pd.DataFrame([
        {"transaction_id": "E1", "date": dt.date(2026, 7, 2), "amount": 3120.0,
         "merchant": "Uber", "description": "UBER"},
        {"transaction_id": "E2", "date": dt.date(2026, 7, 5), "amount": 2940.0,
         "merchant": "Rappi", "description": "RAPPI"},
    ])


def _income_df():
    return pd.DataFrame([
        {"date": dt.date(2026, 7, 3), "amount": 10000.0, "client": "Cliente A", "description": ""},
        {"date": dt.date(2026, 7, 6), "amount": 5000.0, "client": "Cliente A", "description": ""},
    ])


class TestOwnerDashboard:
    def test_kpis_calcula_ganancia(self):
        d = dashboard.owner_dashboard(_income_df(), _expense_df())
        assert d["kpis"]["income"] == 15000.0
        assert d["kpis"]["expense"] == 6060.0
        assert d["kpis"]["profit"] == 8940.0

    def test_desglose_por_rubro_presente(self):
        d = dashboard.owner_dashboard(_income_df(), _expense_df())
        keys = {b["key"] for b in d["expense_breakdown"]}
        assert "transporte" in keys and "comida" in keys

    def test_flujo_diario_ordenado(self):
        d = dashboard.owner_dashboard(_income_df(), _expense_df())
        dates = [f["date"] for f in d["daily_flow"]]
        assert dates == sorted(dates)


class TestProviderLedger:
    def _receipt(self, merchant, amount, day):
        return Receipt(source_file=None, merchant=merchant, amount=amount,
                       txn_date=dt.date(2026, 7, day))

    def _bank(self, tid, merchant, amount, day):
        return BankTransaction(transaction_id=tid, txn_date=dt.date(2026, 7, day),
                               amount=amount, merchant=merchant)

    def test_match_limpio_queda_ok(self):
        result = ReconciliationResult()
        result.matched.append(MatchedPair(
            receipt=self._receipt("Uber", 3120.0, 2),
            bank_txn=self._bank("E1", "Uber", 3120.0, 2),
            date_diff_days=0,
        ))
        ledger = dashboard.provider_ledger(result)
        uber = next(p for p in ledger if p["name"] == "Uber")
        assert uber["estado"] == "ok"
        assert uber["balance"] == 0.0

    def test_amount_mismatch_queda_diferencia(self):
        result = ReconciliationResult()
        result.discrepancies.append(Discrepancy(
            type=DiscrepancyType.AMOUNT_MISMATCH, severity=Severity.CRITICAL,
            message="", receipt=self._receipt("LuzSur", 15000.0, 12),
            bank_txn=self._bank("E5", "LuzSur", 18500.0, 12), delta_amount=3500.0,
        ))
        ledger = dashboard.provider_ledger(result)
        luz = next(p for p in ledger if p["name"] == "LuzSur")
        assert luz["estado"] == "diferencia"
        assert luz["balance"] == 3500.0

    def test_unaccounted_charge_queda_sin_comprobante(self):
        result = ReconciliationResult()
        result.discrepancies.append(Discrepancy(
            type=DiscrepancyType.UNACCOUNTED_CHARGE, severity=Severity.CRITICAL,
            message="", bank_txn=self._bank("E9", "Transferencia", 95000.0, 22),
        ))
        ledger = dashboard.provider_ledger(result)
        t = next(p for p in ledger if p["name"] == "Transferencia")
        assert t["estado"] == "sin_comprobante"
        assert t["paid"] == 95000.0

    def test_asigna_id_estable(self):
        result = ReconciliationResult()
        result.matched.append(MatchedPair(
            receipt=self._receipt("Uber", 100.0, 2),
            bank_txn=self._bank("E1", "Uber", 100.0, 2), date_diff_days=0,
        ))
        a = dashboard.provider_ledger(result)[0]["id"]
        b = dashboard.provider_ledger(result)[0]["id"]
        assert a == b and a.startswith("PROV-")


class TestClientLedger:
    def test_agrupa_por_cliente(self):
        ledger = dashboard.client_ledger(_income_df())
        assert len(ledger) == 1
        assert ledger[0]["collected"] == 15000.0
        assert ledger[0]["invoices"] == 2
        assert ledger[0]["id"].startswith("CLI-")
