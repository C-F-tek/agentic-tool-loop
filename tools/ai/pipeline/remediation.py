"""Guardrail remediation helpers for the AI artifact pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifact_contracts import (
    EXPECTED_MUSIC_ARTIFACTS,
    EXPECTED_SMART_CONTEXT_ARTIFACTS,
    EXPECTED_WAVE_REVIEW_ARTIFACTS,
)
from .compat import pipeline_step, run_pipeline_step
from .guardrail_models import GuardrailPassResult, GuardrailPlan
from .models import PipelineStep
from .steps import build_step_commands


def load_json_if_exists(path: Path) -> Any | None:
    """Load JSON when present; return None on parse or I/O failure."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def guardrail_queue(out: Path) -> dict[str, Any]:
    """Load guardrail action queue or return an empty compatible queue."""
    payload = load_json_if_exists(out / "npu_guardrail_action_queue.json")
    if isinstance(payload, dict):
        return payload
    return {"schema_version": 1, "queue": []}


def auto_safe_requests(out: Path) -> list[dict[str, Any]]:
    """Return auto-safe remediation requests from the guardrail queue."""
    return [item.raw for item in auto_safe_plan(out).requests]


def auto_safe_plan(out: Path) -> GuardrailPlan:
    """Return a typed plan for auto-safe requests from the guardrail queue."""
    return GuardrailPlan.from_queue(guardrail_queue(out).get("queue") or [])


def normalize_guardrail_plan(plan: GuardrailPlan | list[Any] | tuple[Any, ...] | dict[str, Any]) -> GuardrailPlan:
    """Normalize typed or legacy remediation plan payloads.

    This keeps older callers and smoke validators compatible after the internal
    migration from raw dictionaries to GuardrailPlan.
    """
    if isinstance(plan, GuardrailPlan):
        return plan
    if isinstance(plan, dict):
        raw_requests = plan.get("requests") or []
        return GuardrailPlan.from_raw_requests(list(raw_requests) if isinstance(raw_requests, list) else [])
    if isinstance(plan, (list, tuple)):
        return GuardrailPlan.from_raw_requests(list(plan))
    return GuardrailPlan.from_raw_requests([])


def remediation_plan_from_requests(requests: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize guardrail remediation requests by stage and action type."""
    return GuardrailPlan.from_raw_requests(list(requests)).to_dict()


def remedial_steps(
    repo: Path,
    out: Path,
    args: Any,
    plan: GuardrailPlan | list[Any] | tuple[Any, ...] | dict[str, Any],
    pass_index: int,
) -> list[PipelineStep]:
    """Build PipelineStep remediation commands requested by the guardrail."""
    normalized_plan = normalize_guardrail_plan(plan)
    commands = build_step_commands(repo, out, args)
    stages = normalized_plan.stages
    todo: list[PipelineStep] = []

    if "wave_entrypoint_review" in stages and "review_wave_entrypoints" in commands:
        todo.append(
            pipeline_step(
                "remediate_review_wave_entrypoints",
                "CPU",
                "Repeat first-wave script review requested by guardrail.",
                EXPECTED_WAVE_REVIEW_ARTIFACTS,
                commands["review_wave_entrypoints"],
                pass_index,
            )
        )
    if "enrich_intermediates" in stages and "build_music_intermediates" in commands:
        todo.append(
            pipeline_step(
                "remediate_build_music_intermediates",
                "CPU",
                "Auto-safe enrichment pass requested by NPU guardrail.",
                EXPECTED_MUSIC_ARTIFACTS,
                commands["build_music_intermediates"],
                pass_index,
            )
        )
    if "compact_context_generation" in stages and "build_smart_ai_context" in commands:
        todo.append(
            pipeline_step(
                "remediate_build_smart_ai_context_compact",
                "CPU",
                "Auto-safe compact context rebuild requested by NPU guardrail.",
                EXPECTED_SMART_CONTEXT_ARTIFACTS,
                commands["build_smart_ai_context"],
                pass_index,
            )
        )
    if "smart_context_generation" in stages and "build_smart_ai_context" in commands:
        todo.append(
            pipeline_step(
                "remediate_build_smart_ai_context",
                "CPU",
                "Auto-safe smart context rebuild requested by NPU guardrail.",
                EXPECTED_SMART_CONTEXT_ARTIFACTS,
                commands["build_smart_ai_context"],
                pass_index,
            )
        )
    if "guardrail_second_pass" in stages and "npu_guardrail" in commands:
        todo.append(
            pipeline_step(
                "remediate_npu_guardrail_second_pass",
                "NPU",
                "Second guardrail pass requested by NPU guardrail.",
                [str(out / "npu_guardrail_report.json")],
                commands["npu_guardrail"],
                pass_index,
            )
        )

    if todo and "npu_guardrail" in commands and all(step.name != "remediate_npu_guardrail_second_pass" for step in todo):
        todo.append(
            pipeline_step(
                "remediate_npu_guardrail_verify",
                "NPU",
                "Verify artifact state after auto-safe remediation passes.",
                [str(out / "npu_guardrail_report.json")],
                commands["npu_guardrail"],
                pass_index,
            )
        )

    return todo


def execute_remediation_loop(repo: Path, out: Path, args: Any, results: list[dict[str, Any]]) -> dict[str, Any]:
    """Execute auto-safe remediation passes requested by the NPU guardrail."""
    if not args.guardrail_auto_remediate or not args.npu_guardrail:
        return {"enabled": False, "reason": "disabled", "passes": []}

    passes: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()
    for pass_index in range(1, max(1, args.guardrail_max_passes) + 1):
        plan = auto_safe_plan(out)
        signature = plan.signature()
        if not plan.requests:
            passes.append(GuardrailPassResult(pass_index, "no_auto_safe_requests", plan, []).to_dict())
            break
        if signature in seen_signatures:
            passes.append(GuardrailPassResult(pass_index, "repeated_plan_stopped", plan, []).to_dict())
            break
        seen_signatures.add(signature)

        todo = remedial_steps(repo, out, args, plan, pass_index)
        if not todo:
            passes.append(GuardrailPassResult(pass_index, "no_supported_remediation_commands", plan, []).to_dict())
            break

        step_results = []
        for step in todo:
            res = run_pipeline_step(step, repo, args.dry_run)
            step_results.append(res)
            results.append(res)
            if res["returncode"] and not args.continue_on_error:
                break
        passes.append(GuardrailPassResult(pass_index, "executed", plan, step_results).to_dict())
        if any(item["returncode"] for item in step_results) and not args.continue_on_error:
            break
    return {"enabled": True, "max_passes": args.guardrail_max_passes, "passes": passes}
