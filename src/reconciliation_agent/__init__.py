"""Privacy-First AI Financial Reconciliation Agent.

A 100% offline pipeline that reads physical receipts (images/PDFs), extracts
structured data with a local OCR/NLP engine (Tether QVAC SDK), and cross
references it against a bank statement export to flag billing discrepancies.

No document, image, or byte of financial data ever leaves the machine it
runs on -- there are no network calls anywhere in this package.
"""

__version__ = "0.1.0"
