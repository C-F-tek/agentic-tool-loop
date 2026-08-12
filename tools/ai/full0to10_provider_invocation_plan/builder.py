"""Build provider invocation dry-run plan artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from full0to10_provider_governor.builder import build_provider_governor

from .constants import (
    DRY_RUN_STEPS_JSON,
    PLAN_JSON,
    PLAN_MD,
    PRIMARY_PROVIDER_LANE,
    SAFETY_FLAGS,
    TELEMETRY_CONTRACT_JSON,
    WORKLOAD_CONTRACT_JSON,
)
from .dry_run import build_dry_run_steps
from .npu_hooks import build_npu_audit_hooks
from .paths import ensure_dir, repo_relative
from .readiness import build_invocation_readiness
from .render import render_plan_markdown
from .telemetry_contract import build_expected_telemetry_contract
from .workload_contract import build_workload_report_contract


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_provider_invocation_plan(
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
    governor = build_provider_governor(
        repo_root,
        output_dir / "provider_governor",
        request,
        operator_intent,
        allow_provider_generation,
        no_external_probes,
        timeout_seconds,
    )
    workload_contract = build_workload_report_contract(governor)
    telemetry_contract = build_expected_telemetry_contract(governor)
    npu_hooks = build_npu_audit_hooks(governor)
    dry_run_steps = build_dry_run_steps(governor)
    readiness = build_invocation_readiness(governor, workload_contract, telemetry_contract, dry_run_steps)

    plan: dict[str, Any] = {
        "kind": "full0to10_provider_invocation_plan",
        "passed": readiness["passed"],
        "request": request,
        "provider_lane": PRIMARY_PROVIDER_LANE,
        "permit_decision": governor["run_permit"]["decision"],
        "permit_allowed": governor["run_permit"]["permit_allowed"],
        "generation_executes_now": False,
        "governor": governor,
        "workload_report_contract": workload_contract,
        "expected_telemetry_contract": telemetry_contract,
        "npu_audit_hooks": npu_hooks,
        "dry_run_steps": dry_run_steps,
        "readiness": readiness,
        "errors": readiness["blockers"],
        "warnings": readiness["warnings"],
    }
    plan.update(SAFETY_FLAGS)

    plan_path = output_dir / PLAN_JSON
    workload_path = output_dir / WORKLOAD_CONTRACT_JSON
    telemetry_path = output_dir / TELEMETRY_CONTRACT_JSON
    steps_path = output_dir / DRY_RUN_STEPS_JSON
    md_path = output_dir / PLAN_MD
    write_json(plan_path, plan)
    write_json(workload_path, workload_contract)
    write_json(telemetry_path, telemetry_contract)
    write_json(steps_path, dry_run_steps)
    md_path.write_text(render_plan_markdown(plan), encoding="utf-8")
    plan["outputs"] = {
        "plan": repo_relative(plan_path, repo_root),
        "workload_contract": repo_relative(workload_path, repo_root),
        "telemetry_contract": repo_relative(telemetry_path, repo_root),
        "dry_run_steps": repo_relative(steps_path, repo_root),
        "markdown": repo_relative(md_path, repo_root),
    }
    return plan
