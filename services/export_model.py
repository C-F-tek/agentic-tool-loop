"""Compatibility wrapper for the OpenVINO model export CLI."""

from __future__ import annotations

import runpy


def main() -> int:
    runpy.run_module("model_export.cli", run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

