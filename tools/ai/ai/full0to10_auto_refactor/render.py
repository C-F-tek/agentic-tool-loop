"""Markdown renderer for Full0To10 auto-refactor plan."""
from __future__ import annotations

from typing import Any


def render_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# Full0To10 auto-refactor and hardware optimization plan",
        "",
        f"- Passed: `{plan['passed']}`",
        f"- Records: `{plan['record_count']}`",
        f"- Candidates: `{plan['candidate_count']}`",
        f"- Hardware candidates: `{plan['hardware_candidate_count']}`",
        f"- Patch specs: `{plan['patch_spec_count']}`",
        "",
        "## Candidate summary",
        "",
    ]
    for kind, count in plan["candidate_summary"].items():
        lines.append(f"- `{kind}`: `{count}`")
    lines.extend(["", "## Hardware contract", ""])
    for key, value in plan["hardware_contract"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Top candidates", ""])
    for item in plan["candidates"][:30]:
        lines.append(f"- `{item['severity']}` `{item['kind']}` `{item['path']}` — {item['reason']}")
    lines.append("")
    return "\n".join(lines)
