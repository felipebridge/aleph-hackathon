#!/usr/bin/env python
"""Simulates a month of customers sending receipts over WhatsApp, without
needing a real Meta Business account -- see README "Demo sin API real de
WhatsApp". Each message is fed through the real OCR + extraction pipeline
and filed into data/whatsapp_intake/2026-07/.

Run with: python scripts/simulate_whatsapp_traffic.py
Then reconcile the result with:
  python main.py --whatsapp-month 2026-07 --bank-csv data/bank_statement_ar.csv
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reconciliation_agent.whatsapp.simulator import run_simulation


def main() -> None:
    run_simulation()


if __name__ == "__main__":
    main()
