"""Task Markdown and operational-memory note builders."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ia_carmine.context.heap_context_memory_reload.common import read_text, sha256_text

TASK_CONTEXT_FILE_ROW_LIMIT = 240
TASK_CONTEXT_PREVIEW_FILE_LIMIT = 16
TASK_CONTEXT_PREVIEW_CHARS = 1200


def build_context_loaded_block(artifacts: dict[str, str]) -> list[str]:
    key_labels = (
        ("tool_catalog_json", "tool catalog"),
        ("shared_memory_json", "memory inventory"),
        ("operational_memory_status_json", "operational memory status"),
        ("operational_memory_search_json", "operational memory search"),
        ("shared_context_json", "transient request context"),
        ("gpu1_dynamic_context_pack_json", "active GPU1 dynamic context pack"),
        ("gpu1_dynamic_context_pack_markdown", "active GPU1 dynamic context pack markdown"),
        ("startup_context_pack_json", "legacy unified context pack attachment"),
        ("startup_context_pack_markdown", "legacy unified context pack markdown attachment"),
        ("ai_context_pack_json", "static AI context pack evidence"),
        ("ai_context_pack_markdown", "static AI context pack markdown"),
        ("rag_context_pack_json", "RAG context pack evidence"),
        ("rag_context_pack_markdown", "RAG context pack markdown"),
        ("semantic_code_chunks_json", "semantic chunks"),
        ("semantic_evidence_chunks_json", "semantic evidence chunks"),
        ("repo_docs_map_json", "repo docs map"),
    )
    lines = ["CONTEXT LOADED INTO HEAP:"]
    for key, label in key_labels:
        value = artifacts.get(key, "")
        lines.append(f"- {label}: `{value}`")
    return lines


def build_task_markdown(
    *,
    repo_root: Path,
    request: str,
    stamp: str,
    context_files: list[str],
    artifacts: dict[str, str],
    commands: list[dict[str, Any]],
    warnings: list[str],
    context_delta: dict[str, Any],
    startup_reload_degraded: bool,
    degraded_requirements: list[str],
    blocking_requirements: list[str],
) -> str:
    lines: list[str] = [
        "# Heap Startup Input-Ready Context",
        "",
        f"- Stamp: `{stamp}`",
        "- Source: `prepare_heap_context_memory_reload.py`",
        "- Mode: `runtime_owned_pre_provider_reload`",
        f"- Startup reload degraded: `{startup_reload_degraded}`",
        f"- Context reload mode: `{context_delta.get('reload_mode', '')}`",
        f"- Changed context files: `{context_delta.get('changed_context_file_count', 0)}`",
        f"- Unchanged context refs: `{context_delta.get('unchanged_context_file_count', 0)}`",
        f"- Degraded requirements: `{degraded_requirements}`",
        f"- Blocking requirements: `{blocking_requirements}`",
        "- Provider execution performed: `False`",
        "- Patch application performed: `False`",
        "- Source writes performed: `False`",
        "",
        "## Operator request",
        "",
        request.strip() or "(empty)",
        "",
        "## Reload contract for heap providers",
        "",
        "- Before GPU1 planning, consume this task file as startup heap context.",
        "- Treat listed artifacts as the current source of knowledge for repo, docs, tool catalog and memory inventory.",
        "- Use startup_context_delta_json to decide what changed; unchanged context refs are pointers, not content to reload blindly.",
        "- If startup_reload_degraded is true, block provider start and repair the internal preload surface first.",
        "- Do not answer from a single token window: write proposal chunks and let the final composer assemble them.",
        "- GPU0 must refine or reject generic/stub chunks using source anchors and quality diagnosis.",
        "- NPU must contribute bounded audit/workload evidence when enabled.",
        "- Memory, RAG, chunks, raw startup context and context packs are mandatory internal runtime surfaces, not provider-selected tools and not advisory.",
        "",
        "## Context loaded into heap",
        "",
        *build_context_loaded_block(artifacts),
        "",
        "## Startup artifacts",
        "",
    ]
    lines.extend(f"- `{name}`: `{value}`" for name, value in artifacts.items() if value)
    lines.extend(["", "## Startup internal surface executions", ""])
    for item in commands:
        lines.append(
            "- "
            + f"name=`{item.get('name')}` "
            + f"required=`{item.get('required')}` "
            + f"passed=`{item.get('passed')}` "
            + f"effective_passed=`{item.get('effective_passed')}` "
            + f"degraded=`{item.get('degraded')}` "
            + f"rc=`{item.get('returncode')}` "
            + f"artifacts=`{item.get('useful_artifact_paths')}`"
        )
    if warnings:
        lines.extend(["", "## Startup warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)
    lines.extend(["", "## Canonical context files loaded", ""])
    lines.append(f"- Context file count: `{len(context_files)}`")
    lines.append("- Full context file list: `heap_context_memory_reload_manifest.json`")
    for rel_path in context_files[:TASK_CONTEXT_FILE_ROW_LIMIT]:
        lines.append(f"- `{rel_path}`")
    if len(context_files) > TASK_CONTEXT_FILE_ROW_LIMIT:
        remaining = len(context_files) - TASK_CONTEXT_FILE_ROW_LIMIT
        lines.append(f"- ... `{remaining}` additional refs in the startup manifest")
    lines.extend(["", "## Bounded context previews", ""])
    for rel_path in context_files[:TASK_CONTEXT_PREVIEW_FILE_LIMIT]:
        text = read_text(repo_root / rel_path, max_chars=TASK_CONTEXT_PREVIEW_CHARS)
        if text:
            lines.extend([f"### `{rel_path}`", "", "```text", text, "```", ""])
    return "\n".join(lines)


def append_artifact_ref(refs: list[str], value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        return
    normalized = value.replace("\\", "/")
    if normalized not in refs:
        refs.append(normalized)


def collect_startup_artifact_refs(
    artifacts: dict[str, str], commands: list[dict[str, Any]]
) -> list[str]:
    refs: list[str] = []
    for value in artifacts.values():
        append_artifact_ref(refs, value)
    for execution in commands:
        if not isinstance(execution, dict):
            continue
        for key in ("useful_artifact_paths", "existing_artifact_paths", "artifact_paths"):
            for value in execution.get(key) or []:
                append_artifact_ref(refs, value)
        for summary in execution.get("artifact_summaries") or []:
            if isinstance(summary, dict):
                append_artifact_ref(refs, summary.get("path"))
        for artifact in execution.get("artifacts") or []:
            append_artifact_ref(refs, artifact.get("path") if isinstance(artifact, dict) else artifact)
    return refs


def build_operational_memory_write_content(
    *,
    stamp: str,
    request: str,
    startup_reload_degraded: bool,
    degraded_requirements: list[str],
    blocking_requirements: list[str],
    artifacts: dict[str, str],
    commands: list[dict[str, Any]],
    context_delta: dict[str, Any],
) -> str:
    payload = {
        "schema_version": 1,
        "kind": "heap_startup_operational_memory_note",
        "stamp": stamp,
        "request_file": artifacts.get("startup_request_file", ""),
        "request_chars": len(request or ""),
        "request_sha256": sha256_text(request),
        "startup_reload_degraded": startup_reload_degraded,
        "context_reload_mode": context_delta.get("reload_mode", ""),
        "context_delta_digest": context_delta.get("current_digest", ""),
        "changed_context_file_count": context_delta.get("changed_context_file_count", 0),
        "unchanged_context_file_count": context_delta.get("unchanged_context_file_count", 0),
        "changed_context_files": context_delta.get("changed_context_files", [])[:80],
        "degraded_requirements": degraded_requirements,
        "blocking_requirements": blocking_requirements,
        "artifact_refs": collect_startup_artifact_refs(artifacts, commands)[:80],
        "tool_execution_summary": [
            {
                "name": item.get("name"),
                "requirement": item.get("requirement"),
                "passed": item.get("passed"),
                "effective_passed": item.get("effective_passed"),
                "degraded": item.get("degraded"),
                "useful_artifact_paths": item.get("useful_artifact_paths", []),
            }
            for item in commands
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)
