"""Prompt required-working-set builders for planner turns."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..code_product.required_working_set import latest_code_product_for_prompt


HistoryToolResult = Callable[[dict[str, Any]], dict[str, Any]]
PathNormalizer = Callable[[Any], str]
RepoReadFullContent = Callable[[dict[str, Any]], tuple[str, dict[str, Any]]]
TextWindowBuilder = Callable[..., dict[str, Any]]
LatestBuildState = Callable[[list[dict[str, Any]], str], dict[str, Any]]
TextHash = Callable[[str], str]
GoalTargetFile = Callable[[str], str]


def repo_read_items_for_prompt(
    history: list[dict[str, Any]],
    paths: set[str],
    *,
    job_root: Path,
    goal: str,
    window_chars: int,
    compact_mode: bool,
    history_tool_result: HistoryToolResult,
    repo_rel_token: PathNormalizer,
    repo_read_item_full_content: RepoReadFullContent,
    store_prompt_text_window: TextWindowBuilder,
    window_text: TextWindowBuilder,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in reversed(history if isinstance(history, list) else []):
        result = history_tool_result(row)
        if result.get("tool") != "repo_read" or not result.get("ok"):
            continue
        for raw in result.get("items") or []:
            if not isinstance(raw, dict) or not raw.get("ok"):
                continue
            path = repo_rel_token(raw.get("path") or "")
            if not path or path in seen:
                continue
            if paths and path not in paths:
                continue
            content, content_meta = repo_read_item_full_content(raw)
            if compact_mode or len(content) > max(800, int(window_chars or 3000)):
                window = store_prompt_text_window(
                    job_root,
                    section=f"repo_read:{path}",
                    text=content,
                    query=goal,
                    max_chars=window_chars,
                    metadata={"kind": "repo_read_content", "path": path},
                )
            else:
                window = window_text(
                    content,
                    max_chars=max(800, int(window_chars or 3000)),
                )
            items.append(
                {
                    "path": path,
                    "line_count": raw.get("line_count"),
                    "truncated": raw.get("truncated"),
                    "content_source": content_meta.get("source"),
                    "full_context_reconstructed": content_meta.get("source") in {
                        "repo_file_rehydrated_for_prompt_window",
                        "repo_read_artifact_rehydrated_for_prompt",
                    },
                    "content_rehydrated_from_repo_file": content_meta.get("source") == "repo_file_rehydrated_for_prompt_window",
                    "content_source_error": content_meta.get("error"),
                    "content_window": window,
                    "planner_can_request_more": {
                        "tool": "planner_scratchpad_read",
                        "arguments": {
                            "kind": "prompt_context_window",
                            "document_id": window.get("document_id"),
                            "offset": window.get("window_end"),
                            "max_chars": window_chars,
                        },
                    } if window.get("document_id") and window.get("has_more_after") is True else None,
                    "content_chars": len(content),
                }
            )
            seen.add(path)
    items.reverse()
    return items


def required_working_set_for_prompt(
    goal: str,
    history: list[dict[str, Any]],
    contract: dict[str, Any],
    *,
    job_root: Path,
    window_chars: int,
    compact_mode: bool,
    repo_rel_token: PathNormalizer,
    goal_target_file: GoalTargetFile,
    latest_code_product_build_state: LatestBuildState,
    history_tool_result: HistoryToolResult,
    repo_read_item_full_content: RepoReadFullContent,
    store_prompt_text_window: TextWindowBuilder,
    window_text: TextWindowBuilder,
    text_hash: TextHash,
) -> dict[str, Any]:
    target_paths: set[str] = set()
    target_file = repo_rel_token(contract.get("resolved_goal_file") or goal_target_file(goal) or "")
    if target_file and target_file != ".":
        target_paths.add(target_file)
    apply_contract = contract.get("apply_write_contract") if isinstance(contract.get("apply_write_contract"), dict) else {}
    apply_targets = apply_contract.get("target_files") if isinstance(apply_contract.get("target_files"), list) else []
    for raw_target in apply_targets:
        apply_target = repo_rel_token(raw_target)
        if apply_target and apply_target != ".":
            target_paths.add(apply_target)
    code_contract = contract.get("code_product_contract") if isinstance(contract.get("code_product_contract"), dict) else {}
    latest_target = repo_rel_token(code_contract.get("latest_target_file") or "")
    if latest_target and latest_target != ".":
        target_paths.add(latest_target)
    candidate_target = repo_rel_token(code_contract.get("candidate_target_file") or "")
    if candidate_target and candidate_target != ".":
        target_paths.add(candidate_target)
    code_product_history_required = bool(
        code_contract.get("required")
        or contract.get("goal_requires_code_product_report")
        or contract.get("goal_requests_code_product")
        or latest_target
        or candidate_target
    )
    build_state = (
        latest_code_product_build_state(history, candidate_target or target_file)
        if code_product_history_required
        else {}
    )
    code_product = (
        latest_code_product_for_prompt(
            history,
            job_root=job_root,
            goal=goal,
            window_chars=window_chars,
            compact_mode=compact_mode,
            store_prompt_text_window=store_prompt_text_window,
            text_hash=text_hash,
        )
        if code_product_history_required
        else {}
    )
    required = {
        "schema": "planner_required_working_set.v1",
        "no_truncation_allowed": True,
        "context_storage": {
            "enabled": bool(compact_mode),
            "store": "job_local_sqlite",
            "recursive_window_tool": "planner_scratchpad_read",
            "window_policy": "real_text_windows_with_offsets_and_hashes",
        },
        "target_paths": sorted(target_paths),
        "repo_reads": repo_read_items_for_prompt(
            history,
            target_paths,
            job_root=job_root,
            goal=goal,
            window_chars=window_chars,
            compact_mode=compact_mode,
            history_tool_result=history_tool_result,
            repo_rel_token=repo_rel_token,
            repo_read_item_full_content=repo_read_item_full_content,
            store_prompt_text_window=store_prompt_text_window,
            window_text=window_text,
        ),
        "code_product": code_product,
        "code_product_build_state": build_state,
        "limits": [],
        "errors": [],
    }
    for item in required["repo_reads"]:
        window = item.get("content_window") if isinstance(item.get("content_window"), dict) else {}
        has_real_window_text = bool(str(window.get("text") or ""))
        if item.get("truncated") is True and item.get("full_context_reconstructed") is not True:
            row = {"path": item.get("path"), "kind": "repo_read_not_full_content", "content_source": item.get("content_source")}
            if has_real_window_text:
                required["limits"].append(row)
            else:
                required["errors"].append({"path": item.get("path"), "error": "repo_read_full_content_window_unavailable"})
        if item.get("content_source") == "content_preview_only":
            row = {"path": item.get("path"), "kind": "repo_read_content_preview_only"}
            if has_real_window_text:
                required["limits"].append(row)
            else:
                required["errors"].append({"path": item.get("path"), "error": "repo_read_full_content_missing_in_required_working_set"})
    return required
