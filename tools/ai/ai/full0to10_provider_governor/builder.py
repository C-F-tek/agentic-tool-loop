"""Build Full0To10 provider governor artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from full0to10_accelerator_control.builder import build_accelerator_control
from full0to10_quality_gate.builder import build_quality_gate

from .budget import build_budget_plan
from .constants import GOVERNOR_JSON, GOVERNOR_MD, PERMIT_JSON, SAFETY_FLAGS, TELEMETRY_JSON
from .npu_audit import build_npu_audit_plan
from .paths import ensure_dir, repo_relative
from .permit import build_run_permit
from .policy import build_policy
from .render import render_governor_markdown
from .telemetry import build_telemetry, event


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_provider_governor(
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
    events: list[dict[str, Any]] = []

    accelerator = build_accelerator_control(repo_root, output_dir / "accelerator_control", request, no_external_probes, timeout_seconds)
    quality_gate = build_quality_gate(repo_root, None)
    budget = build_budget_plan(request)
    policy = build_policy(operator_intent, quality_gate, accelerator)
    npu_audit = build_npu_audit_plan(accelerator)
    run_permit = build_run_permit(policy, budget, npu_audit, allow_provider_generation)

    events.append(event("accelerator_control", accelerator["passed"], {"score": accelerator["readiness"]["score"]}, structural=True))
    events.append(event("quality_gate_observed", True, {"quality_gate_passed": bool(quality_gate.get("passed"))}))
    events.append(event("policy_decision", True, {"policy_passed": policy["passed"], "operator_intent": operator_intent}))
    events.append(event("run_permit_decision", True, {"permit_allowed": run_permit["permit_allowed"], "decision": run_permit["decision"]}))
    telemetry = build_telemetry(events)

    structural_ok = accelerator["passed"] and telemetry["passed"] and run_permit["passed"]
    governor: dict[str, Any] = {
        "kind": "full0to10_provider_governor",
        "passed": structural_ok,
        "valid_result": structural_ok,
        "request": request,
        "operator_intent": operator_intent,
        "allow_provider_generation_requested": allow_provider_generation,
        "decision": run_permit["decision"],
        "permit_allowed": run_permit["permit_allowed"],
        "deny_is_failure": False,
        "accelerator_control": accelerator,
        "quality_gate": quality_gate,
        "budget": budget,
        "policy": policy,
        "npu_audit": npu_audit,
        "run_permit": run_permit,
        "telemetry": telemetry,
        "errors": [] if structural_ok else ["structural governor artifact failure"],
        "warnings": run_permit.get("warnings", []),
    }
    governor.update(SAFETY_FLAGS)

    governor_path = output_dir / GOVERNOR_JSON
    permit_path = output_dir / PERMIT_JSON
    telemetry_path = output_dir / TELEMETRY_JSON
    markdown_path = output_dir / GOVERNOR_MD
    write_json(governor_path, governor)
    write_json(permit_path, run_permit)
    write_json(telemetry_path, telemetry)
    markdown_path.write_text(render_governor_markdown(governor), encoding="utf-8")
    governor["outputs"] = {
        "governor": repo_relative(governor_path, repo_root),
        "permit": repo_relative(permit_path, repo_root),
        "telemetry": repo_relative(telemetry_path, repo_root),
        "markdown": repo_relative(markdown_path, repo_root),
    }
    return governor
