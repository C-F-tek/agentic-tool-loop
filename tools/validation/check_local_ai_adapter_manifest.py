#!/usr/bin/env python3
"""Validate local AI task pipeline adapter manifests.

The adapter manifest is produced by Tools/workflow/run_local_ai_task_via_pipeline.ps1
and records which enrichment artifacts were requested/generated, which providers
were requested, and whether patch application occurred.

This validator is report-only. It reads one or more manifest JSON files and
writes an optional validation report. It does not execute providers, apply
patches, or inspect ignored runtime payloads beyond the manifest paths.
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

EXPECTED_KIND = "local_ai_task_pipeline_adapter_manifest"
REPORT_KIND = "local_ai_adapter_manifest_contract"

REQUIRED_ROOT_FIELDS = (
    "schema_version",
    "kind",
    "prompt_file",
    "task_file",
    "pipeline_output_dir",
    "profile",
    "basename",
    "proposal_basename",
    "context_files",
    "context_file_count",
    "enrichment_requested",
    "enrichment_outputs",
    "provider_execution_requested",
    "patch_application_performed",
    "provider_execution_performed_by_adapter",
    "outputs",
)

REQUIRED_ENRICHMENT_REQUESTED_FIELDS = (
    "build_semantic_chunks",
    "select_semantic_chunks",
    "build_context_pack",
    "build_agent_state_packet",
    "memory_db",
    "save_inputs_to_memory_db",
)

ALLOWED_INDEXAI_ARTIFACTS = {
    "indexAI/code_chunks/semantic_code_chunks.json",
    "indexAI/code_chunks/semantic_code_chunks_manifest.json",
}

FORBIDDEN_PATH_PREFIXES = (
    ".git/",
    ".venv/",
    "venv/",
    "indexAI/agent_memory/",
    "output/patch_specs/",
    "Scripting/ready_to_jazz_wow_youtube_profiles_audio_sync/",
)
FORBIDDEN_PATH_EXACT = {"Scripting/shared/blender_compat.py"}
FORBIDDEN_PATH_FRAGMENTS = ("full_analysis", "analysis_full")


def split_manifest_values(items: list[str]) -> list[str]:
    values: list[str] = []
    for item in items:
        for part in str(item).split(","):
            normalized = part.strip().strip("'\"")
            if normalized:
                values.append(normalized)
    return values


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


def path_policy_errors(path: str, *, allow_output: bool = True, allow_index_artifacts: bool = True) -> list[str]:
    normalized = normalize_path(path)
    errors: list[str] = []
    if not normalized:
        return ["path is empty"]
    if Path(normalized).is_absolute():
        errors.append(f"absolute paths are not allowed: {normalized}")
    if normalized in FORBIDDEN_PATH_EXACT:
        errors.append(f"forbidden exact path: {normalized}")
    if any(normalized.startswith(prefix) for prefix in FORBIDDEN_PATH_PREFIXES):
        errors.append(f"forbidden path prefix: {normalized}")
    if normalized.startswith("output/") and not allow_output:
        errors.append(f"output path is not allowed here: {normalized}")
    if normalized.startswith("indexAI/") and not (allow_index_artifacts and normalized in ALLOWED_INDEXAI_ARTIFACTS):
        errors.append(f"indexAI path is not allowed here: {normalized}")
    lower = normalized.lower()
    if any(fragment in lower for fragment in FORBIDDEN_PATH_FRAGMENTS) and lower.endswith(".json"):
        errors.append(f"forbidden full-analysis JSON path: {normalized}")
    return errors


def bool_field(data: dict[str, Any], key: str) -> bool:
    return data.get(key) is True


def require_path_if_requested(
    errors: list[str],
    outputs: dict[str, Any],
    field: str,
    reason: str,
    *,
    allow_output: bool = True,
    allow_index_artifacts: bool = True,
) -> None:
    value = normalize_path(outputs.get(field))
    if not value:
        errors.append(f"{field} is required when {reason}")
        return
    for error in path_policy_errors(value, allow_output=allow_output, allow_index_artifacts=allow_index_artifacts):
        errors.append(f"{field}: {error}")


def validate_manifest(path: Path, repo_root: Path) -> dict[str, Any]:
    rel_path = repo_relative(path, repo_root)
    errors: list[str] = []
    warnings: list[str] = []
    data, parse_error = read_json_object(path)
    if parse_error or data is None:
        return {
            "path": rel_path,
            "exists": path.exists(),
            "json_ok": False,
            "ok": False,
            "errors": [parse_error or "unknown JSON parse error"],
            "warnings": warnings,
        }

    missing = [field for field in REQUIRED_ROOT_FIELDS if field not in data]
    if missing:
        errors.append(f"missing required root fields: {', '.join(missing)}")
    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if data.get("kind") != EXPECTED_KIND:
        errors.append(f"kind must be {EXPECTED_KIND}")
    if data.get("patch_application_performed") is not False:
        errors.append("patch_application_performed must be false")
    if data.get("provider_execution_performed_by_adapter") is not False:
        errors.append("provider_execution_performed_by_adapter must be false")

    context_files = data.get("context_files")
    if not isinstance(context_files, list) or not all(isinstance(item, str) and item for item in context_files):
        errors.append("context_files must be a non-empty list of strings")
        context_files = []
    declared_count = data.get("context_file_count")
    if not isinstance(declared_count, int):
        errors.append("context_file_count must be an integer")
    elif declared_count != len(context_files):
        errors.append("context_file_count must equal len(context_files)")
    seen: set[str] = set()
    for context in context_files:
        normalized = normalize_path(context)
        key = normalized.lower()
        if key in seen:
            errors.append(f"duplicate context file: {normalized}")
        seen.add(key)
        for error in path_policy_errors(normalized):
            errors.append(f"context_files: {error}")

    enrichment_requested = data.get("enrichment_requested")
    if not isinstance(enrichment_requested, dict):
        errors.append("enrichment_requested must be an object")
        enrichment_requested = {}
    else:
        missing_req = [field for field in REQUIRED_ENRICHMENT_REQUESTED_FIELDS if field not in enrichment_requested]
        if missing_req:
            errors.append(f"enrichment_requested missing fields: {', '.join(missing_req)}")

    enrichment_outputs = data.get("enrichment_outputs")
    if not isinstance(enrichment_outputs, dict):
        errors.append("enrichment_outputs must be an object")
        enrichment_outputs = {}
    outputs = data.get("outputs")
    if not isinstance(outputs, dict):
        errors.append("outputs must be an object")
        outputs = {}

    if bool_field(enrichment_requested, "build_semantic_chunks"):
        require_path_if_requested(errors, enrichment_outputs, "semantic_chunks_manifest", "build_semantic_chunks is true", allow_output=False)
        require_path_if_requested(errors, enrichment_outputs, "semantic_chunks_json", "build_semantic_chunks is true", allow_output=False)

    if bool_field(enrichment_requested, "select_semantic_chunks"):
        require_path_if_requested(errors, enrichment_outputs, "selected_chunks_json", "select_semantic_chunks is true")
        require_path_if_requested(errors, enrichment_outputs, "selected_chunks_markdown", "select_semantic_chunks is true")

    if bool_field(enrichment_requested, "build_selected_chunks_evidence"):
        if not bool_field(enrichment_requested, "select_semantic_chunks"):
            errors.append("build_selected_chunks_evidence requires select_semantic_chunks")
        require_path_if_requested(errors, enrichment_outputs, "selected_chunks_validation", "build_selected_chunks_evidence is true")
        require_path_if_requested(errors, enrichment_outputs, "selected_chunks_evidence_json", "build_selected_chunks_evidence is true", allow_output=False, allow_index_artifacts=False)
        require_path_if_requested(errors, enrichment_outputs, "selected_chunks_evidence_markdown", "build_selected_chunks_evidence is true", allow_output=False, allow_index_artifacts=False)

    if bool_field(enrichment_requested, "build_context_pack"):
        require_path_if_requested(errors, enrichment_outputs, "context_pack_json", "build_context_pack is true")
        require_path_if_requested(errors, enrichment_outputs, "context_pack_markdown", "build_context_pack is true")
        require_path_if_requested(errors, enrichment_outputs, "context_pack_evidence_json", "build_context_pack is true", allow_output=False, allow_index_artifacts=False)

    if bool_field(enrichment_requested, "build_agent_state_packet"):
        require_path_if_requested(errors, enrichment_outputs, "agent_state_json", "build_agent_state_packet is true")
        require_path_if_requested(errors, enrichment_outputs, "agent_state_markdown", "build_agent_state_packet is true")
        memory_db = normalize_path(enrichment_requested.get("memory_db") or enrichment_outputs.get("memory_db"))
        if not memory_db:
            errors.append("memory_db must be recorded when build_agent_state_packet is true")
        elif not memory_db.endswith(".sqlite"):
            warnings.append("memory_db does not end with .sqlite")

    if data.get("provider_execution_requested") is True:
        for flag in ("run_ollama_probe", "run_npu_probe", "run_npu_decode_smoke", "multistep_provider_workflow_requested"):
            if flag in data and data.get(flag) is True:
                break
        else:
            warnings.append("provider_execution_requested is true but no explicit provider/multistep flag is true")

    for output_key in (
        "packet_json",
        "packet_markdown",
        "proposals_json",
        "proposals_markdown",
        "proposal_validation",
    ):
        value = normalize_path(outputs.get(output_key))
        if not value:
            errors.append(f"outputs.{output_key} is required")
        else:
            for error in path_policy_errors(value):
                errors.append(f"outputs.{output_key}: {error}")

    for output_key in ("telemetry_json", "telemetry_markdown"):
        value = normalize_path(outputs.get(output_key))
        if value:
            for error in path_policy_errors(value):
                errors.append(f"outputs.{output_key}: {error}")

    return {
        "path": rel_path,
        "exists": True,
        "json_ok": True,
        "kind": data.get("kind"),
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "context_file_count": len(context_files),
        "provider_execution_requested": data.get("provider_execution_requested"),
        "provider_execution_performed_by_adapter": data.get("provider_execution_performed_by_adapter"),
        "patch_application_performed": data.get("patch_application_performed"),
        "build_evidence_requested": data.get("build_evidence_requested"),
        "telemetry_outputs_declared": bool(outputs.get("telemetry_json") or outputs.get("telemetry_markdown")),
        "enrichment_requested_keys": sorted(enrichment_requested.keys()),
        "enrichment_output_keys": sorted(enrichment_outputs.keys()),
    }


def validate_manifests(repo_root: Path, manifests: list[Path]) -> dict[str, Any]:
    results = [validate_manifest(path, repo_root) for path in manifests]
    errors = [f"{item['path']}: {error}" for item in results for error in item.get("errors", [])]
    warnings = [f"{item['path']}: {warning}" for item in results for warning in item.get("warnings", [])]
    return {
        "schema_version": 1,
        "kind": REPORT_KIND,
        "repo_root": repo_root.as_posix(),
        "passed": not errors,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "blender_runtime_execution_performed": False,
        "ffmpeg_runtime_execution_performed": False,
        "errors": errors,
        "warnings": warnings,
        "manifest_count": len(results),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--manifest", action="append", default=[], help="Manifest path. Repeatable or comma-separated.")
    parser.add_argument("--output", help="Optional JSON validation report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    raw_paths = split_manifest_values(list(args.manifest or []))
    if not raw_paths:
        raw_paths = ["output/local_ai_runs/latest/pipeline/local_ai_task_pipeline_adapter_manifest.json"]
    manifests = [resolve_repo_path(repo_root, raw) for raw in raw_paths]
    report = validate_manifests(repo_root, manifests)
    output = resolve_output_path(repo_root, args.output) if args.output else None
    print(write_json_report(report, output), end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
