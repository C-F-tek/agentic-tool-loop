"""Code-product build-state history and action helpers."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .code_product_state import (
    CODE_PRODUCT_BUILD_STATE_KIND,
    CODE_PRODUCT_BUILD_STATE_SCHEMA,
    code_product_build_state_parse,
    code_product_build_state_ready_payload,
    code_product_build_state_section,
    goal_exact_text_block,
)
from .history_queries import history_tool_result
from .path_tokens import repo_rel_token
from .prompt_values import text_hash


ArtifactPayloadLoader = Callable[[dict[str, Any]], dict[str, Any]]
RepoReadFullContentLoader = Callable[[dict[str, Any]], tuple[str, dict[str, Any]]]


def code_product_build_state_duplicate_write(
    history: list[dict[str, Any]],
    *,
    target_file: str,
    text: str,
) -> bool:
    target = repo_rel_token(target_file)
    if not target or target == ".":
        return False
    sha256 = text_hash(text)
    for item in history if isinstance(history, list) else []:
        result = history_tool_result(item)
        if (
            result.get("tool") == "planner_scratchpad_write"
            and result.get("ok") is True
            and str(result.get("mode") or "") == CODE_PRODUCT_BUILD_STATE_KIND
            and repo_rel_token(result.get("target_file") or "") == target
            and str(result.get("sha256") or "") == sha256
        ):
            return True
    return False


def code_product_build_state_from_result(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict) or result.get("ok") is not True:
        return {}
    tool = str(result.get("tool") or "")
    mode = str(result.get("mode") or "")
    if mode != CODE_PRODUCT_BUILD_STATE_KIND or tool not in {"planner_scratchpad_write", "planner_scratchpad_read"}:
        return {}
    base: dict[str, Any] = {
        "schema": CODE_PRODUCT_BUILD_STATE_SCHEMA,
        "source_tool": tool,
        "document_id": result.get("document_id"),
        "section": result.get("section"),
        "target_file": repo_rel_token(result.get("target_file") or ""),
        "status": result.get("status"),
        "sha256": result.get("sha256"),
        "complete_payload_ready": bool(result.get("complete_payload_ready")),
        "payload_loaded": False,
    }
    if tool == "planner_scratchpad_read":
        items = result.get("items") if isinstance(result.get("items"), list) else []
        if not items:
            return {}
        for item in reversed(items):
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            state = code_product_build_state_parse(str(item.get("text") or ""))
            if state:
                base.update({
                    "document_id": item.get("document_id") or base.get("document_id"),
                    "section": item.get("section") or base.get("section"),
                    "target_file": repo_rel_token(
                        metadata.get("target_file")
                        or state.get("target_file")
                        or base.get("target_file")
                        or ""
                    ),
                    "status": metadata.get("status") or state.get("status") or base.get("status"),
                    "sha256": item.get("sha256") or base.get("sha256"),
                    "window_start": item.get("window_start"),
                    "window_end": item.get("window_end"),
                    "full_chars": item.get("full_chars"),
                    "complete": item.get("complete"),
                    "has_more_after": item.get("has_more_after"),
                })
                ready_args = code_product_build_state_ready_payload(state)
                base["payload_loaded"] = True
                base["state"] = state
                base["complete_payload_ready"] = bool(ready_args)
                if ready_args:
                    base["ready_arguments"] = ready_args
                return {k: v for k, v in base.items() if v not in (None, "", [], {})}
            if item.get("has_more_after") is True:
                base.update({
                    "document_id": item.get("document_id") or base.get("document_id"),
                    "section": item.get("section") or base.get("section"),
                    "target_file": repo_rel_token(metadata.get("target_file") or base.get("target_file") or ""),
                    "status": metadata.get("status") or base.get("status"),
                    "sha256": item.get("sha256") or base.get("sha256"),
                    "window_start": item.get("window_start"),
                    "window_end": item.get("window_end"),
                    "full_chars": item.get("full_chars"),
                    "complete": item.get("complete"),
                    "has_more_after": item.get("has_more_after"),
                    "window_only": True,
                })
                return {k: v for k, v in base.items() if v not in (None, "", [], {})}
        return {}
    return {k: v for k, v in base.items() if v not in (None, "", [], {})}


def latest_code_product_build_state(
    history: list[dict[str, Any]],
    target_file: str = "",
) -> dict[str, Any]:
    target = repo_rel_token(target_file)
    for item in reversed(history if isinstance(history, list) else []):
        result = history_tool_result(item)
        state = code_product_build_state_from_result(result)
        if not state:
            continue
        state_target = repo_rel_token(state.get("target_file") or "")
        if target and target != "." and state_target and state_target != target:
            continue
        return state
    return {}


def code_product_build_state_read_action(state: dict[str, Any], target_file: str) -> dict[str, Any]:
    target = repo_rel_token(target_file or state.get("target_file") or "")
    args: dict[str, Any] = {
        "kind": CODE_PRODUCT_BUILD_STATE_KIND,
        "max_chars": 8000,
    }
    if state.get("document_id"):
        args["document_id"] = state.get("document_id")
        args["offset"] = int(state.get("window_end") or 0)
    elif target and target != ".":
        args["target_file"] = target
        args["section"] = code_product_build_state_section(target)
        args["offset"] = 0
    else:
        args["section"] = CODE_PRODUCT_BUILD_STATE_KIND
        args["offset"] = 0
    return {
        "action": "tool",
        "tool": "planner_scratchpad_read",
        "arguments": args,
        "reason": "Read the internal code_product_build_state SQLite window before proposing a code product.",
    }


def code_product_source_windows_from_reads(
    history: list[dict[str, Any]],
    target_file: str,
    *,
    same_tool_artifact_payload: ArtifactPayloadLoader,
    repo_read_item_full_content: RepoReadFullContentLoader,
    limit: int = 3,
) -> list[dict[str, Any]]:
    target = repo_rel_token(target_file)
    if not target or target == ".":
        return []
    windows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in reversed(history if isinstance(history, list) else []):
        result = history_tool_result(item)
        if result.get("tool") != "repo_read" or result.get("ok") is not True:
            continue
        source = same_tool_artifact_payload(result)
        raw_items = source.get("items") if isinstance(source.get("items"), list) else []
        if not raw_items and source.get("path"):
            raw_items = [source]
        for sub in raw_items:
            if not isinstance(sub, dict) or sub.get("ok") is False:
                continue
            path = repo_rel_token(sub.get("path") or sub.get("repo_path") or "")
            if path != target:
                continue
            text, _content_meta = repo_read_item_full_content(sub)
            if not text:
                text = str(sub.get("content") or "")
            if not text:
                continue
            digest = text_hash(text)
            if digest in seen:
                continue
            seen.add(digest)
            windows.append({
                "source_tool": "repo_read",
                "target_file": target,
                "section": f"repo_read:{target}",
                "window_start": int(sub.get("window_start") or 0),
                "window_end": int(sub.get("window_end") or len(text)),
                "full_chars": int(sub.get("full_chars") or len(text)),
                "window_chars": len(text),
                "complete": bool(sub.get("complete", sub.get("truncated") is not True)),
                "has_more_before": bool(sub.get("has_more_before", False)),
                "has_more_after": bool(sub.get("has_more_after", False)),
                "sha256": digest,
                "window_sha256": text_hash(text),
            })
            if len(windows) >= max(1, int(limit or 1)):
                return windows
    return windows


def code_product_build_state_write_action(
    target_file: str,
    history: list[dict[str, Any]] | None = None,
    *,
    same_tool_artifact_payload: ArtifactPayloadLoader,
    repo_read_item_full_content: RepoReadFullContentLoader,
) -> dict[str, Any]:
    target = repo_rel_token(target_file)
    if not target or target == ".":
        return {}
    source_windows = code_product_source_windows_from_reads(
        history or [],
        target,
        same_tool_artifact_payload=same_tool_artifact_payload,
        repo_read_item_full_content=repo_read_item_full_content,
    )
    if not source_windows:
        return {}
    state = {
        "schema": CODE_PRODUCT_BUILD_STATE_SCHEMA,
        "target_file": target,
        "status": "collecting_source",
        "source_windows": source_windows,
        "rationale": (
            "Verified repo_read source window captured. Continue by producing "
            "ready_for_propose with edit_kind=unified_diff and complete "
            "unified_diff or complete old_text/new_text, or blocked_incomplete "
            "with an explicit blocker."
        ),
    }
    state_text = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    if code_product_build_state_duplicate_write(history or [], target_file=target, text=state_text):
        return {}
    return {
        "action": "tool",
        "tool": "planner_scratchpad_write",
        "arguments": {
            "kind": CODE_PRODUCT_BUILD_STATE_KIND,
            "target_file": target,
            "status": "collecting_source",
            "section": code_product_build_state_section(target),
            "max_chars": 8000,
            "text": state_text,
        },
        "reason": (
            "Persist a valid internal code_product_build_state with real repo_read "
            "source-window progress before attempting repo_propose_code_edit."
        ),
    }


def code_product_build_state_propose_action(
    state: dict[str, Any],
    latest_violations: list[str],
) -> dict[str, Any]:
    args = state.get("ready_arguments") if isinstance(state.get("ready_arguments"), dict) else {}
    if not args:
        loaded_state = state.get("state") if isinstance(state.get("state"), dict) else {}
        args = code_product_build_state_ready_payload(loaded_state)
    if not args:
        return {}
    return {
        "action": "tool",
        "tool": "repo_propose_code_edit",
        "arguments": args,
        "reason": (
            "Use ready internal code_product_build_state to produce the required report-only code product. "
            "Current violations: " + ", ".join(latest_violations or ["missing_code_product_candidate"])
        ),
    }


def code_product_candidate_action(
    *,
    target_file: str,
    latest_violations: list[str],
    goal: str = "",
) -> dict[str, Any]:
    target = repo_rel_token(target_file)
    old_text = goal_exact_text_block(goal, "old_text")
    new_text = goal_exact_text_block(goal, "new_text")
    if not (old_text and new_text):
        return {}
    args: dict[str, Any] = {
        "target_file": target,
        "edit_kind": "unified_diff",
        "rationale": "Report-only unified diff from exact old_text/new_text supplied by the user.",
        "old_text": old_text,
        "new_text": new_text,
        "validation_commands": ["git apply --check <complete-unified-diff-from-tool-payload>"],
    }
    return {
        "action": "tool",
        "tool": "repo_propose_code_edit",
        "arguments": args,
        "reason": (
            "Code-product final is blocked until repo_propose_code_edit returns ok=true "
            f"with a complete inline payload for {target}. Current violations: "
            + ", ".join(latest_violations or ["missing_code_product_candidate"])
        ),
    }
