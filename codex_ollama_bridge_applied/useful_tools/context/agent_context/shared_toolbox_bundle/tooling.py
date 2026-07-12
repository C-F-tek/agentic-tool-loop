from __future__ import annotations

from .common import *  # noqa: F403

def runtime_tool_capabilities() -> list[dict[str, Any]]:
    """Build tool capability rows from the broker allowlist, not a duplicate list."""
    rows: list[dict[str, Any]] = []
    for name in sorted(TOOL_SPECS):
        spec = TOOL_SPECS[name]
        rows.append(
            {
                "tool_name": spec.name,
                "category": classify_tool_category(spec.name),
                "safe_default_mode": (
                    "report-only"
                    if spec.name != "runtime_sqlite_memory"
                    else "controlled read-only/status by default"
                ),
                "what_it_can_do": [spec.description],
                "what_it_must_not_do": tool_must_not_do(spec.name),
                "recommended_next_use": recommended_tool_use(spec.name),
                "allowed_args": list(spec.allowed_args),
            }
        )
    return rows

def classify_tool_category(tool_name: str) -> str:
    if "inventory" in tool_name or "line_count" in tool_name:
        return "inventory"
    if tool_name.startswith("check_") or tool_name.endswith("_smoke"):
        return "validation"
    if "context" in tool_name:
        return "context"
    if "sqlite" in tool_name or "memory" in tool_name:
        return "memory_status"
    if "code_interpreter" in tool_name:
        return "static_analysis"
    return "support_tool"

def tool_must_not_do(tool_name: str) -> list[str]:
    base = [
        "execute arbitrary shell commands",
        "apply patches",
        "run Blender runtime",
        "commit output artifacts",
    ]
    if tool_name == "runtime_sqlite_memory":
        base.append("write persistent memory without explicit confirmation and authorization")
    else:
        base.append("write SQLite or persistent memory")
    return base

def recommended_tool_use(tool_name: str) -> str:
    mapping = {
        "build_python_line_count_csv": "Refresh complete Python inventory before refactor planning.",
        "build_agent_memory_inventory": "Summarize durable project memory as read-only context.",
        "build_agent_agnostic_tool_inventory": "Discover reusable tooling before adding new scripts.",
        "build_agent_transient_request_context": "Assemble request-scoped context for local AI planning.",
        "check_python_syntax": "Gate Python source changes.",
        "check_validation_report_contract": "Gate report quality before evidence bundling.",
        "run_gpu_planner_json_contract_smoke": "Validate planner JSON contract without providers.",
        "build_code_interpreter_report": "Build static analysis/refactor evidence.",
        "runtime_sqlite_memory": "Read memory status/search through broker-controlled actions.",
    }
    return mapping.get(
        tool_name,
        "Use through the runtime tool broker when a report-only request requires it.",
    )

def default_tool_requests() -> list[dict[str, Any]]:
    return [
        {
            "id": f"request_{name}",
            "tool": name,
            "reason": recommended_tool_use(name),
            "args": {},
            "status": "proposed_or_reported",
        }
        for name in sorted(TOOL_SPECS)
        if name
        in {
            "check_python_syntax",
            "check_validation_report_contract",
            "build_code_interpreter_report",
        }
    ]
