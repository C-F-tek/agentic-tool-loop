"""Per-run GPU1 dynamic context pack for heap startup reload."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ia_carmine._shared.file_backed_transport import (
    artifact_ref,
    repo_rel,
    write_json_artifact,
    write_text_artifact,
    write_transport_manifest,
    validate_runtime_payload_manifest,
)
from ia_carmine._shared.provider_tool_schemas import (
    broker_tool_api_definitions,
    validate_broker_tool_api_definitions,
)
from ia_carmine._shared.provider_tool_loop import ollama_tool_call_tool_names
from ia_carmine.context.heap_context_memory_reload.common import write_json


LAB_TOOL_NAMES = {
    "agent_runtime_debug_lab",
    "run_heap_code_execution_matrix",
    "run_heap_virtual_dev_environment",
    "synthesize_patch_candidates",
    "runtime_file_refs",
}


def build_gpu1_dynamic_context_pack(
    *,
    repo_root: Path,
    output_dir: Path,
    stamp: str,
    artifacts: dict[str, str],
    commands: list[dict[str, Any]],
    request_text: str,
) -> tuple[dict[str, Any], Path, Path]:
    """Write the active GPU1 context artifact for the current run."""
    output_json = output_dir / "startup_gpu1_dynamic_context_pack.json"
    output_md = output_dir / "startup_gpu1_dynamic_context_pack.md"
    tool_definitions = broker_tool_api_definitions(ollama_tool_call_tool_names())
    tool_validation = validate_broker_tool_api_definitions(tool_definitions)
    selected_refs = _artifact_refs(repo_root, artifacts)
    capability_map = _capability_map(tool_definitions)
    runtime_file_refs = _runtime_file_refs(artifacts)
    payload_refs = _write_payload_manifest(
        repo_root=repo_root,
        output_dir=output_dir,
        stamp=stamp,
        request_text=request_text,
        artifact_refs=selected_refs,
    )
    errors: list[str] = []
    if not selected_refs:
        errors.append("gpu1_dynamic_context_pack_has_no_artifact_refs")
    if not tool_validation.get("passed"):
        errors.extend(str(item) for item in tool_validation.get("errors") or [])
    manifest_validation = payload_refs.get("payload_manifest_validation", {})
    if manifest_validation and not manifest_validation.get("passed"):
        errors.extend(str(item) for item in manifest_validation.get("errors") or [])
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "gpu1_dynamic_context_pack",
        "stamp": stamp,
        "active_context_pack": True,
        "passed": not errors,
        "request_chars": len(request_text or ""),
        "request_sha256": hashlib.sha256(
            (request_text or "").encode("utf-8", errors="replace")
        ).hexdigest(),
        "request_ref": payload_refs.get("request_ref", {}),
        "context_summary_ref": payload_refs.get("context_summary_ref", {}),
        "chunks_manifest_ref": payload_refs.get("chunks_manifest_ref", {}),
        "payload_manifest_ref": payload_refs.get("payload_manifest_ref", {}),
        "payload_manifest_validation": manifest_validation,
        "artifact_refs": selected_refs,
        "runtime_file_refs": runtime_file_refs,
        "tool_api_contract": {
            "api_native_required": True,
            "textual_tool_calls_are_not_executable": True,
            "provider_textual_tool_call_rejection": "provider_textual_tool_call_not_executable",
            "generic_write_without_native_tool_call_is_raw_gpu1_text_evidence": True,
            "tool_request_counter_source": "broker_request_artifacts_only",
            "transport_policy": "http_coordinates_filesystem_transports_mass",
            "large_payload_transport": "payload_file_or_artifact_ref",
        },
        "tool_definitions": tool_definitions,
        "tool_definition_validation": tool_validation,
        "broker_tool_schema_count": len(tool_definitions),
        "provider_native_tool_names": [str(item.get("name") or "") for item in tool_definitions],
        "api_native_tool_contract_ready": tool_validation.get("passed") is True,
        "capability_map": capability_map,
        "startup_tool_execution_count": len(commands),
        "side_effect_policy": {
            "provider_source_writes": "forbidden",
            "provider_patch_application": "forbidden",
            "allowed_outputs": "broker_report_artifacts_under_output",
        },
        "transport_policy": {
            "principle": "HTTP coordinates; filesystem transports mass.",
            "http_body": "job_id_payload_file_and_small_control_metadata_only",
            "filesystem": "authoritative_mass_transport",
            "manifest": "structure_and_checksums",
            "report": "verifiability",
            "no_operational_excerpts": True,
        },
        "missing_value_policy": {
            "optional_missing": "empty_or_null",
            "required_missing": "typed_block_or_exception",
            "placeholder_strings_forbidden": ["not_available", "*_not_available"],
        },
        "errors": errors,
        "warnings": [],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
    }
    write_json(output_json, payload)
    output_md.write_text(render_gpu1_dynamic_context_markdown(payload), encoding="utf-8")
    return payload, output_json, output_md


def render_gpu1_dynamic_context_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# GPU1 Dynamic Context Pack",
        "",
        f"- Active context pack: `{payload.get('active_context_pack')}`",
        f"- Passed: `{payload.get('passed')}`",
        f"- Tool API contract ready: `{payload.get('api_native_tool_contract_ready')}`",
        f"- Tool definition count: `{payload.get('broker_tool_schema_count')}`",
        f"- Startup internal surface execution count: `{payload.get('startup_tool_execution_count')}`",
        "",
        "## Runtime Contract",
        "",
        "- GPU1 receives this compact dynamic pack as an artifact-ref control surface.",
        "- HTTP/API bodies coordinate job ids and payload refs; the filesystem carries mass.",
        "- Provider-native operative tools are exposed through API-ready definitions, not as prose commands.",
        "- Memory, RAG, chunks, raw output capture and reconstruction are mandatory internal runtime surfaces, not provider-selected tools.",
        "- Tool/lab/matrix/debug evidence counts only after broker request/result artifacts.",
        "- Markdown, fenced JSON, prose, and mixed textual tool calls are classified as `provider_textual_tool_call_not_executable`.",
        "- A strict whole-message Qwen JSON object is executable only when the selected model protocol enables that chat(tools=...) adapter.",
        "",
        "## Artifact Refs",
        "",
    ]
    for key, value in (payload.get("artifact_refs") or {}).items():
        if isinstance(value, dict):
            lines.append(
                f"- {key}: `{value.get('path')}` bytes=`{value.get('bytes')}` sha256=`{value.get('sha256')}`"
            )
        else:
            lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Payload Manifest", ""])
    for key in ("request_ref", "context_summary_ref", "chunks_manifest_ref", "payload_manifest_ref"):
        ref = payload.get(key) if isinstance(payload.get(key), dict) else {}
        lines.append(
            f"- {key}: `{ref.get('path', '')}` bytes=`{ref.get('bytes', 0)}` sha256=`{ref.get('sha256', '')}`"
        )
    lines.extend(["", "## Capability Map", ""])
    for key, value in (payload.get("capability_map") or {}).items():
        lines.append(f"### {key}")
        for field in ("tool", "prerequisites", "expected_artifacts", "side_effect_policy"):
            lines.append(f"- {field}: `{value.get(field)}`")
        lines.append("")
    lines.extend(["## Provider Native Tool Definitions", ""])
    for item in payload.get("tool_definitions") or []:
        lines.append(
            "- "
            + f"`{item.get('name')}` "
            + f"policy=`{item.get('side_effect_policy')}` "
            + f"timeout=`{item.get('timeout_seconds')}` "
            + f"artifacts=`{item.get('expected_artifacts')}`"
        )
    errors = payload.get("errors") or []
    if errors:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {item}" for item in errors)
    return "\n".join(lines).rstrip() + "\n"


def _artifact_refs(repo_root: Path, artifacts: dict[str, str]) -> dict[str, dict[str, Any]]:
    preferred = {
        "startup_context_pack_json": "startup_context_pack",
        "startup_context_pack_markdown": "startup_context_pack_markdown",
        "startup_repo_scan_index_json": "repo_index",
        "tool_catalog_json": "tool_catalog",
        "tool_catalog_markdown": "tool_catalog_markdown",
        "semantic_code_chunks_json": "semantic_code_chunks",
        "semantic_evidence_chunks_json": "semantic_evidence_chunks",
        "shared_memory_json": "shared_memory",
        "operational_memory_status_json": "operational_memory_status",
        "operational_memory_search_json": "operational_memory_search",
        "rag_context_pack_json": "rag_context_pack",
        "ai_context_pack_json": "ai_context_pack",
        "required_context_files_json": "required_context_files",
        "repo_docs_map_json": "repo_docs_map",
    }
    refs: dict[str, dict[str, Any]] = {}
    for key, kind in preferred.items():
        value = str(artifacts.get(key) or "").strip()
        if not value:
            continue
        ref = artifact_ref(value, repo_root, kind=kind, ref_id=key, producer="startup_reload")
        if ref.get("exists"):
            refs[key] = ref
    return refs


def _write_payload_manifest(
    *,
    repo_root: Path,
    output_dir: Path,
    stamp: str,
    request_text: str,
    artifact_refs: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    payload_dir = output_dir / "payload"
    chunks_dir = payload_dir / "chunks"
    request_ref = write_text_artifact(
        repo_root,
        payload_dir,
        name="request",
        text=request_text or "",
        kind="operator_request",
        producer="gpu1_dynamic_context_pack",
        suffix=".md",
    )
    context_summary = "\n".join(
        [
            "# Runtime Context Summary",
            "",
            "## Transport Contract",
            "HTTP coordinates job ids and payload refs. Filesystem artifacts carry full context, prompts, chunks, logs and reports.",
            "",
            "## Required Reading",
            "- request.md",
            "- chunks/chunks_manifest.json",
            "- referenced startup/RAG/tool artifacts in the payload manifest",
            "",
            "## Provider Semantics",
            "- GPU1 remains primary planner/chat/product owner.",
            "- GPU0/NPU remain packet_review_only sidecars until GPU1 consumes their refs.",
            "- Tool/lab/matrix/debug evidence counts only from native broker request/result artifacts.",
        ]
    )
    context_summary_ref = write_text_artifact(
        repo_root,
        payload_dir,
        name="context_summary",
        text=context_summary,
        kind="context_summary",
        producer="gpu1_dynamic_context_pack",
        suffix=".md",
    )
    chunks = [
        {
            "schema_version": 1,
            "chunk_id": key,
            "chunk_index": index,
            "chunk_count": len(artifact_refs),
            "kind": ref.get("kind"),
            "title": key,
            "path": ref.get("path"),
            "required_for": ["gpu1", "gpu0", "npu", "composer"],
            "depends_on": [context_summary_ref.get("path")],
            "bytes": ref.get("bytes"),
            "sha256": ref.get("sha256"),
            "source": ref.get("source") or ref.get("producer") or "startup_reload",
        }
        for index, (key, ref) in enumerate(artifact_refs.items(), start=1)
    ]
    chunks_manifest_ref = write_json_artifact(
        repo_root,
        chunks_dir,
        name="chunks_manifest",
        payload={
            "schema_version": 1,
            "kind": "semantic_chunk_manifest",
            "read_order": [item["chunk_id"] for item in chunks],
            "chunks": chunks,
        },
        kind="chunks_manifest",
        producer="gpu1_dynamic_context_pack",
    )
    manifest_path = payload_dir / "manifest.json"
    refs = [request_ref, context_summary_ref, chunks_manifest_ref, *artifact_refs.values()]
    provider_input_refs = [
        ref.get("path")
        for ref in [request_ref, context_summary_ref, chunks_manifest_ref, *artifact_refs.values()]
        if isinstance(ref, dict) and ref.get("path")
    ]
    write_transport_manifest(
        repo_root,
        manifest_path,
        job_id=stamp,
        run_dir=output_dir,
        refs=refs,
        extra={
            "input": {
                "request_path": request_ref.get("path"),
                "context_summary_path": context_summary_ref.get("path"),
            },
            "context": {
                "chunks_manifest_path": chunks_manifest_ref.get("path"),
                "artifact_ref_keys": list(artifact_refs),
            },
            "heap": {"pointer_refs": [], "revision_refs": []},
            "providers": {
                "gpu1": {"role": "primary_planner", "input_refs": provider_input_refs},
                "gpu0": {"role": "packet_review_only", "input_refs": provider_input_refs},
                "npu": {"role": "packet_review_only", "input_refs": provider_input_refs},
            },
            "broker": {"tool_request_refs": [], "tool_result_refs": []},
            "output": {"report_path": "", "documents_dir": "", "stdout_path": "", "stderr_path": ""},
            "read_order": ["context_summary", "request", "chunks_manifest", "artifact_refs"],
        },
    )
    payload_manifest_ref = artifact_ref(
        manifest_path,
        repo_root,
        kind="ia_carmine_runtime_payload_manifest",
        ref_id="runtime_payload_manifest",
        producer="gpu1_dynamic_context_pack",
    )
    payload_manifest_validation = validate_runtime_payload_manifest(repo_root, manifest_path)
    return {
        "request_ref": request_ref,
        "context_summary_ref": context_summary_ref,
        "chunks_manifest_ref": chunks_manifest_ref,
        "payload_manifest_ref": payload_manifest_ref,
        "payload_manifest_validation": payload_manifest_validation,
    }


def _runtime_file_refs(artifacts: dict[str, str]) -> dict[str, Any]:
    return {
        "policy": "runtime_file_refs_is_hard_gate_before_provider",
        "source_ref_surfaces": [
            value
            for key, value in artifacts.items()
            if key
            in {
                "startup_repo_scan_index_json",
                "semantic_code_chunks_json",
                "semantic_evidence_chunks_json",
                "repo_docs_map_json",
            }
            and value
        ],
        "no_placeholder_refs": True,
    }


def _capability_map(tool_definitions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_name = {str(item.get("name") or ""): item for item in tool_definitions}
    entries = {
        "runtime_file_refs": "Resolve provider/operator refs before provider product claims.",
        "virtual_dev_environment": "Probe AST/import/help/compile for concrete source targets.",
        "code_execution_matrix": "Execute guarded matrix for verified code proposals.",
        "runtime_debug_lab": "Run report-only Python debug lab.",
        "patch_candidate_synthesis": "Create artifact-owned patch candidates from verified targets.",
    }
    tool_for = {
        "virtual_dev_environment": "run_heap_virtual_dev_environment",
        "code_execution_matrix": "run_heap_code_execution_matrix",
        "runtime_debug_lab": "agent_runtime_debug_lab",
        "patch_candidate_synthesis": "synthesize_patch_candidates",
        "runtime_file_refs": "runtime_file_refs",
    }
    mapped: dict[str, dict[str, Any]] = {}
    for name, description in entries.items():
        tool = tool_for[name]
        definition = by_name.get(tool, {})
        mapped[name] = {
            "description": description,
            "tool": tool,
            "input_schema": definition.get("input_schema") or {},
            "expected_artifacts": definition.get("expected_artifacts") or [],
            "side_effect_policy": definition.get("side_effect_policy") or "",
            "prerequisites": _prerequisites(name),
            "counts_as_called_when": "native_tool_call_and_broker_request_artifact_exist",
            "counts_as_usable_when": "expected_report_written_schema_valid_and_targets_present",
        }
    return mapped


def _prerequisites(name: str) -> list[str]:
    if name == "runtime_file_refs":
        return ["startup_repo_scan_index_json", "semantic_code_chunks_json"]
    if name == "code_execution_matrix":
        return ["runtime_file_refs_passed", "verified_target_files"]
    if name == "virtual_dev_environment":
        return ["verified_target_files"]
    if name == "runtime_debug_lab":
        return ["broker_request_args_schema_valid"]
    return ["verified_target_files", "matrix_or_provider_evidence"]
