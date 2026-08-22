#!/usr/bin/env python
"""Runs the local web UI for the reconciliation agent.

    python main_web.py

Then open http://127.0.0.1:8080 in a browser. Requires the QVAC worker
installed for the "carpeta local" source (see README); the "WhatsApp"
source just reads the already-OCR'd monthly dataset, no QVAC needed at
request time.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Web UI for the reconciliation agent.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Bind port (default: 8080)")
    args = parser.parse_args()

    uvicorn.run(
        "reconciliation_agent.webapp:app",
        host=args.host,
        port=args.port,
        app_dir=str(Path(__file__).parent / "src"),
    )


if __name__ == "__main__":
    main()
