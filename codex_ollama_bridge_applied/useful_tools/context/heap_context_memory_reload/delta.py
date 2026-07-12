"""Delta detection for heap startup context reload."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ia_carmine.context.heap_context_memory_reload.common import read_json, repo_rel, sha256_text, write_json
from ia_carmine.context.heap_context_memory_reload.runner_state import ReloadRun
from ia_carmine.context.heap_context_memory_reload.startup_scan import scan_entries_by_path


def context_signature(repo_root: Path, rel_path: str) -> dict[str, Any]:
    path = repo_root / rel_path
    try:
        stat = path.stat()
    except OSError:
        return {"path": rel_path, "exists": False, "size_bytes": 0, "mtime_ns": 0}
    return {
        "path": rel_path,
        "exists": path.is_file(),
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def digest_context(request_text: str, signatures: list[dict[str, Any]]) -> str:
    payload = {"request_sha256": sha256_text(request_text), "files": signatures}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def build_context_delta(state: ReloadRun) -> None:
    scan_by_path = scan_entries_by_path(state.repo_scan_index)
    signatures = []
    diagnostics: list[dict[str, Any]] = []
    for path in state.context_files:
        scan_entry = scan_by_path.get(path)
        if scan_entry:
            diagnostics.append(
                {
                    "path": path,
                    "delta_status": str(scan_entry.get("delta_status") or ""),
                }
            )
            signatures.append(
                {
                    "path": path,
                    "exists": True,
                    "size_bytes": int(scan_entry.get("size_bytes") or 0),
                    "mtime_ns": int(scan_entry.get("mtime_ns") or 0),
                    "content_hash": str(scan_entry.get("content_hash") or ""),
                }
            )
        else:
            signatures.append(context_signature(state.repo_root, path))
    current_digest = digest_context(state.request_text, signatures)
    cache = state.repo_root / "output" / "ai_runtime_memory" / "startup_context_digest.json"
    previous = read_json(cache)
    previous_by_path = {
        str(item.get("path") or ""): item
        for item in previous.get("context_file_signatures", [])
        if isinstance(item, dict)
    }
    changed: list[str] = []
    unchanged_count = 0
    for item in signatures:
        rel_path = str(item.get("path") or "")
        if _comparison_signature(previous_by_path.get(rel_path)) == _comparison_signature(item):
            unchanged_count += 1
        else:
            changed.append(rel_path)
    state.context_delta = {
        "schema_version": 1,
        "kind": "heap_startup_context_delta",
        "reload_mode": "initial_full_index" if not previous else "delta_index",
        "current_digest": current_digest,
        "previous_digest": str(previous.get("current_digest") or ""),
        "request_sha256": sha256_text(state.request_text),
        "request_changed": previous.get("request_sha256") != sha256_text(state.request_text),
        "context_file_count": len(signatures),
        "changed_context_file_count": len(changed),
        "unchanged_context_file_count": unchanged_count,
        "changed_context_files": changed[:240],
        "unchanged_preview_policy": "omit_unchanged_bounded_previews_use_file_refs",
        "context_file_signatures": signatures,
        "context_file_diagnostics": diagnostics,
    }
    delta_path = state.output_dir / "startup_context_delta.json"
    write_json(delta_path, state.context_delta)
    cache.parent.mkdir(parents=True, exist_ok=True)
    write_json(cache, state.context_delta)
    state.artifacts["startup_context_delta_json"] = repo_rel(state.repo_root, delta_path)


def _comparison_signature(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    signature = dict(item)
    signature.pop("delta_status", None)
    return signature
