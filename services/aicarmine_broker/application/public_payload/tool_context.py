"""OpenWebUI-visible tool context shaping for terminal planner results."""
from __future__ import annotations

from typing import Any, Callable

from ..shared.clean_values import drop_empty_dict_values
from ..shared.history_ledger import history_item_ollama_turn, planner_ollama_turn_from_decision
from ..shared.history_queries import history_tool_result
from ..prompt.history_messages import LOCAL_ARTIFACT_KEYS


PUBLIC_LOCAL_REFERENCE_KEYS = {
    "cached_from_artifact",
    "stream_path",
    "events_path",
    "error_path",
    "final_path",
    "final_markdown_path",
    "db",
    "workspace",
    "operator_error_path",
    "document_id",
    "final_json",
    "final_markdown",
    "events_ndjson",
    "planner_stream",
}

ArtifactPayloadLoader = Callable[[dict[str, Any]], dict[str, Any]]
RepoReadContentLoader = Callable[[dict[str, Any]], tuple[str, dict[str, Any]]]


def decision_for_turn_memory(decision: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(decision, dict):
        return {}
    return drop_empty_dict_values({
        "action": decision.get("action"),
        "tool": decision.get("tool"),
        "arguments": decision.get("arguments") if isinstance(decision.get("arguments"), dict) else None,
        "reason": decision.get("reason"),
        "final_answer": decision.get("final_answer"),
        "native_tool_call": decision.get("native_tool_call"),
        "native_tool_calls_seen": decision.get("native_tool_calls_seen"),
    })


def strip_public_artifact_paths(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): strip_public_artifact_paths(v)
            for k, v in value.items()
            if str(k) not in LOCAL_ARTIFACT_KEYS
        }
    if isinstance(value, list):
        return [strip_public_artifact_paths(item) for item in value]
    return value


def strip_public_local_references(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text == "artifact" and isinstance(item, str):
                continue
            if key_text in PUBLIC_LOCAL_REFERENCE_KEYS:
                continue
            if key_text == "store" and str(item).lower() in {"job_local_sqlite", "sqlite", "local_path"}:
                continue
            out[key_text] = strip_public_local_references(item)
        return out
    if isinstance(value, list):
        return [strip_public_local_references(item) for item in value]
    return value


def public_tool_response(
    tool_result: dict[str, Any],
    *,
    same_tool_artifact_payload: ArtifactPayloadLoader,
    repo_read_item_full_content: RepoReadContentLoader,
    code_product_build_state_kind: str,
) -> dict[str, Any]:
    if not isinstance(tool_result, dict) or not tool_result.get("ok"):
        return {}
    source = same_tool_artifact_payload(tool_result)
    tool = str(source.get("tool") or tool_result.get("tool") or "")
    if (
        tool in {"planner_scratchpad_read", "planner_scratchpad_write"}
        and str(source.get("mode") or tool_result.get("mode") or "") == code_product_build_state_kind
    ):
        return {}

    if tool == "repo_read":
        items: list[dict[str, Any]] = []
        for read_item in source.get("items") or []:
            if not isinstance(read_item, dict) or not read_item.get("ok"):
                continue
            content, _content_meta = repo_read_item_full_content(read_item)
            if content in (None, ""):
                content = read_item.get("content")
            if content is None:
                content = read_item.get("content_view") or read_item.get("content_preview")
            items.append(drop_empty_dict_values({
                "repo_path": read_item.get("path"),
                "size_bytes": read_item.get("size_bytes"),
                "line_count": read_item.get("line_count"),
                "truncated": False if content else read_item.get("truncated"),
                "content": content,
            }))
        return drop_empty_dict_values({
            "tool": tool,
            "ok": True,
            "count": len(items),
            "requested_count": source.get("requested_count"),
            "success_count": len(items),
            "max_paths": source.get("max_paths"),
            "items": items,
        })

    if tool == "repo_propose_code_edit":
        response: dict[str, Any] = {
            "tool": tool,
            "ok": source.get("ok"),
            "kind": source.get("kind"),
            "target_file": source.get("target_file"),
            "edit_kind": source.get("edit_kind"),
            "rationale": source.get("rationale"),
            "source_writes_performed": source.get("source_writes_performed"),
            "patch_application_performed": source.get("patch_application_performed"),
            "manual_review_required": source.get("manual_review_required"),
            "validation_commands": source.get("validation_commands"),
            "errors": source.get("errors"),
            "warnings": source.get("warnings"),
            "target_metadata": source.get("target_metadata"),
            "ast_evidence": source.get("ast_evidence"),
        }
        if source.get("edit_kind") == "unified_diff":
            response["unified_diff"] = source.get("unified_diff")
        if source.get("edit_kind") == "structured_edit":
            response["structured_operations"] = source.get("structured_operations")
        return drop_empty_dict_values(response)

    if tool == "repo_tree":
        entries = source.get("entries") if isinstance(source.get("entries"), list) else []
        return drop_empty_dict_values({
            "tool": tool,
            "ok": True,
            "repo_path": source.get("path"),
            "count": source.get("count", len(entries)),
            "entries_total": source.get("entries_total") or source.get("count") or len(entries),
            "truncated": source.get("truncated"),
            "entries": strip_public_artifact_paths(entries),
        })

    if tool == "repo_list_files":
        paths = source.get("paths") if isinstance(source.get("paths"), list) else []
        return drop_empty_dict_values({
            "tool": tool,
            "ok": True,
            "repo_path": source.get("path"),
            "suffix": source.get("suffix"),
            "count": source.get("count", len(paths)),
            "total_matches": source.get("total_matches"),
            "limit": source.get("limit"),
            "truncated": source.get("truncated"),
            "paths": paths,
            "files": strip_public_artifact_paths(source.get("files"))
            if isinstance(source.get("files"), list) else None,
        })

    if tool in {"repo_command", "terminal_run_command_wait"}:
        return drop_empty_dict_values({
            "tool": tool,
            "ok": source.get("ok"),
            "command": source.get("command"),
            "returncode": source.get("returncode"),
            "stdout": source.get("stdout") or source.get("stdout_text"),
            "stderr": source.get("stderr") or source.get("stderr_text"),
            "stdout_tail": source.get("stdout_tail"),
            "stderr_tail": source.get("stderr_tail"),
        })

    useful: dict[str, Any] = {"tool": tool, "ok": source.get("ok")}
    for key in (
        "summary", "content", "text", "message", "result", "items",
        "matches", "files", "paths", "count", "total_matches", "limit",
        "truncated", "returncode", "stdout", "stderr", "stdout_text",
        "stderr_text", "stdout_tail", "stderr_tail", "diagnostics",
        "diagnostics_total", "anchors", "anchors_total", "symbols",
        "symbols_total", "comments", "parsed_json", "file_count",
        "results", "results_total", "errors", "warnings", "stderr_tail",
    ):
        if source.get(key) not in (None, "", [], {}):
            useful[key] = strip_public_artifact_paths(source.get(key))
    return drop_empty_dict_values(useful)


def successful_tool_turns(
    history: list[dict[str, Any]],
    *,
    same_tool_artifact_payload: ArtifactPayloadLoader,
    repo_read_item_full_content: RepoReadContentLoader,
    code_product_build_state_kind: str,
) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    for item in history if isinstance(history, list) else []:
        if not isinstance(item, dict):
            continue
        result = history_tool_result(item)
        tool = str(result.get("tool") or "")
        if not tool or tool == "controller_guard" or not result.get("ok"):
            continue
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        response = public_tool_response(
            result,
            same_tool_artifact_payload=same_tool_artifact_payload,
            repo_read_item_full_content=repo_read_item_full_content,
            code_product_build_state_kind=code_product_build_state_kind,
        )
        if not response:
            continue
        turns.append(drop_empty_dict_values({
            "step": item.get("step"),
            "substep": item.get("substep"),
            "producer": "controller_preseed"
            if str(decision.get("action") or "") == "controller_preseed"
            else "planner",
            "ollama_done_reason": history_item_ollama_turn(item).get("done_reason"),
            "ollama_turn": history_item_ollama_turn(item),
            "tool_call": decision_for_turn_memory(decision),
            "tool_response": response,
        }))
    return turns


def public_tool_artifact_rows(
    history: list[dict[str, Any]],
    *,
    same_tool_artifact_payload: ArtifactPayloadLoader,
    repo_read_item_full_content: RepoReadContentLoader,
    code_product_build_state_kind: str,
) -> list[dict[str, Any]]:
    """Return OpenWebUI-visible artifacts with real payloads, never local paths."""
    rows: list[dict[str, Any]] = []
    for item in history if isinstance(history, list) else []:
        if not isinstance(item, dict):
            continue
        result = history_tool_result(item)
        tool = str(result.get("tool") or "")
        if not tool or tool == "controller_guard" or not result.get("ok"):
            continue
        response = public_tool_response(
            result,
            same_tool_artifact_payload=same_tool_artifact_payload,
            repo_read_item_full_content=repo_read_item_full_content,
            code_product_build_state_kind=code_product_build_state_kind,
        )
        if not response:
            continue
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        arguments = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
        base = {
            "producer_step": item.get("step"),
            "substep": item.get("substep"),
            "tool": tool,
            "arguments": arguments,
            "ok": True,
        }
        if tool == "repo_read":
            for read_item in response.get("items") or []:
                if not isinstance(read_item, dict):
                    continue
                artifact = {"kind": "repo_read", **strip_public_artifact_paths(read_item)}
                rows.append(drop_empty_dict_values({**base, "artifact": artifact}))
            continue
        artifact_payload = {
            k: v for k, v in response.items()
            if k not in {"tool", "ok"} and v not in (None, "", [], {})
        }
        artifact_payload = strip_public_artifact_paths(artifact_payload)
        if tool == "repo_propose_code_edit":
            artifact = {"kind": "code_edit_proposal", **artifact_payload}
        elif tool in {"repo_unidiff_validate", "repo_git_apply_check"}:
            artifact = {"kind": "diff_validation", **artifact_payload}
        elif tool in {"repo_ruff_check", "repo_pyright_check", "repo_pytest_run", "repo_shellcheck", "repo_semgrep_scan"}:
            artifact = {"kind": "validation_result", **artifact_payload}
        elif tool in {"repo_ast_grep_search", "repo_ast_grep_dry_run", "repo_tree_sitter_parse", "repo_ctags_symbols"}:
            artifact = {"kind": "structural_evidence", **artifact_payload}
        elif tool in {"repo_fd_files", "repo_rg_search", "repo_jq_query"}:
            artifact = {"kind": "deterministic_repo_evidence", **artifact_payload}
        elif tool == "repo_tree":
            artifact = {"kind": "repo_tree", **artifact_payload}
        elif tool == "repo_list_files":
            artifact = {"kind": "repo_list_files", **artifact_payload}
        elif tool in {"repo_command", "terminal_run_command_wait"}:
            artifact = {"kind": "command_result", **artifact_payload}
        else:
            artifact = {"kind": artifact_payload.get("kind") or "tool_result", **artifact_payload}
        rows.append(drop_empty_dict_values({**base, "artifact": artifact}))
    return rows


def public_tool_context_limits(artifact_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    limits: list[dict[str, Any]] = []
    for row in artifact_rows if isinstance(artifact_rows, list) else []:
        if not isinstance(row, dict):
            continue
        artifact = row.get("artifact") if isinstance(row.get("artifact"), dict) else {}
        if not artifact:
            continue
        base = {
            "step": row.get("producer_step"),
            "tool": row.get("tool"),
            "path": artifact.get("repo_path") or artifact.get("target_file"),
        }
        if artifact.get("truncated") is True:
            limits.append(drop_empty_dict_values({**base, "kind": "truncated"}))
        if artifact.get("preview_only") is True:
            limits.append(drop_empty_dict_values({**base, "kind": "preview_only"}))
        total = artifact.get("total_matches") or artifact.get("entries_total")
        visible = artifact.get("count")
        try:
            if total not in (None, "") and visible not in (None, "") and int(total) > int(visible):
                limits.append(drop_empty_dict_values({
                    **base,
                    "kind": "partial_list",
                    "visible": visible,
                    "total": total,
                }))
        except Exception:
            pass
    return limits


def ollama_turn_rows(
    history: list[dict[str, Any]],
    terminal_decision: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, str, str]] = set()
    for item in history if isinstance(history, list) else []:
        if not isinstance(item, dict):
            continue
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        result = history_tool_result(item)
        turn = history_item_ollama_turn(item)
        if not turn:
            continue
        row = drop_empty_dict_values({
            "step": item.get("step"),
            "done_reason": turn.get("done_reason"),
            "done_seen": turn.get("done_seen"),
            "action": decision.get("action"),
            "tool": decision.get("tool") or result.get("tool"),
            "tool_ok": result.get("ok") if result.get("tool") != "controller_guard" else None,
            "guard_type": result.get("guard_type"),
        })
        key = (row.get("step"), str(row.get("action") or ""), str(row.get("tool") or ""))
        if key not in seen:
            seen.add(key)
            rows.append(row)
    if isinstance(terminal_decision, dict):
        turn = planner_ollama_turn_from_decision(terminal_decision, step=terminal_decision.get("step"))
        if turn:
            row = drop_empty_dict_values({
                "step": terminal_decision.get("step"),
                "done_reason": turn.get("done_reason"),
                "done_seen": turn.get("done_seen"),
                "action": terminal_decision.get("action"),
                "tool": terminal_decision.get("tool"),
                "terminal": True,
            })
            key = (row.get("step"), str(row.get("action") or ""), str(row.get("tool") or ""))
            if key not in seen:
                rows.append(row)
    return rows


def planner_turn_memory(
    history: list[dict[str, Any]],
    terminal_decision: dict[str, Any] | None = None,
    *,
    same_tool_artifact_payload: ArtifactPayloadLoader,
    repo_read_item_full_content: RepoReadContentLoader,
    code_product_build_state_kind: str,
) -> dict[str, Any]:
    return drop_empty_dict_values({
        "contract": (
            "Ollama done_reason closes one planner response turn only; "
            "3572 validator/finalization still decides job status."
        ),
        "ollama_turns": ollama_turn_rows(history, terminal_decision),
        "successful_tool_turns": successful_tool_turns(
            history,
            same_tool_artifact_payload=same_tool_artifact_payload,
            repo_read_item_full_content=repo_read_item_full_content,
            code_product_build_state_kind=code_product_build_state_kind,
        ),
    })


def ollama_turn_summary_text(
    history: list[dict[str, Any]],
    terminal_decision: dict[str, Any] | None = None,
) -> str:
    rows = ollama_turn_rows(history, terminal_decision)
    if not rows:
        return ""
    lines = ["Turni Ollama conclusi:"]
    for row in rows:
        line = f"- step={row.get('step')} done_reason={row.get('done_reason')}"
        if row.get("action"):
            line += f" action={row.get('action')}"
        if row.get("tool"):
            line += f" tool={row.get('tool')}"
        if row.get("tool_ok") is not None:
            line += f" tool_ok={row.get('tool_ok')}"
        if row.get("guard_type"):
            line += f" guard_type={row.get('guard_type')}"
        if row.get("terminal"):
            line += " terminal=true"
        lines.append(line)
    return "\n".join(lines)


def final_summary_with_ollama_done_reasons(
    status: str,
    final_summary: str,
    result: dict[str, Any],
) -> str:
    summary = str(final_summary or "").strip() or "Job terminale senza final_summary."
    if "Turni Ollama conclusi:" in summary:
        return summary
    history = result.get("history") if isinstance(result.get("history"), list) else []
    terminal_decision = result.get("planner_decision") if isinstance(result.get("planner_decision"), dict) else {}
    turn_text = ollama_turn_summary_text(history, terminal_decision)
    if not turn_text:
        return summary
    suffix = turn_text
    if str(status or "") == "max_steps_reached":
        suffix += (
            "\nNota stato: i done_reason chiudono i turni Ollama; "
            "non equivalgono a completed senza final accettato dal validator 3572."
        )
    return summary + "\n\n" + suffix
