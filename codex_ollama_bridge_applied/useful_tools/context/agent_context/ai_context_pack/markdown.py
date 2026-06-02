"""Markdown renderers for AI context packs."""

from __future__ import annotations

from typing import Any

def render_pack_markdown(pack: dict[str, Any]) -> str:
    lines = [f"# AI Context Pack: {pack['profile']}", ""]
    lines.append(f"- Generated at: `{pack['generated_at']}`")
    lines.append(f"- Passed: `{pack['passed']}`")
    lines.append(f"- Provider execution performed: `{pack['provider_execution_performed']}`")
    lines.append(f"- Included files: `{pack['included_file_count']}/{pack['file_count']}`")
    lines.append(f"- Included chars: `{pack['total_included_chars']}`")
    lines.append("")
    lines.append("## Validation Commands")
    lines.append("")
    for command in pack.get("validation_commands") or []:
        lines.append(f"- `{command}`")
    lines.append("")
    lines.append("## Stop Conditions")
    lines.append("")
    for condition in pack.get("stop_conditions") or []:
        lines.append(f"- {condition}")
    lines.append("")
    lines.append("## Files")
    lines.append("")
    for item in pack.get("files") or []:
        lines.append(
            f"- `{item['path']}` ({item['role']}): included `{item['included']}`, "
            f"required `{item['required']}`, truncated `{item['truncated']}`"
        )
    lines.append("")
    lines.append("## Content")
    lines.append("")
    for item in pack.get("files") or []:
        if not item.get("included"):
            continue
        lines.append(f"### `{item['path']}`")
        lines.append("")
        lines.append("```text")
        lines.append(str(item.get("content") or ""))
        lines.append("```")
        lines.append("")
    return "\n".join(lines)

def render_evidence_markdown(evidence: dict[str, Any]) -> str:
    lines = [f"# AI Context Pack Evidence: {evidence['profile']}", ""]
    lines.append(f"- Generated at: `{evidence['generated_at']}`")
    lines.append(f"- Passed: `{evidence['passed']}`")
    lines.append(f"- Provider execution performed: `{evidence['provider_execution_performed']}`")
    lines.append(f"- Source pack: `{evidence['source_pack']}`")
    lines.append(f"- Included files: `{evidence['included_file_count']}/{evidence['file_count']}`")
    lines.append(f"- Truncated files: `{evidence['truncated_file_count']}`")
    lines.append(f"- Forbidden path count: `{evidence['forbidden_path_count']}`")
    lines.append(f"- Blender runtime touched: `{evidence['blender_runtime_touched']}`")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    for key, value in evidence["decision"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## Included Paths")
    lines.append("")
    for item in evidence["included_paths"]:
        lines.append(
            f"- `{item['path']}` ({item['role']}): included `{item['included']}`, "
            f"required `{item['required']}`, truncated `{item['truncated']}`"
        )
    lines.append("")
    lines.append(
        "This evidence summarizes a local context pack. It does not prove provider execution and does not include source changes."
    )
    return "\n".join(lines) + "\n"
