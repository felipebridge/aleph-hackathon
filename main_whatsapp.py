#!/usr/bin/env python
"""Runs the WhatsApp webhook receiver locally.

    python main_whatsapp.py

To receive real messages, expose this port publicly (e.g. `ngrok http 8000`)
and point your Meta app's webhook at <public-url>/webhook, using the same
WHATSAPP_VERIFY_TOKEN configured here. Without real Meta credentials, use
`python scripts/simulate_whatsapp_traffic.py` instead -- see README
"Demo sin API real de WhatsApp".
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(
        description="WhatsApp webhook receiver for the reconciliation agent."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    args = parser.parse_args()

    uvicorn.run(
        "reconciliation_agent.whatsapp.webhook_server:app",
        host=args.host,
        port=args.port,
        app_dir=str(Path(__file__).parent / "src"),
    )


if __name__ == "__main__":
    main()
