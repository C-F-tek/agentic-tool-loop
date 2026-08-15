"""Executed-tool evidence views for OpenWebUI follow-up context."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from ..shared.payload_metadata import sha256_text


RepoReadContentLoader = Callable[[dict[str, Any]], tuple[str, dict[str, Any]]]
KeyLineExtractor = Callable[[str], list[str]]


def repo_read_content_views(
    history: list[dict[str, Any]],
    
    repo_read_item_full_content: RepoReadContentLoader,
    per_item_limit: int = 60000,
    total_limit: int = 180000,
) -> list[dict[str, Any]]:
    """Return repo_read payload metadata without duplicating file content."""
    views: list[dict[str, Any]] = []
    used = 0
    seen: set[tuple[str, str]] = set()
    for item in history if isinstance(history, list) else []:
        if not isinstance(item, dict):
            continue
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        if result.get("tool") != "repo_read":
            continue
        artifact = str(result.get("artifact") or "")
        source_result = result
        if artifact:
            try:
                artifact_path = Path(artifact)
                if artifact_path.exists() and artifact_path.is_file():
                    loaded = json.loads(artifact_path.read_text(encoding="utf-8", errors="replace"))
                    if isinstance(loaded, dict):
                        source_result = loaded
            except Exception:
                source_result = result
        for read_item in source_result.get("items") or []:
            if not isinstance(read_item, dict) or not read_item.get("ok") or not read_item.get("path"):
                continue
            path = str(read_item.get("path"))
            content, _content_meta = repo_read_item_full_content(read_item)
            if not content:
                content = str(
                    read_item.get("content")
                    or read_item.get("content_view")
                    or read_item.get("content_preview")
                    or ""
                )
            if not content:
                continue
            key = (path, artifact)
            if key in seen:
                continue
            seen.add(key)
            view = {
                "path": path,
                "line_count": read_item.get("line_count"),
                "tool_truncated": bool(read_item.get("truncated")),
                "content_chars": len(content),
                "content_sha256": sha256_text(content),
                "content_not_duplicated_here": True,
                "content_location": (
                    "tool_context_for_30b.artifacts[*].artifact.content "
                    "matching this path and content_sha256"
                ),
            }
            metadata_chars = len(json.dumps(view, ensure_ascii=False, default=str))
            if total_limit > 0 and used + metadata_chars > total_limit:
                break
            used += metadata_chars
            views.append(view)
        if used >= total_limit:
            break
    return views


def execution_evidence_digest_text(
    result: dict[str, Any] | None,
    
    repo_read_item_full_content: RepoReadContentLoader,
    extract_key_lines: KeyLineExtractor,
    limit: int = 12000,
) -> str:
    """Human-visible evidence from the actual executed loop."""
    result = result if isinstance(result, dict) else {}
    history = result.get("history") if isinstance(result.get("history"), list) else []
    if not history:
        return ""
    reads: list[str] = []
    lists: list[str] = []
    content_views = repo_read_content_views(
        history,
        repo_read_item_full_content=repo_read_item_full_content,
    )
    guards: list[str] = []
    repairs: list[str] = []
    raw_outputs: list[str] = []
    read_notes: list[str] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        tool_result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        tool = str(tool_result.get("tool") or decision.get("tool") or "")
        if tool == "repo_read":
            paths: list[str] = []
            for read_item in tool_result.get("items") or []:
                if isinstance(read_item, dict) and read_item.get("ok") and read_item.get("path"):
                    path = str(read_item.get("path"))
                    paths.append(path)
                    content = str(read_item.get("content") or read_item.get("content_preview") or "")
                    key_lines = extract_key_lines(content)
                    note = key_lines[0] if key_lines else ""
                    if note:
                        note = note[:180].replace("\n", " ")
                        row = f"{path}: {note}"
                        if row not in read_notes:
                            read_notes.append(row)
            if not paths and tool_result.get("path"):
                paths.append(str(tool_result.get("path")))
            for path in paths:
                if path not in reads:
                    reads.append(path)
        elif tool in {"repo_tree", "repo_list_files"}:
            path = tool_result.get("path")
            if path not in (None, ""):
                total = tool_result.get("total_matches") or tool_result.get("entries_total") or tool_result.get("count")
                truncated = tool_result.get("truncated")
                label = f"{tool}:{path}"
                if total not in (None, ""):
                    label += f" total={total}"
                if truncated:
                    label += " truncated=true"
                if label not in lists:
                    lists.append(label)
        elif tool == "controller_guard":
            summary = str(tool_result.get("summary") or "")
            if summary and summary not in guards:
                guards.append(summary)
            guard_raw = str(tool_result.get("raw_planner_text_preview") or "")
            if guard_raw:
                compact_raw = re.sub(r"\s+", " ", guard_raw).strip()[:500]
                if compact_raw and compact_raw not in raw_outputs:
                    raw_outputs.append(compact_raw)
            repair = tool_result.get("vulkan_repair") if isinstance(tool_result.get("vulkan_repair"), dict) else {}
            if repair:
                repair_label = "ok=" + str(repair.get("ok"))
                if repair.get("error"):
                    repair_label += " error=" + str(repair.get("error"))[:160]
                if repair_label not in repairs:
                    repairs.append(repair_label)
                raw_preview = str(repair.get("raw_planner_text_preview") or "")
                if raw_preview:
                    compact_raw = re.sub(r"\s+", " ", raw_preview).strip()[:500]
                    if compact_raw and compact_raw not in raw_outputs:
                        raw_outputs.append(compact_raw)
        elif decision.get("raw_planner_text_before_deterministic_strip"):
            raw_preview = str(decision.get("raw_planner_text_before_deterministic_strip") or "")
            compact_raw = re.sub(r"\s+", " ", raw_preview).strip()[:500]
            if compact_raw and compact_raw not in raw_outputs:
                raw_outputs.append(compact_raw)
    parts = [
        "OpenWebUI follow-up evidence from executed tools:",
        f"- agentic_steps_recorded={len(history)}",
    ]
    if lists:
        parts.append("- list/tree evidence: " + "; ".join(lists[:8]))
    if reads:
        shown = reads[:32]
        suffix = f" (+{len(reads) - len(shown)} more)" if len(reads) > len(shown) else ""
        parts.append("- successful repo_read paths: " + ", ".join(shown) + suffix)
    if read_notes:
        parts.append("- concrete content evidence:")
        for note in read_notes[:10]:
            parts.append("  - " + note)
    if content_views:
        parts.append("- repo_read payload metadata:")
        for view in content_views:
            meta = (
                f"path={view.get('path')} lines={view.get('line_count')} "
                f"chars={view.get('content_chars')} sha256={view.get('content_sha256')}"
            )
            if view.get("tool_truncated"):
                meta += " tool_truncated=true"
            meta += " content_not_duplicated_here=true"
            parts.append("  - " + meta)
    if guards:
        parts.append("- controller_guard events: " + "; ".join(guards[:5]))
    if repairs:
        parts.append("- Vulkan/GPU0 repair events: " + "; ".join(repairs[:5]))
    if raw_outputs:
        parts.append("- raw planner output surfaced:")
        for raw in raw_outputs[:3]:
            parts.append("  - " + raw)
    text = "\n".join(parts)
    return text[:limit] if int(limit or 0) > 0 else text
