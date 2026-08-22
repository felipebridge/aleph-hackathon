#!/usr/bin/env python
"""Thin entry point: `python main.py [options]`.

See `src/reconciliation_agent/cli.py` for the actual pipeline wiring, and
`README.md` for the full usage guide.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from reconciliation_agent.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
