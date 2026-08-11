"""Markdown rendering for Full0To10 light profile promotion."""
from __future__ import annotations

from typing import Any


def render_promotion(report: dict[str, Any]) -> str:
    lines = [
        "# Full0To10 light profile promotion",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Promotable: `{report['promotable_to_unified_launcher']}`",
        f"- Profile: `{report['light_profile_name']}`",
        f"- Launcher flag: `{report['recommended_launcher_flag']}`",
        f"- Failed steps: `{report['failed_count']}`",
        "",
        "## Missing required steps",
        "",
    ]
    for item in report["missing_required_steps"] or ["None"]:
        lines.append(f"- `{item}`")
    lines.extend(["", "## Safety violations", ""])
    for item in report["safety_violations"] or ["None"]:
        lines.append(f"- `{item}`")
    lines.extend(["", "## Next loop actions", ""])
    for item in report["next_loop_actions"]:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def build_next_loop(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "full0to10_light_profile_next_loop",
        "passed": bool(report["promotable_to_unified_launcher"]),
        "actions": report["next_loop_actions"],
        "guardrails": [
            "no provider generation in light profile",
            "no patch apply",
            "no Blender runtime",
            "no FFmpeg runtime",
            "do not delete or restore Markdown in progress",
        ],
    }
