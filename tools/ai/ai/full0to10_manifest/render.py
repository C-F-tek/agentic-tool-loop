"""Markdown rendering for Full0To10 manifests."""
from __future__ import annotations

from typing import Any


def render_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# Full0To10 run manifest",
        "",
        f"- Passed: `{manifest['passed']}`",
        f"- Artifact count: `{manifest['artifact_count']}`",
        f"- Scan roots: `{manifest['scan_roots']}`",
        "",
        "## Role summary",
        "",
    ]
    role_summary = manifest["role_summary"]
    for role, count in role_summary["role_counts"].items():
        lines.append(f"- `{role}`: `{count}`")
    lines.extend(["", "## Missing roles", ""])
    for role in role_summary["missing_roles"] or ["None"]:
        lines.append(f"- {role}")
    lines.extend(["", "## Memory", ""])
    mem = manifest["memory"]
    lines.append(f"- Scratch: `{mem['scratch_memory_path']}`")
    lines.append(f"- Persistent: `{mem['persistent_memory_path']}`")
    lines.append(f"- SQLite content included: `{mem['sqlite_content_included']}`")
    lines.extend(["", "## Hardware", ""])
    hw = manifest["hardware"]["contract"]
    for key, value in hw.items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    return "\n".join(lines)
