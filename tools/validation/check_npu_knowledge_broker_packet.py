#!/usr/bin/env python3
"""Validate NPU knowledge-broker/context-oracle packets.

The NPU knowledge broker is a context-preparation helper, not an advisory lane.
This validator enforces that packets remain report-only, provider-free,
patch-free and bounded.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from report_utils import resolve_output_path, write_json_report
except ImportError:
    from Tools.validation.report_utils import resolve_output_path, write_json_report  # type: ignore

EXPECTED_KIND = "npu_knowledge_broker_packet"
EXPECTED_ROLE = "knowledge_broker_context_oracle"
REPORT_KIND = "npu_knowledge_broker_packet_contract"

FORBIDDEN_PREFIXES = (
    ".git/",
    ".venv/",
    "venv/",
    "indexAI/agent_memory/",
    "output/patch_specs/",
    "Scripting/ready_to_jazz_wow_youtube_profiles_audio_sync/",
)
FORBIDDEN_EXACT = {"Scripting/shared/blender_compat.py"}
FORBIDDEN_FRAGMENTS = ("full_analysis", "analysis_full")


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_repo_path(repo_root: Path, raw: str) -> Path:
    path = Path(raw)
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def normalize_path(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/")


def read_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
    except OSError as exc:
        return None, str(exc)
    if not isinstance(data, dict):
        return None, f"expected JSON object, got {type(data).__name__}"
    return data, None


def path_errors(path: str) -> list[str]:
    normalized = normalize_path(path)
    errors: list[str] = []
    if not normalized:
        return ["path is empty"]
    if Path(normalized).is_absolute():
        errors.append(f"absolute path is not allowed: {normalized}")
    if normalized in FORBIDDEN_EXACT:
        errors.append(f"forbidden exact path: {normalized}")
    if any(normalized.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
        errors.append(f"forbidden path prefix: {normalized}")
    lower = normalized.lower()
    if any(fragment in lower for fragment in FORBIDDEN_FRAGMENTS) and lower.endswith(".json"):
        errors.append(f"forbidden full-analysis JSON path: {normalized}")
    return errors


def validate_candidate(item: Any, index: int) -> dict[str, Any]:
    label = f"candidate_context[{index}]"
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(item, dict):
        return {"label": label, "path": label, "ok": False, "errors": ["candidate must be an object"], "warnings": []}
    path = normalize_path(item.get("path"))
    errors.extend(path_errors(path))
    score = item.get("score")
    if not isinstance(score, int) or score < 0:
        errors.append("score must be a non-negative integer")
    if item.get("provider_execution_required") is not False:
        errors.append("provider_execution_required must be false")
    if item.get("source_write_allowed") is not False:
        errors.append("source_write_allowed must be false")
    if not isinstance(item.get("sources"), list) or not item.get("sources"):
        errors.append("sources must be a non-empty list")
    if not isinstance(item.get("reasons"), list) or not item.get("reasons"):
        errors.append("reasons must be a non-empty list")
    return {"label": label, "path": path, "ok": not errors, "errors": errors, "warnings": warnings}


def validate_packet(repo_root: Path, packet_path: Path, min_candidates: int, max_candidates: int) -> dict[str, Any]:
    rel_path = repo_relative(packet_path, repo_root)
    errors: list[str] = []
    warnings: list[str] = []
    data, parse_error = read_json_object(packet_path)
    if parse_error or data is None:
        return {
            "path": rel_path,
            "exists": packet_path.exists(),
            "json_ok": False,
            "ok": False,
            "errors": [parse_error or "unknown JSON parse error"],
            "warnings": warnings,
            "candidate_count": 0,
            "candidate_checks": [],
        }

    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if data.get("kind") != EXPECTED_KIND:
        errors.append(f"kind must be {EXPECTED_KIND}")
    if data.get("npu_role") != EXPECTED_ROLE:
        errors.append(f"npu_role must be {EXPECTED_ROLE}")
    if data.get("apply_mode") != "context_only":
        errors.append("apply_mode must be context_only")
    if data.get("provider_execution_performed") is not False:
        errors.append("provider_execution_performed must be false")
    if data.get("provider_execution_required") is not False:
        errors.append("provider_execution_required must be false")
    if data.get("source_writes_performed") is not False:
        errors.append("source_writes_performed must be false")
    if data.get("patch_application_performed") is not False:
        errors.append("patch_application_performed must be false")
    if data.get("primary_advisory_provider") != "ollama_gpu":
        errors.append("primary_advisory_provider must remain ollama_gpu")
    if data.get("npu_promoted_to_advisory") is not False:
        errors.append("npu_promoted_to_advisory must be false")
    if data.get("openvino_gpu_primary_lane") is not False:
        errors.append("openvino_gpu_primary_lane must be false")

    candidates = data.get("candidate_context")
    if not isinstance(candidates, list):
        errors.append("candidate_context must be a list")
        candidates = []
    candidate_count = len(candidates)
    declared_count = data.get("candidate_count")
    if not isinstance(declared_count, int):
        errors.append("candidate_count must be an integer")
    elif declared_count != candidate_count:
        errors.append("candidate_count must equal len(candidate_context)")
    if candidate_count < min_candidates:
        errors.append(f"candidate_count {candidate_count} below minimum {min_candidates}")
    if candidate_count > max_candidates:
        errors.append(f"candidate_count {candidate_count} above maximum {max_candidates}")

    checks = [validate_candidate(item, index) for index, item in enumerate(candidates)]
    seen: set[str] = set()
    for check in checks:
        path = str(check.get("path") or "")
        if path.lower() in seen:
            errors.append(f"duplicate candidate path: {path}")
        seen.add(path.lower())
        for error in check.get("errors", []):
            errors.append(f"{path}: {error}")
        for warning in check.get("warnings", []):
            warnings.append(f"{path}: {warning}")

    decision = data.get("decision")
    if not isinstance(decision, dict):
        errors.append("decision must be an object")
    else:
        required_false = (
            "provider_execution_seen",
            "source_writes_performed",
            "patch_application_performed",
            "npu_advisory_promotion_requested",
        )
        for key in required_false:
            if decision.get(key) is not False:
                errors.append(f"decision.{key} must be false")
        if decision.get("knowledge_broker_packet_built") is not True:
            errors.append("decision.knowledge_broker_packet_built must be true")
        if decision.get("requires_primary_advisory_review") is not True:
            errors.append("decision.requires_primary_advisory_review must be true")

    return {
        "path": rel_path,
        "exists": True,
        "json_ok": True,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "candidate_count": candidate_count,
        "candidate_checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--packet", required=True)
    parser.add_argument("--output")
    parser.add_argument("--min-candidates", type=int, default=3)
    parser.add_argument("--max-candidates", type=int, default=32)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    packet_path = resolve_repo_path(repo_root, args.packet)
    result = validate_packet(repo_root, packet_path, args.min_candidates, args.max_candidates)
    errors = [f"{result['path']}: {error}" for error in result.get("errors", [])]
    warnings = [f"{result['path']}: {warning}" for warning in result.get("warnings", [])]
    report = {
        "schema_version": 1,
        "kind": REPORT_KIND,
        "repo_root": repo_root.as_posix(),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "results": [result],
    }
    output = resolve_output_path(repo_root, args.output) if args.output else None
    print(write_json_report(report, output), end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
