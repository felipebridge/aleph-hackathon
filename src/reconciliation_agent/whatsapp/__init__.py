"""WhatsApp Business Cloud API ingestion.

Receives receipt/invoice attachments customers send over WhatsApp, downloads
them, and hands them to the same local QVAC OCR + extraction pipeline the
CLI uses for a local folder of files. This package is the only place in the
project that talks to a cloud API (Meta's) -- it only ever moves message
transport, never does AI inference. See README "Arquitectura híbrida".
"""
