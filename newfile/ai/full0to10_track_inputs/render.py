"""Markdown rendering for track input contract."""
from __future__ import annotations

from typing import Any


def render_contract_markdown(contract: dict[str, Any]) -> str:
    lines = [
        "# Full0To10 track input contract",
        "",
        f"- Track: `{contract['track_name']}`",
        f"- Complete: `{contract['complete']}`",
        f"- Passed: `{contract['passed']}`",
        f"- Require inputs: `{contract['require_inputs']}`",
        "",
        "## Selected inputs",
        "",
    ]
    for role in contract["required_roles"]:
        selected = contract["selected_inputs"].get(role)
        if selected:
            lines.append(f"- `{role}`: `{selected['path']}` score=`{selected['score']}`")
        else:
            lines.append(f"- `{role}`: missing")
    lines.extend(["", "## Candidate counts", ""])
    for role, candidates in contract["candidates"].items():
        lines.append(f"- `{role}`: `{len(candidates)}`")
    lines.extend(["", "## Warnings", ""])
    for warning in contract["warnings"] or ["None"]:
        lines.append(f"- {warning}")
    lines.extend(["", "## Next actions", ""])
    lines.append("Populate the template paths or place matching JSON files under output/input/data/assets.")
    lines.append("")
    return "\n".join(lines)
