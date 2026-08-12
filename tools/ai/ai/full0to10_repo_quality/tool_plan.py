"""Tool plan for repo quality packet."""
from __future__ import annotations

from typing import Any

from .constants import SAFETY_FLAGS


def build_tool_plan(tool: str, request: str, inventory: dict[str, Any]) -> dict[str, Any]:
    counts = inventory.get("counts_by_kind", {})
    routes: list[str] = []
    if counts.get("markdown"):
        routes.append("markdown_chunk_memory")
    if counts.get("python"):
        routes.append("python_static_analysis")
    if counts.get("json"):
        routes.append("json_contract_probe")
    routes.append("quality_packet_render")

    plan = {
        "kind": "full0to10_repo_quality_tool_plan",
        "passed": True,
        "tool": tool,
        "request": request,
        "routes": routes,
        "execution_policy": {
            "read_files": True,
            "execute_python_inputs": False,
            "execute_external_tools": False,
            "provider_generation": False,
            "write_output_file_only_when_requested": True,
        },
    }
    plan.update(SAFETY_FLAGS)
    return plan
