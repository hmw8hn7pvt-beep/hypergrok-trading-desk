#!/usr/bin/env python3
"""Finite public Bybit linear quote check. Python 3.11+ standard library only."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from live_public import execute_finite_live


if __name__ == "__main__":
    raise SystemExit(execute_finite_live(sys.argv[1:]))
