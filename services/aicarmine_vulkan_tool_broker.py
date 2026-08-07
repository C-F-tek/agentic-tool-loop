from __future__ import annotations

import sys
import os

# Add repo root to PYTHONPATH for module resolution
repo_root = os.path.dirname(os.path.abspath(__file__))
if repo_root not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aicarmine_broker.app import app

__all__ = ["app"]
