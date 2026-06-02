"""Compose the active startup context pack from static and RAG components."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import now_iso, read_json, repo_rel, report_flags, sha256_text


def _component_ref(repo_root: Path, path: Path, kind: str) -> dict[str, Any]:
    payload = read_json(path)
    return {
        "kind": kind,
        "path": repo_rel(repo_root, path),
        "exists": path.exists(),
        "passed": payload.get("passed"),
        "source_kind": payload.get("kind"),
        "warnings": (payload.get("warnings") or [])[:20] if isinstance(payload.get("warnings"), list) else [],
        "errors": (payload.get("errors") or [])[:20] if isinstance(payload.get("errors"), list) else [],
    }


def build_unified_context_pack(
    *,
    repo_root: Path,
    ai_context_pack_json: Path,
    rag_context_pack_json: Path,
    stamp: str,
) -> dict[str, Any]:
    ai_pack = read_json(ai_context_pack_json)
    rag_pack = read_json(rag_context_pack_json)
    rag_chunks = rag_pack.get("chunks") if isinstance(rag_pack.get("chunks"), list) else []
    ai_files = ai_pack.get("files") if isinstance(ai_pack.get("files"), list) else []
    selected_ai_files = [
        {
            "path": item.get("path"),
            "role": item.get("role"),
            "included_chars": item.get("included_chars"),
            "sha256": item.get("sha256"),
        }
        for item in ai_files[:40]
        if isinstance(item, dict)
    ]
    context_pack_id = sha256_text(
        f"{stamp}:{ai_pack.get('generated_at')}:{rag_pack.get('context_pack_id')}"
    )[:32]
    warnings: list[str] = []
    errors: list[str] = []
    for pack_name, payload in (("ai_context_pack", ai_pack), ("rag_context_pack", rag_pack)):
        if payload.get("warnings"):
            warnings.extend(f"{pack_name}: {item}" for item in payload.get("warnings", [])[:10])
        if payload.get("errors"):
            errors.extend(f"{pack_name}: {item}" for item in payload.get("errors", [])[:10])
    return {
        "schema_version": 1,
        "kind": "startup_unified_context_pack",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "stamp": stamp,
        "context_pack_id": context_pack_id,
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        **report_flags(),
        "active_context_pack": True,
        "component_policy": "static_ai_context_pack_plus_rag_retrieval_single_provider_surface",
        "components": [
            _component_ref(repo_root, ai_context_pack_json, "static_ai_context_pack"),
            _component_ref(repo_root, rag_context_pack_json, "rag_context_pack"),
        ],
        "ai_context_pack": {
            "path": repo_rel(repo_root, ai_context_pack_json),
            "included_file_count": ai_pack.get("included_file_count"),
            "total_included_chars": ai_pack.get("total_included_chars"),
            "files": selected_ai_files,
        },
        "rag_context_pack": {
            "path": repo_rel(repo_root, rag_context_pack_json),
            "retrieved_count": rag_pack.get("retrieved_count"),
            "total_selected_chars": rag_pack.get("total_selected_chars"),
            "sources": rag_pack.get("sources") or [],
            "chunks": rag_chunks[:40],
            "retrieval_config": rag_pack.get("retrieval_config") or {},
            "retrieval_event_id": rag_pack.get("retrieval_event_id") or "",
        },
    }


def render_markdown(pack: dict[str, Any]) -> str:
    lines = [
        "# Startup Unified Context Pack",
        "",
        f"- Passed: `{pack.get('passed')}`",
        f"- Active context pack: `{pack.get('active_context_pack')}`",
        f"- Context pack id: `{pack.get('context_pack_id')}`",
        f"- Component policy: `{pack.get('component_policy')}`",
        f"- Provider execution performed: `{pack.get('provider_execution_performed')}`",
        f"- Source writes performed: `{pack.get('source_writes_performed')}`",
        f"- Patch application performed: `{pack.get('patch_application_performed')}`",
        "",
        "## Components",
        "",
    ]
    for component in pack.get("components") or []:
        lines.append(f"- `{component.get('kind')}`: `{component.get('path')}` passed=`{component.get('passed')}`")
    rag = pack.get("rag_context_pack") if isinstance(pack.get("rag_context_pack"), dict) else {}
    lines.extend(["", "## RAG Sources", ""])
    for source in rag.get("sources") or []:
        lines.append(f"- `{source}`")
    lines.extend(["", "## RAG Chunks", ""])
    for item in rag.get("chunks") or []:
        lines.extend(
            [
                f"### `{item.get('source_path')}#{item.get('chunk_index')}`",
                "",
                f"- Chunk id: `{item.get('chunk_id')}`",
                f"- Fused score: `{item.get('fused_score')}`",
                "",
                "```text",
                str(item.get("text") or "")[:2400],
                "```",
                "",
            ]
        )
    if pack.get("warnings"):
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {item}" for item in pack["warnings"][:40])
    if pack.get("errors"):
        lines.extend(["## Errors", ""])
        lines.extend(f"- {item}" for item in pack["errors"][:40])
    return "\n".join(lines).rstrip() + "\n"
