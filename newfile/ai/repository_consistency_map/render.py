"""Markdown renderer for repository consistency maps."""

from __future__ import annotations

from typing import Any


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Repository Consistency Map", ""]
    lines.append(f"- Passed: `{report['passed']}`")
    lines.append(f"- Finding count: `{report['finding_count']}`")
    lines.append(f"- Markdown files: `{report['scope']['markdown_file_count']}`")
    lines.append(f"- Python files: `{report['scope']['python_file_count']}`")
    lines.append(f"- Markdown references: `{report['scope']['markdown_reference_count']}`")
    lines.append(f"- Markdown Python commands: `{report['scope']['markdown_python_command_count']}`")
    lines.append(f"- Provider execution performed: `{report['provider_execution_performed']}`")
    if report.get("performance"):
        performance = report["performance"]
        lines.append(f"- Workers requested: `{performance.get('workers_requested')}`")
        lines.append(f"- Total build seconds: `{performance.get('total_build_report_seconds')}`")
        lines.append(f"- Markdown scan seconds: `{performance.get('markdown_scan_seconds')}`")
        lines.append(f"- Python inventory seconds: `{performance.get('python_inventory_seconds')}`")
    lines.append(f"- Patch application performed: `{report['patch_application_performed']}`")
    lines.append("")
    lines.append("## Severity counts")
    lines.append("")
    if report.get("severity_counts"):
        for key, value in report["severity_counts"].items():
            lines.append(f"- `{key}`: `{value}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Finding kind counts")
    lines.append("")
    if report.get("finding_kind_counts"):
        for key, value in report["finding_kind_counts"].items():
            lines.append(f"- `{key}`: `{value}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Findings")
    lines.append("")
    lines.append("| Severity | Kind | Source | Line | Target | Recommendation |")
    lines.append("|---|---|---|---:|---|---|")
    for item in report.get("findings", [])[:200]:
        lines.append(
            f"| `{item.get('severity')}` | `{item.get('kind')}` | `{item.get('source')}` | {item.get('line') or 0} | `{item.get('target') or item.get('flag') or ''}` | {str(item.get('recommendation') or '').replace('|', '/')} |"
        )
    if len(report.get("findings", [])) > 200:
        lines.append(f"| ... | ... | ... | ... | ... | truncated in Markdown; JSON contains {len(report['findings'])} findings |")
    lines.append("")
    lines.append("## Provider hints")
    lines.append("")
    for hint in report.get("provider_hints_for_gpu_planner", [])[:40]:
        sample_targets = ", ".join("`" + item + "`" for item in hint.get("sample_targets", [])[:5])
        lines.append(f"- `{hint.get('kind')}` count `{hint.get('count')}`; sample targets: {sample_targets}")
    return "\n".join(lines) + "\n"
