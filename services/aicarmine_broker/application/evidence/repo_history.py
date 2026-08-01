"""Repository evidence extraction frfrom services.aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

om planner tool history."""
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..shared.history_queries import history_tool_result
from ..shared.path_tokens import repo_rel_token
from .repo_path_policy import low_signal_top_dir, repo_code_file, top_dir


SameToolArtifactPayload = Callable[[dict[str, Any]], dict[str, Any]]
SafeRelPath = Callable[[str], str]


def append_unique(seq: list[Any], value: Any) -> None:
    if value in (None, "", [], {}):
        return
    item = repo_rel_token(value) if isinstance(value, str) else value
    if item not in seq:
        seq.append(item)


def read_items_from_history(
    history: list[dict[str, Any]],
    *,
    same_tool_artifact_payload: SameToolArtifactPayload,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in history if isinstance(history, list) else []:
        result = history_tool_result(row)
        if result.get("tool") != "repo_read" or not result.get("ok"):
            continue
        source = same_tool_artifact_payload(result)
        source_items = source.get("items") if isinstance(source.get("items"), list) else result.get("items")
        for read_item in result.get("items") or []:
            if isinstance(read_item, dict) and read_item.get("ok"):
                item = dict(read_item)
                for source_item in source_items or []:
                    if (
                        isinstance(source_item, dict)
                        and repo_rel_token(source_item.get("path") or "") == repo_rel_token(item.get("path") or "")
                    ):
                        item.setdefault("artifact", source_item.get("artifact"))
                        if source_item.get("content") not in (None, ""):
                            item.setdefault("content", source_item.get("content"))
                        break
                item.setdefault("step", row.get("step"))
                item["path"] = repo_rel_token(item.get("path") or "")
                items.append(item)
    return items


def extract_headings(content: str) -> list[str]:
    headings: list[str] = []
    for line in str(content or "").splitlines():
        s = line.strip()
        if s.startswith("#"):
            heading = s.lstrip("#").strip()
            if heading and heading not in headings:
                headings.append(heading)
        if len(headings) >= 12:
            break
    return headings


def extract_key_lines(content: str) -> list[str]:
    key_lines: list[str] = []
    needles = (
        "entrypoint", "entry point", "canonical", "workflow", "runtime", "heap",
        "provider", "tool", "problem", "issue", "fix", "expected", "must ",
        "non-negotiable", "limitation", "core", "memory", "context", "chunk",
    )
    for line in str(content or "").splitlines():
        s = line.strip()
        if not s or len(s) > 240:
            continue
        low = s.lower()
        if s.startswith("#") or any(n in low for n in needles) or "/" in s:
            if s not in key_lines:
                key_lines.append(s)
        if len(key_lines) >= 16:
            break
    return key_lines


def extract_mentioned_paths(content: str) -> list[str]:
    paths: list[str] = []
    pattern = r'(?<![\w.-])(?:[A-Za-z0-9_.@+-]+/){1,}[A-Za-z0-9_.@+ -]+(?:\.[A-Za-z0-9_+-]+)?'
    for match in re.finditer(pattern, str(content or "")):
        p = repo_rel_token(match.group(0).strip("`\"'.,);:"))
        if p and p != "." and p not in paths:
            paths.append(p)
        if len(paths) >= 24:
            break
    return paths


def file_memory_from_history(
    history: list[dict[str, Any]],
    *,
    same_tool_artifact_payload: SameToolArtifactPayload,
) -> list[dict[str, Any]]:
    memory: list[dict[str, Any]] = []
    for item in read_items_from_history(history, same_tool_artifact_payload=same_tool_artifact_payload):
        content = str(item.get("content") or item.get("content_preview") or "")
        path = repo_rel_token(item.get("path") or "")
        if not path:
            continue
        memory.append({
            "path": path,
            "line_count": item.get("line_count"),
            "truncated": item.get("truncated"),
            "headings": extract_headings(content),
            "key_lines": extract_key_lines(content),
            "mentioned_paths": extract_mentioned_paths(content),
            "content_excerpt": content[:1800],
        })
    return memory


def repo_list_evidence(
    history: list[dict[str, Any]],
    *,
    same_tool_artifact_payload: SameToolArtifactPayload,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in history if isinstance(history, list) else []:
        result = history_tool_result(item)
        tool = str(result.get("tool") or "")
        if tool not in {"repo_list_files", "repo_tree"} or not result.get("ok"):
            continue

        paths: list[str] = []
        keys = ("paths", "paths_preview") if tool == "repo_list_files" else (
            "entries", "entries_preview", "files", "files_preview",
        )
        sources = [result]
        raw_payload = same_tool_artifact_payload(result)
        if isinstance(raw_payload, dict):
            sources.append(raw_payload)
        for source in sources:
            for key in keys:
                value = source.get(key)
                if not isinstance(value, list):
                    continue
                for raw in value:
                    p = raw.get("path") if isinstance(raw, dict) else raw
                    p = repo_rel_token(p or "")
                    if p and p not in paths:
                        paths.append(p)

        rows.append({
            "step": item.get("step"),
            "tool": tool,
            "path": repo_rel_token(result.get("path") or "."),
            "total_matches": result.get("total_matches")
            if tool == "repo_list_files"
            else result.get("entries_total") or result.get("count"),
            "limit": result.get("limit"),
            "truncated": result.get("truncated"),
            "paths_preview": paths[:80],
        })
    return rows


def successful_repo_read_paths(
    history: list[dict[str, Any]],
    *,
    same_tool_artifact_payload: SameToolArtifactPayload,
) -> list[str]:
    paths: list[str] = []
    for item in history if isinstance(history, list) else []:
        result = history_tool_result(item)
        if result.get("tool") != "repo_read" or result.get("ok") is not True:
            continue
        source = same_tool_artifact_payload(result)
        raw_items = source.get("items") if isinstance(source.get("items"), list) else []
        if not raw_items and source.get("path"):
            raw_items = [source]
        if not raw_items:
            raw_items = result.get("items") if isinstance(result.get("items"), list) else []
        if not raw_items and result.get("path"):
            raw_items = [result]
        for sub in raw_items:
            if not isinstance(sub, dict) or sub.get("ok") is False:
                continue
            path = repo_rel_token(sub.get("path") or sub.get("repo_path") or "")
            if path and path not in paths:
                paths.append(path)
    return paths


def failed_repo_read_paths(history: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for item in history if isinstance(history, list) else []:
        result = history_tool_result(item)
        if result.get("tool") != "repo_read":
            continue
        for sub in result.get("items") or []:
            if isinstance(sub, dict) and sub.get("ok") is False and sub.get("path"):
                path = repo_rel_token(sub.get("path") or "")
                if path and path not in paths:
                    paths.append(path)
    return paths


def failed_repo_list_files_paths(history: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for item in history if isinstance(history, list) else []:
        result = item.get("tool_result") if isinstance(item, dict) and isinstance(item.get("tool_result"), dict) else {}
        if result.get("tool") != "repo_list_files" or result.get("ok") is not False:
            continue
        path = repo_rel_token(result.get("path") or "")
        if path and path not in paths:
            paths.append(path)
    return paths


def rank_core_candidates(
    file_memory: list[dict[str, Any]],
    list_rows: list[dict[str, Any]],
    *,
    repo_root: Path,
    safe_rel_path: SafeRelPath,
) -> list[dict[str, Any]]:
    scores: dict[str, int] = {}
    reasons: dict[str, list[str]] = {}

    def add(path: str, score: int, reason: str) -> None:
        top = top_dir(path)
        if not top or low_signal_top_dir(top):
            return
        # Mentioned paths can come from prose such as "GPU0/NPU sidecar completion".
        # Do not promote prose fragments into repo_list_files candidates unless the
        # top-level directory actually exists in the checked repository.
        try:
            full = (repo_root / safe_rel_path(top)).resolve(strict=False)
            full.relative_to(repo_root)
            if not full.exists() or not full.is_dir():
                return
        except Exception:
            return
        scores[top] = scores.get(top, 0) + score
        reasons.setdefault(top, [])
        if reason not in reasons[top]:
            reasons[top].append(reason)

    for row in list_rows:
        p = repo_rel_token(row.get("path") or "")
        if p and p != ".":
            add(p, 25, "listed non-root directory")
        for sub in row.get("paths_preview") or []:
            add(
                sub,
                20 if repo_code_file(sub) else 8,
                "listed code/file evidence" if repo_code_file(sub) else "listed path evidence",
            )

    for item in file_memory:
        for p in item.get("mentioned_paths") or []:
            add(p, 18 if repo_code_file(p) else 6, "mentioned by read documentation")
        for line in item.get("key_lines") or []:
            for p in extract_mentioned_paths(line):
                add(p, 18 if repo_code_file(p) else 6, "mentioned by key evidence line")

    ranked = sorted(scores, key=lambda k: (-scores[k], k.lower()))
    return [{"path": p, "score": scores[p], "reasons": reasons.get(p, [])[:6]} for p in ranked[:12]]
