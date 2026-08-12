"""Markdown renderer for Full0To10 quality gate."""
from __future__ import annotations

from typing import Any


def render_markdown(report: dict[str, Any]) -> str:
    readiness = report["readiness"]
    lines = [
        "# Full0To10 quality gate",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Score: `{readiness['score']}`",
        f"- Ready for real run: `{readiness['ready_for_real_run']}`",
        "",
        "## Main objective",
        "",
    ]
    for item in report["main_objective"]:
        lines.append(f"- {item}")

    lines.extend(["", "## Blockers", ""])
    for item in readiness["blockers"] or ["None"]:
        lines.append(f"- {item}")

    lines.extend(["", "## Warnings", ""])
    for item in readiness["warnings"] or ["None"]:
        lines.append(f"- {item}")

    lines.extend(["", "## Split advisory", ""])
    advisory = report["split_advisory"]
    lines.append(f"- Patch specs: `{advisory['spec_count']}`")
    lines.append(f"- Markdown splits suggested: `{len(advisory['useful_markdown_splits'])}`")
    lines.append(f"- Code splits suggested: `{len(advisory['useful_code_splits'])}`")
    lines.append(f"- Hardware contract suggestions: `{len(advisory['hardware_contract_suggestions'])}`")
    lines.append("")
    return "\n".join(lines)
