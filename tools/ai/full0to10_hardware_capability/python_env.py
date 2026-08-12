"""Python runtime capability probe."""
from __future__ import annotations

import platform
import sys
from typing import Any


def build_python_env() -> dict[str, Any]:
    return {
        "executable": sys.executable,
        "version": sys.version,
        "version_info": list(sys.version_info[:3]),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
    }
