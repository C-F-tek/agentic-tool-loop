"""State object for heap startup reload."""

from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ReloadRun:
    args: Namespace
    repo_root: Path
    stamp: str
    project_python: str
    output_dir: Path
    request_text: str
    artifacts: dict[str, str] = field(default_factory=dict)
    commands: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    context_files: list[str] = field(default_factory=list)
    context_pack_result: dict[str, Any] = field(default_factory=dict)
    context_delta: dict[str, Any] = field(default_factory=dict)
    repo_scan_index: dict[str, Any] = field(default_factory=dict)
