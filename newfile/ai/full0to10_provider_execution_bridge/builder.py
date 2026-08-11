"""Build Full0To10 provider execution bridge artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from full0to10_provider_invocation_plan.builder import build_provider_invocation_plan

from .command_plan import build_command_plan
from .constants import BRIDGE_JSON, BRIDGE_MD, COMMAND_PLAN_JSON, GATE_JSON, SAFETY_FLAGS, TELEMETRY_JSON, WORKLOAD_PATHS_JSON
from .gate import build_real_run_gate
from .paths import ensure_dir, repo_relative
from .readiness import build_bridge_readiness
from .render import render_bridge_markdown
from .telemetry import build_bridge_telemetry, event
from .workload_paths import build_workload_output_paths


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_provider_execution_bridge(
    repo_root: Path,
    output_dir: Path,
    request: str,
    operator_intent: bool,
    allow_provider_generation: bool,
    no_external_probes: bool,
    timeout_seconds: int,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output_dir = ensure_dir(output_dir)
    invocation_plan = build_provider_invocation_plan(
        repo_root,
        output_dir / "provider_invocation_plan",
        request,
        operator_intent,
        allow_provider_generation,
        no_external_probes,
        timeout_seconds,
    )
    gate = build_real_run_gate(invocation_plan, operator_intent, allow_provider_generation)
    command_plan = build_command_plan(invocation_plan, gate)
    workload_paths = build_workload_output_paths(repo_root, output_dir)
    readiness = build_bridge_readiness(gate, command_plan, workload_paths)
    telemetry = build_bridge_telemetry([
        event("invocation_plan", invocation_plan["passed"], {"permit_decision": invocation_plan["permit_decision"]}),
        event("real_run_gate", gate["passed"], {"decision": gate["decision"]}),
        event("command_plan", command_plan["passed"], {"non_executing": command_plan["all_commands_are_non_executing"]}),
        event("workload_paths", workload_paths["passed"], {"workload_dir": workload_paths["workload_dir"]}),
    ])

    bridge: dict[str, Any] = {
        "kind": "full0to10_provider_execution_bridge",
        "passed": readiness["passed"] and telemetry["passed"],
        "request": request,
        "operator_intent": operator_intent,
        "allow_provider_generation_requested": allow_provider_generation,
        "provider_invocation_plan": invocation_plan,
        "real_run_gate": gate,
        "command_plan": command_plan,
        "workload_output_paths": workload_paths,
        "telemetry": telemetry,
        "readiness": readiness,
        "errors": readiness["blockers"],
        "warnings": readiness["warnings"],
    }
    bridge.update(SAFETY_FLAGS)

    bridge_path = output_dir / BRIDGE_JSON
    gate_path = output_dir / GATE_JSON
    command_path = output_dir / COMMAND_PLAN_JSON
    workload_path = output_dir / WORKLOAD_PATHS_JSON
    telemetry_path = output_dir / TELEMETRY_JSON
    md_path = output_dir / BRIDGE_MD
    write_json(bridge_path, bridge)
    write_json(gate_path, gate)
    write_json(command_path, command_plan)
    write_json(workload_path, workload_paths)
    write_json(telemetry_path, telemetry)
    md_path.write_text(render_bridge_markdown(bridge), encoding="utf-8")
    bridge["outputs"] = {
        "bridge": repo_relative(bridge_path, repo_root),
        "real_run_gate": repo_relative(gate_path, repo_root),
        "command_plan": repo_relative(command_path, repo_root),
        "workload_output_paths": repo_relative(workload_path, repo_root),
        "telemetry": repo_relative(telemetry_path, repo_root),
        "markdown": repo_relative(md_path, repo_root),
    }
    return bridge
