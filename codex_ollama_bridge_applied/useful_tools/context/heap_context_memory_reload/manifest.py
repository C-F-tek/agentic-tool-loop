"""Manifest construction for heap startup reload."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ia_carmine._shared.file_backed_transport import artifact_ref
from ia_carmine.context.heap_context_memory_reload.common import read_json, repo_rel, sha256_text


def artifact_json(repo_root: Path, artifacts: dict[str, str], key: str) -> dict[str, Any]:
    value = str(artifacts.get(key) or "").strip()
    if not value:
        return {}
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return read_json(path)


def as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def requirement_status(
    commands: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str], list[str]]:
    required = [item for item in commands if item.get("required")]
    optional = [item for item in commands if not item.get("required")]
    blocking = [str(item.get("requirement")) for item in required if not item.get("effective_passed")]
    degraded = [str(item.get("requirement")) for item in commands if item.get("degraded")]
    optional_failed = [
        str(item.get("requirement")) for item in optional if not item.get("effective_passed")
    ]
    return required, optional, blocking, degraded, optional_failed


def append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def missing_internal_runtime_surfaces(contract: dict[str, bool]) -> list[str]:
    return [name for name, loaded in contract.items() if not loaded]


def build_manifest(
    *,
    stamp: str,
    repo_root: Path,
    project_python: str,
    request_text: str,
    context_files: list[str],
    artifacts: dict[str, str],
    commands: list[dict[str, Any]],
    warnings: list[str],
    task_file: Path,
    context_delta: dict[str, Any],
    context_pack_result: dict[str, Any],
    strict_ai_context_pack: bool,
    strict_startup_reload: bool,
    startup_effective_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_file = str(artifacts.get("startup_request_file") or "").strip()
    request_ref = (
        artifact_ref(
            request_file,
            repo_root,
            kind="operator_request",
            ref_id="startup_request",
            producer="heap_context_memory_reload",
        )
        if request_file
        else {}
    )
    required, optional, blocking, degraded, optional_failed = requirement_status(commands)
    stale_static_context_demoted = "startup_unified_context_pack" in blocking
    if stale_static_context_demoted:
        blocking = [item for item in blocking if item != "startup_unified_context_pack"]
        append_unique(degraded, "startup_unified_context_pack")
        warnings = [
            *warnings,
            (
                "stale_static_context_reference_demoted:startup_unified_context_pack;"
                " hard blockers are mandatory internal runtime surfaces"
            ),
        ]
    rag_pack = artifact_json(repo_root, artifacts, "rag_context_pack_json")
    rag_ingest = artifact_json(repo_root, artifacts, "rag_repo_ingest_json")
    unified_pack = artifact_json(repo_root, artifacts, "startup_context_pack_json")
    gpu1_dynamic_context_pack = artifact_json(repo_root, artifacts, "gpu1_dynamic_context_pack_json")
    startup_scan = artifact_json(repo_root, artifacts, "startup_repo_scan_index_json")
    rag_index_ready = rag_ingest.get("rag_index_ready") is True
    rag_repo_ingest_passed = rag_ingest.get("passed") is True
    missing_embedding_count_after = as_int(rag_ingest.get("missing_embedding_count_after"))
    rag_index_action = str(rag_ingest.get("action") or "")
    ollama_embedding_performed = rag_ingest.get("ollama_embedding_performed") is True
    rag_resource_lane = str(rag_ingest.get("resource_lane") or "")
    providers_not_started_reason = str(rag_ingest.get("providers_not_started_reason") or "")
    rag_pack_loaded = bool(
        rag_pack.get("passed") is True and as_int(rag_pack.get("retrieved_count")) > 0
    )
    unified_pack_loaded = bool(unified_pack.get("passed") is True)
    gpu1_dynamic_context_pack_loaded = bool(
        gpu1_dynamic_context_pack.get("passed") is True
        and gpu1_dynamic_context_pack.get("active_context_pack") is True
    )
    gpu1_dynamic_context_pack_api_ready = bool(
        gpu1_dynamic_context_pack.get("api_native_tool_contract_ready") is True
    )
    ai_context_pack_loaded = bool(
        artifacts.get("ai_context_pack_json")
        and context_pack_result.get("effective_passed") is True
        and context_pack_result.get("artifact_contract_passed") is True
    )
    internal_runtime_surfaces = {
        "tool_catalog": bool(artifacts.get("tool_catalog_json")),
        "shared_memory": bool(artifacts.get("shared_memory_json")),
        "operational_memory_status": bool(artifacts.get("operational_memory_status_json")),
        "operational_memory_search": bool(artifacts.get("operational_memory_search_json")),
        "operational_memory_write": bool(artifacts.get("operational_memory_write_json")),
        "shared_context_chunks": bool(artifacts.get("shared_context_json")),
        "semantic_code_chunks": bool(artifacts.get("semantic_code_chunks_json")),
        "semantic_evidence_chunks": bool(artifacts.get("semantic_evidence_chunks_json")),
        "ai_context_pack": ai_context_pack_loaded,
        "rag_repo_ingest": rag_repo_ingest_passed,
        "rag_index_ready": rag_index_ready,
        "rag_context_pack": bool(rag_pack_loaded and rag_index_ready),
        "gpu1_dynamic_context_pack": gpu1_dynamic_context_pack_loaded,
        "gpu1_dynamic_context_pack_api_ready": gpu1_dynamic_context_pack_api_ready,
        "startup_repo_scan_index": bool(startup_scan),
        "runtime_raw_context": as_int(artifacts.get("startup_context_raw_file_count")) > 0,
    }
    if not rag_repo_ingest_passed:
        append_unique(blocking, "rag_repo_ingest")
    if not rag_index_ready:
        append_unique(blocking, "rag_index_ready")
    if not rag_pack_loaded or not rag_index_ready:
        append_unique(blocking, "rag_context_pack")
    if not gpu1_dynamic_context_pack_loaded:
        append_unique(blocking, "gpu1_dynamic_context_pack")
    if not gpu1_dynamic_context_pack_api_ready:
        append_unique(blocking, "gpu1_dynamic_context_pack_api_ready")
    for missing in missing_internal_runtime_surfaces(internal_runtime_surfaces):
        append_unique(blocking, f"internal_runtime_surface_missing:{missing}")
    hard_context_blockers = [
        item
        for item in (
            "rag_repo_ingest",
            "rag_index_ready",
            "rag_context_pack",
            "gpu1_dynamic_context_pack",
            "gpu1_dynamic_context_pack_api_ready",
            *[
                f"internal_runtime_surface_missing:{name}"
                for name in missing_internal_runtime_surfaces(internal_runtime_surfaces)
            ],
        )
        if item in blocking
    ]
    startup_reload_degraded = bool(degraded or optional_failed)
    required_passed = not blocking
    optional_passed = all(bool(item.get("effective_passed")) for item in optional)
    input_ready_before_heap = required_passed and bool(context_files)
    strict_startup = True
    passed = bool(input_ready_before_heap and not startup_reload_degraded)
    return {
        "schema_version": 1,
        "kind": "heap_context_memory_reload_manifest",
        "stamp": stamp,
        "repo_root": repo_root.as_posix(),
        "project_python": project_python,
        "request_file": request_file,
        "request_ref": request_ref,
        "request_chars": len(request_text),
        "request_sha256": sha256_text(request_text),
        "context_delta": context_delta,
        "startup_repo_scan_index": {
            "path": artifacts.get("startup_repo_scan_index_json", ""),
            "file_count": startup_scan.get("file_count", 0),
            "changed_file_count": startup_scan.get("changed_file_count", 0),
            "unchanged_ref_only_count": startup_scan.get("unchanged_ref_only_count", 0),
            "deleted_file_count": startup_scan.get("deleted_file_count", 0),
            "discovery_mode": startup_scan.get("discovery_mode", ""),
        },
        "context_reload_mode": context_delta.get("reload_mode", ""),
        "changed_context_file_count": context_delta.get("changed_context_file_count", 0),
        "unchanged_context_file_count": context_delta.get("unchanged_context_file_count", 0),
        "passed": passed,
        "input_ready_before_heap": input_ready_before_heap,
        "load_context_into_heap": True,
        "startup_reload_degraded": startup_reload_degraded,
        "rag_index_ready": rag_index_ready,
        "rag_repo_ingest_passed": rag_repo_ingest_passed,
        "rag_index_action": rag_index_action,
        "rag_missing_embedding_count_after": missing_embedding_count_after,
        "rag_resource_lane": rag_resource_lane,
        "ollama_embedding_performed": ollama_embedding_performed,
        "providers_not_started_reason": providers_not_started_reason,
        "strict_startup_reload": strict_startup,
        "required_reload_passed": required_passed,
        "optional_reload_passed": optional_passed,
        "blocking_requirements": blocking,
        "hard_context_blockers": hard_context_blockers,
        "degraded_requirements": degraded,
        "optional_failed_requirements": optional_failed,
        "stale_static_context_block_demoted": stale_static_context_demoted,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "context_file_count": len(context_files),
        "context_files": context_files,
        "startup_effective_config": startup_effective_config or {},
        "artifacts": artifacts,
        "tool_executions": commands,
        "startup_warnings": warnings,
        "required_requirements": [item["requirement"] for item in required],
        "optional_requirements": [item["requirement"] for item in optional],
        "heap_task_file": artifacts["heap_task_file"],
        "contract": {
            "input_ready_before_heap": input_ready_before_heap,
            "load_context_into_heap": True,
            "tool_catalog_loaded": bool(artifacts.get("tool_catalog_json")),
            "shared_memory_loaded": bool(artifacts.get("shared_memory_json")),
            "operational_memory_loaded": bool(artifacts.get("operational_memory_status_json")),
            "operational_memory_write_recorded": bool(
                artifacts.get("operational_memory_write_json")
            ),
            "repo_docs_loaded": bool(artifacts.get("repo_docs_map_json")),
            "semantic_code_chunks_loaded": bool(artifacts.get("semantic_code_chunks_json")),
            "ai_context_pack_loaded": ai_context_pack_loaded,
            "rag_index_ready": rag_index_ready,
            "rag_repo_ingest_passed": rag_repo_ingest_passed,
            "rag_missing_embedding_count_after": missing_embedding_count_after,
            "rag_index_action": rag_index_action,
            "rag_resource_lane": rag_resource_lane,
            "ollama_embedding_performed": ollama_embedding_performed,
            "providers_not_started_reason": providers_not_started_reason,
            "rag_context_pack_loaded": bool(rag_pack_loaded and rag_index_ready),
            "startup_unified_context_pack_loaded": unified_pack_loaded,
            "startup_unified_context_pack_blocking": False,
            "stale_static_context_block_demoted": stale_static_context_demoted,
            "gpu1_dynamic_context_pack_loaded": gpu1_dynamic_context_pack_loaded,
            "gpu1_dynamic_context_pack_required": True,
            "gpu1_dynamic_context_pack_api_ready": gpu1_dynamic_context_pack_api_ready,
            "gpu1_dynamic_context_pack_path": artifacts.get("gpu1_dynamic_context_pack_json", ""),
            "rag_context_pack_required": True,
            "hard_context_blockers": hard_context_blockers,
            "startup_unified_context_pack_required": True,
            "semantic_evidence_chunks_loaded": bool(artifacts.get("semantic_evidence_chunks_json")),
            "internal_runtime_surfaces_required": True,
            "internal_runtime_surfaces": internal_runtime_surfaces,
            "missing_internal_runtime_surfaces": missing_internal_runtime_surfaces(
                internal_runtime_surfaces
            ),
            "heap_task_file_written": task_file.exists(),
            "advisory_context_pack_non_blocking": False,
            "final_composer_required": True,
            "memory_reload_uses_delta": bool(context_delta),
            "startup_repo_scan_index_loaded": bool(startup_scan),
            "startup_tool_catalog_cache_hit": artifacts.get("tool_catalog_cache_hit", ""),
            "parallel_provider_input_lanes": artifacts.get("startup_parallel_provider_input_lanes", ""),
            "startup_effective_config": startup_effective_config or {},
            "unchanged_context_refs_not_reloaded_as_previews": (
                context_delta.get("unchanged_preview_policy")
                == "omit_unchanged_bounded_previews_use_file_refs"
            ),
        },
    }


def build_print_payload(manifest: dict[str, Any], repo_root: Path, manifest_path: Path, manifest_md: Path) -> dict[str, Any]:
    return {
        "schema_version": manifest["schema_version"],
        "kind": manifest["kind"],
        "stamp": manifest["stamp"],
        "passed": manifest["passed"],
        "input_ready_before_heap": manifest["input_ready_before_heap"],
        "startup_reload_degraded": manifest["startup_reload_degraded"],
        "rag_index_ready": manifest.get("rag_index_ready", False),
        "rag_repo_ingest_passed": manifest.get("rag_repo_ingest_passed", False),
        "rag_missing_embedding_count_after": manifest.get("rag_missing_embedding_count_after", 0),
        "rag_index_action": manifest.get("rag_index_action", ""),
        "rag_resource_lane": manifest.get("rag_resource_lane", ""),
        "ollama_embedding_performed": manifest.get("ollama_embedding_performed", False),
        "providers_not_started_reason": manifest.get("providers_not_started_reason", ""),
        "gpu1_dynamic_context_pack_loaded": manifest.get("contract", {}).get(
            "gpu1_dynamic_context_pack_loaded", False
        ),
        "gpu1_dynamic_context_pack_api_ready": manifest.get("contract", {}).get(
            "gpu1_dynamic_context_pack_api_ready", False
        ),
        "required_reload_passed": manifest["required_reload_passed"],
        "optional_reload_passed": manifest["optional_reload_passed"],
        "request_file": manifest.get("request_file", ""),
        "request_ref": manifest.get("request_ref", {}),
        "request_chars": manifest.get("request_chars", 0),
        "request_sha256": manifest.get("request_sha256", ""),
        "context_file_count": manifest.get("context_file_count", 0),
        "context_reload_mode": manifest.get("context_reload_mode", ""),
        "startup_repo_scan_file_count": manifest.get("startup_repo_scan_index", {}).get("file_count", 0),
        "startup_repo_scan_changed_file_count": manifest.get("startup_repo_scan_index", {}).get("changed_file_count", 0),
        "changed_context_file_count": manifest.get("changed_context_file_count", 0),
        "unchanged_context_file_count": manifest.get("unchanged_context_file_count", 0),
        "artifact_count": len(manifest.get("artifacts", {})),
        "tool_execution_count": len(manifest.get("tool_executions", [])),
        "blocking_requirements": manifest.get("blocking_requirements", []),
        "hard_context_blockers": manifest.get("hard_context_blockers", []),
        "degraded_requirements": manifest.get("degraded_requirements", []),
        "optional_failed_requirements": manifest.get("optional_failed_requirements", []),
        "stale_static_context_block_demoted": manifest.get(
            "stale_static_context_block_demoted", False
        ),
        "startup_effective_config": manifest.get("startup_effective_config", {}),
        "manifest": repo_rel(repo_root, manifest_path),
        "markdown": repo_rel(repo_root, manifest_md),
        "heap_task_file": manifest.get("heap_task_file", ""),
    }
