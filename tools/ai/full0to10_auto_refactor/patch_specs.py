"""Patch-spec generation for auto-refactor candidates."""
from __future__ import annotations

from typing import Any

from .constants import MAX_PATCH_SPECS


def proposed_action(kind: str, path: str) -> str:
    if kind == "markdown_split":
        return f"Split {path} into a directory README.md plus numbered child docs."
    if kind == "code_split_candidate":
        return f"Inspect {path} for helper/module extraction; do not rewrite automatically."
    if kind == "safe_cleanup_trailing_whitespace":
        return f"Remove trailing whitespace from {path} after diff review."
    if kind == "safe_cleanup_final_newline":
        return f"Append final newline to {path} after diff review."
    if kind == "npu_gpu0_integration_contract":
        return f"Add explicit NPU/OpenVINO GPU.0 contract notes or diagnostics to {path}."
    if kind == "npu_sampled_auditor_contract":
        return f"Mark NPU behavior in {path} as sampled-auditor unless intentionally promoted."
    if kind == "gpu_telemetry_visibility":
        return f"Expose GPU optimization telemetry/capability output from {path}."
    return f"Review {path}."


def patch_spec_for_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    kind = str(candidate["kind"])
    path = str(candidate["path"])
    return {
        "kind": "full0to10_auto_refactor_patch_spec",
        "candidate_kind": kind,
        "target_path": path,
        "apply_automatically": False,
        "requires_human_review": True,
        "destructive": False,
        "provider_required": False,
        "proposed_action": proposed_action(kind, path),
        "reason": candidate["reason"],
    }


def build_patch_specs(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [patch_spec_for_candidate(candidate) for candidate in candidates[:MAX_PATCH_SPECS]]
