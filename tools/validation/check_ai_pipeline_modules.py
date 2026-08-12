#!/usr/bin/env python3
"""Smoke-check reusable AI pipeline modules without running heavy workloads.

This validator imports the modular AI artifact pipeline, builds representative
steps and reports, and verifies that the thin entrypoint can be imported.
It does not execute NPU, GPU, Blender, FFmpeg or long-running artifact jobs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def import_pipeline_modules(repo_root: Path) -> dict[str, Any]:
    """Import pipeline modules after ensuring the repository root is importable."""
    import sys

    root_text = str(repo_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)

    from Tools.ai.pipeline.artifact_contracts import planned_outputs, slugify
    from Tools.ai.pipeline.cli import build_parser
    from Tools.ai.pipeline.compat import pipeline_step, run_pipeline_step
    from Tools.ai.pipeline.models import PipelineLane, PipelineStep
    from Tools.ai.pipeline.orchestrator import run_parallel_steps, run_serial_steps
    from Tools.ai.pipeline.preflight import preflight
    from Tools.ai.pipeline.remediation import remediation_plan_from_requests, remedial_steps
    from Tools.ai.pipeline.schema_report import build_report, empty_failed_report
    from Tools.ai.pipeline.steps import build_parallel_steps, build_serial_steps, build_step_commands
    from Tools.ai.run_parallel_artifact_pipeline import main as entrypoint_main
    from Tools.validation.ai_pipeline_report_contracts import validate_ai_pipeline_report_payload

    return {
        "planned_outputs": planned_outputs,
        "slugify": slugify,
        "build_parser": build_parser,
        "pipeline_step": pipeline_step,
        "run_pipeline_step": run_pipeline_step,
        "PipelineLane": PipelineLane,
        "PipelineStep": PipelineStep,
        "run_parallel_steps": run_parallel_steps,
        "run_serial_steps": run_serial_steps,
        "preflight": preflight,
        "remediation_plan_from_requests": remediation_plan_from_requests,
        "remedial_steps": remedial_steps,
        "build_report": build_report,
        "empty_failed_report": empty_failed_report,
        "build_parallel_steps": build_parallel_steps,
        "build_serial_steps": build_serial_steps,
        "build_step_commands": build_step_commands,
        "entrypoint_main": entrypoint_main,
        "validate_ai_pipeline_report_payload": validate_ai_pipeline_report_payload,
    }


def make_args(repo_root: Path) -> SimpleNamespace:
    """Build a representative dry-run namespace without requiring input artifacts."""
    return SimpleNamespace(
        repo_root=str(repo_root),
        analysis_json=None,
        track_stem="Smoke Test Track",
        output_dir=str(repo_root / "output" / "ai_pipeline_smoke"),
        review_wave_entrypoints=True,
        build_chunks=False,
        build_music_summary=False,
        smart_context=True,
        smart_task="Smoke test task",
        smart_max_packet_chars=22000,
        smart_max_capsule_chars=3200,
        agent_state_packet=None,
        use_npu=False,
        npu_guardrail=True,
        npu_workers=4,
        guardrail_auto_remediate=True,
        guardrail_max_passes=2,
        gpu_command=None,
        validate=True,
        dry_run=True,
        write_dry_run_report=True,
        continue_on_error=False,
    )


def write_smoke_agent_state_packet(out: Path) -> Path:
    """Write a minimal local packet used only for report contract validation."""
    packet = out / "agent_state_packet_smoke.json"
    packet.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "objective": "AI pipeline module smoke validation",
                "selected_memory": [],
                "microtasks": [],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return packet


def check_agent_state_packet_contract(report: dict[str, Any], *, enabled: bool) -> list[str]:
    """Validate the additive agent_state_packet report contract."""
    errors: list[str] = []
    packet = report.get("agent_state_packet")
    if not isinstance(packet, dict):
        return ["report.agent_state_packet is missing or is not an object"]

    for field in ["enabled", "path", "exists", "source"]:
        if field not in packet:
            errors.append(f"report.agent_state_packet.{field} is missing")

    if packet.get("enabled") is not enabled:
        errors.append(f"report.agent_state_packet.enabled expected {enabled!r}, got {packet.get('enabled')!r}")

    if enabled:
        if packet.get("exists") is not True:
            errors.append("enabled agent_state_packet should exist in smoke contract")
        if packet.get("source") != "cli":
            errors.append("enabled agent_state_packet should have source='cli'")
        if not packet.get("repo_relative_path"):
            errors.append("enabled agent_state_packet should expose repo_relative_path")
    else:
        if packet.get("exists") is not False:
            errors.append("disabled agent_state_packet should have exists=false")
        if packet.get("source") != "disabled":
            errors.append("disabled agent_state_packet should have source='disabled'")

    return errors


def check_modules(repo_root: Path) -> dict[str, Any]:
    modules = import_pipeline_modules(repo_root)
    args = make_args(repo_root)
    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    parser = modules["build_parser"]()
    parsed = parser.parse_args(["--repo-root", str(repo_root), "--dry-run"])
    parsed_with_packet = parser.parse_args(
        ["--repo-root", str(repo_root), "--dry-run", "--agent-state-packet", "output/ai_pipeline_smoke/agent_state_packet_smoke.json"]
    )

    step = modules["pipeline_step"](
        "smoke_step",
        "CPU",
        "Smoke-check command runner integration.",
        ["output/ai_pipeline_smoke/smoke.json"],
        ["python", "--version"],
    )
    step_payload = step.to_dict()
    dry_result = modules["run_pipeline_step"](step, repo_root, True)

    commands = modules["build_step_commands"](repo_root, out, args)
    serial = modules["build_serial_steps"](commands, modules["slugify"](args.track_stem))
    parallel = modules["build_parallel_steps"](commands, out, args)
    pf = modules["preflight"](repo_root, out, args)
    plan = modules["remediation_plan_from_requests"](
        [
            {
                "suggested_stage": "smart_context_generation",
                "action_type": "rerun_stage",
                "auto_safe": True,
            }
        ]
    )
    remediation = modules["remedial_steps"](repo_root, out, args, plan["requests"], 1)
    smoke_schedule = {
        "serial_count": 1,
        "parallel_count": 0,
        "total_count": 1,
        "serial": ["smoke_step"],
        "parallel": [],
        "parallel_lanes": [],
    }
    report = modules["build_report"](
        repo_root,
        out,
        args,
        pf,
        [dry_result],
        {"enabled": False, "reason": "smoke", "passes": []},
        smoke_schedule,
    )
    failed_report = modules["empty_failed_report"](repo_root, out, True, {"passed": False, "errors": ["smoke"], "warnings": []})
    planned = modules["planned_outputs"](repo_root, out, args)

    smoke_packet = write_smoke_agent_state_packet(out)
    packet_args = make_args(repo_root)
    packet_args.agent_state_packet = str(smoke_packet)
    packet_pf = modules["preflight"](repo_root, out, packet_args)
    packet_report = modules["build_report"](
        repo_root,
        out,
        packet_args,
        packet_pf,
        [dry_result],
        {"enabled": False, "reason": "smoke", "passes": []},
        smoke_schedule,
    )
    report_contract = modules["validate_ai_pipeline_report_payload"](report, require_dry_run=True)
    packet_report_contract = modules["validate_ai_pipeline_report_payload"](packet_report, require_dry_run=True)
    failed_report_contract = modules["validate_ai_pipeline_report_payload"](failed_report, require_dry_run=True)

    checks = {
        "parser_type": type(parser).__name__,
        "parsed_dry_run": bool(parsed.dry_run),
        "parsed_agent_state_packet_default": parsed.agent_state_packet,
        "parsed_agent_state_packet_value": parsed_with_packet.agent_state_packet,
        "step_lane": step_payload["lane"],
        "dry_result_returncode": dry_result["returncode"],
        "dry_result_planned_only": dry_result["planned_only"],
        "command_count": len(commands),
        "serial_step_count": len(serial),
        "parallel_step_count": len(parallel),
        "preflight_passed": pf["passed"],
        "agent_state_packet_contract_disabled": report.get("agent_state_packet"),
        "agent_state_packet_contract_enabled": packet_report.get("agent_state_packet"),
        "agent_state_packet_preflight_enabled": packet_pf.get("agent_state_packet"),
        "remediation_request_count": plan["request_count"],
        "remediation_step_count": len(remediation),
        "report_schema_version": report["schema_version"],
        "failed_report_schema_version": failed_report["schema_version"],
        "report_contract_passed": report_contract["passed"],
        "packet_report_contract_passed": packet_report_contract["passed"],
        "failed_report_contract_passed": failed_report_contract["passed"],
        "failed_report_contract_warning_count": len(failed_report_contract["warnings"]),
        "planned_output_count": len(planned),
        "entrypoint_imported": callable(modules["entrypoint_main"]),
    }

    errors: list[str] = []
    if checks["step_lane"] != "CPU":
        errors.append("pipeline_step did not preserve CPU lane")
    if checks["dry_result_returncode"] != 0 or not checks["dry_result_planned_only"]:
        errors.append("run_pipeline_step dry-run did not produce a planned successful result")
    if checks["serial_step_count"] < 1:
        errors.append("serial step builder produced no steps for smoke configuration")
    if checks["report_schema_version"] != 6:
        errors.append("build_report did not produce schema version 6")
    if parsed.agent_state_packet is not None:
        errors.append("--agent-state-packet should default to None")
    if not parsed_with_packet.agent_state_packet:
        errors.append("--agent-state-packet parser did not preserve provided path")
    if not packet_pf["passed"]:
        errors.append("preflight failed for smoke agent_state_packet")
    errors.extend(check_agent_state_packet_contract(report, enabled=False))
    errors.extend(check_agent_state_packet_contract(packet_report, enabled=True))
    errors.extend(f"schema-v6 smoke report contract failed: {error}" for error in report_contract["errors"])
    errors.extend(f"schema-v6 packet report contract failed: {error}" for error in packet_report_contract["errors"])
    errors.extend(f"schema-v6 failed report contract failed: {error}" for error in failed_report_contract["errors"])
    if not checks["entrypoint_imported"]:
        errors.append("artifact pipeline entrypoint was not importable")

    return {
        "schema_version": 1,
        "kind": "ai_pipeline_modules",
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": [],
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = check_modules(repo_root)
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
