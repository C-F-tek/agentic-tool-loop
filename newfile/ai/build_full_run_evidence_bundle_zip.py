#!/usr/bin/env python3
"""CLI entrypoint for recursive Full0To10 evidence ZIP bundle creation."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Tools.ai.full_run_bundle_zip.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
