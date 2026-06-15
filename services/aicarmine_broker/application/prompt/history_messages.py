"""Planner history message shaping for Ollama turns."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ..shared.clean_values import drop_empty_dict_values
from ..shared.history_queries import history_tool_result
from .context_windows import bounded_prompt_context_tool_result_payload
from .values import prompt_clip_text
from ..tool_surface.manifest_builder import json_char_len


OLLAMA_STREAM_META_KEYS = (
    "ollama_done_seen",
    "ollama_done_reason",
    "ollama_load_duration",
    "ollama_total_duration",
    "ollama_eval_count",
    "ollama_prompt_eval_count",
)

LOCAL_ARTIFACT_KEYS = {
    "artifact",
    "cached_from_artifact",
    "stream_path",
    "events_path",
    "final_path",
    "final_markdown_path",
}

PLANNER_HISTORY_NOISE_KEYS = {
    *LOCAL_ARTIFACT_KEYS,
    *OLLAMA_STREAM_META_KEYS,
    "cache_key",
    "repair_cache_key",
    "repair_cache_hit",
    "cached_from_step",
    "controller_preseed",
    "preseed_index",
    "dynamic_initial_orientation",
    "duration",
    "duration_ms",
    "elapsed",
    "elapsed_ms",
    "started_at",
    "finished_at",
    "created_at",
    "updated_at",
    "events",
    "raw_events",
}

StorePromptTextWindow = Callable[..., dict[str, Any]]


def planner_history_summary(value: Any) -> str:
    text = str(value or "").strip()
    for marker in (
        " artifact=",
        " cached_from_artifact=",
        " stream_path=",
        " events_path=",
        " final_path=",
    ):
        if marker in text:
            text = text.split(marker, 1)[0].strip()
    return prompt_clip_text(text, 700)


def clean_planner_history_value(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in PLANNER_HISTORY_NOISE_KEYS:
                continue
            if key_text == "store" and str(item).lower() in {"job_local_sqlite", "sqlite", "local_path"}:
                continue
            if key_text == "summary":
                cleaned_summary = planner_history_summary(item)
                if cleaned_summary:
                    out[key_text] = cleaned_summary
                continue
            out[key_text] = clean_planner_history_value(item)
        return drop_empty_dict_values(out)
    if isinstance(value, list):
        return [
            cleaned
            for item in value
            if (cleaned := clean_planner_history_value(item)) not in (None, "", [], {})
        ]
    return value


def planner_history_arguments(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
    arguments = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
    if arguments:
        return drop_empty_dict_values(clean_planner_history_value(arguments))
    derived: dict[str, Any] = {}
    for key in (
        "path",
        "paths",
        "query",
        "target_file",
        "edit_kind",
        "kind",
        "mode",
        "line",
        "before",
        "after",
        "max_chars",
        "limit",
        "max_depth",
        "suffix",
        "document_id",
        "offset",
    ):
        if result.get(key) not in (None, "", [], {}):
            derived[key] = result.get(key)
    return drop_empty_dict_values(clean_planner_history_value(derived))


def planner_history_reason(item: dict[str, Any], result: dict[str, Any]) -> str:
    decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
    for value in (
        decision.get("reason"),
        result.get("preseed_reason"),
        result.get("summary"),
    ):
        reason = planner_history_summary(value)
        if reason:
            return reason
    return ""


def planner_controller_guard_history_payload(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    contract = result.get("evidence_contract") if isinstance(result.get("evidence_contract"), dict) else {}
    if not contract:
        contract = (
            result.get("evidence_contract_summary")
            if isinstance(result.get("evidence_contract_summary"), dict)
            else {}
        )
    rejected = result.get("rejected_decision") if isinstance(result.get("rejected_decision"), dict) else {}
    operational = contract.get("operational_notes") if isinstance(contract.get("operational_notes"), dict) else {}
    coverage = contract.get("minimum_read_coverage") if isinstance(contract.get("minimum_read_coverage"), dict) else {}
    content = rejected.get("content")
    payload: dict[str, Any] = {
        "schema": "planner_controller_guard_history.v1",
        "step": item.get("step"),
        "substep": item.get("substep"),
        "guard_label": "controller_guard",
        "ok": result.get("ok"),
        "guard_type": result.get("guard_type"),
        "violations": result.get("violations"),
        "summary": planner_history_summary(result.get("summary")),
        "rejected_action": rejected.get("action"),
        "rejected_final_answer_source": rejected.get("final_answer_source"),
        "rejected_content_keys": list(content.keys()) if isinstance(content, dict) else None,
        "required_next_progress": contract.get("required_next_progress"),
        "planner_may_choose_final": contract.get("planner_may_choose_final"),
        "coverage_satisfied": contract.get("coverage_satisfied"),
        "missing_owner_paths": contract.get("missing_owner_paths"),
        "covered_owner_paths": contract.get("covered_owner_paths"),
        "minimum_read_coverage": {
            "required": coverage.get("required"),
            "coverage_satisfied": coverage.get("coverage_satisfied"),
            "target_kind": coverage.get("target_kind"),
            "required_count": coverage.get("required_count"),
            "covered_count": coverage.get("covered_count"),
            "missing_owner_paths": coverage.get("missing_owner_paths"),
            "covered_owner_paths": coverage.get("covered_owner_paths"),
            "reason": coverage.get("reason"),
        } if coverage else None,
        "next_instruction": result.get("next_instruction") or operational.get("next_instruction"),
        "successful_repo_read_count": contract.get("successful_repo_read_count"),
        "verified_content_read_count": contract.get("verified_content_read_count"),
    }
    return drop_empty_dict_values(clean_planner_history_value(payload))


def planner_repo_read_history_payload(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    items = result.get("items") if isinstance(result.get("items"), list) else []
    successful_items = [
        row
        for row in items
        if isinstance(row, dict) and row.get("ok") and row.get("path") not in (None, "")
    ]
    read_items = [
        drop_empty_dict_values(
            {
                "path": row.get("path"),
                "line_count": row.get("line_count"),
                "truncated": row.get("truncated"),
            }
        )
        for row in successful_items[:80]
    ]
    payload: dict[str, Any] = {
        "schema": "planner_repo_read_history_digest.v1",
        "step": item.get("step"),
        "substep": item.get("substep"),
        "tool": "repo_read",
        "ok": result.get("ok"),
        "reason": planner_history_reason(item, result),
        "arguments": planner_history_arguments(item, result),
        "count": result.get("count", len(items)),
        "success_count": result.get("success_count", len(successful_items)),
        "failed_count": result.get("failed_count"),
        "read_items": read_items,
        "content_transport": {
            "full_content_not_repeated_in_history": True,
            "primary_context": "required_working_set.repo_reads",
            "history_contains_path_listing_only": True,
            "planner_can_use_required_working_set_or_read_selectively": True,
            "artifact_payload_available": bool(result.get("artifact")),
        },
    }
    return drop_empty_dict_values(payload)


def planner_history_evidence_payload(item: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    tool = str(result.get("tool") or (item.get("decision") or {}).get("tool") or "")
    payload: dict[str, Any] = {
        "schema": "planner_tool_history_evidence.v1",
        "step": item.get("step"),
        "substep": item.get("substep"),
        "tool": tool,
        "reason": planner_history_reason(item, result),
        "arguments": planner_history_arguments(item, result),
        "result": clean_planner_history_value(result),
    }
    return drop_empty_dict_values(payload)


def planner_tool_result_message_payload(
    item: dict[str, Any],
    result: dict[str, Any],
    *,
    root: Path,
    goal: str,
    window_chars: int,
    code_product_build_state_kind: str,
    store_prompt_text_window: StorePromptTextWindow,
) -> dict[str, Any]:
    tool = str(result.get("tool") or (item.get("decision") or {}).get("tool") or "")
    direct_payload = bounded_prompt_context_tool_result_payload(
        result,
        code_product_build_state_kind=code_product_build_state_kind,
    )
    if direct_payload:
        direct_payload["step"] = item.get("step")
        if item.get("substep") not in (None, "", [], {}):
            direct_payload["substep"] = item.get("substep")
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        if isinstance(decision.get("arguments"), dict):
            direct_payload["arguments"] = decision.get("arguments")
        return direct_payload
    if tool == "repo_read":
        return planner_repo_read_history_payload(item, result)
    if tool == "controller_guard":
        return planner_controller_guard_history_payload(item, result)
    raw_payload = planner_history_evidence_payload(item, result)
    raw_text = json.dumps(raw_payload, ensure_ascii=False, indent=2, default=str)
    if len(raw_text) <= max(1200, int(window_chars or 0)):
        return raw_payload
    window = store_prompt_text_window(
        root,
        section=f"message_tool_result:{item.get('step')}:{tool}",
        text=raw_text,
        query=goal,
        max_chars=window_chars,
        metadata={
            "kind": "planner_message_tool_result_payload",
            "step": item.get("step"),
            "substep": item.get("substep"),
            "tool": tool,
            "format": "json",
        },
    )
    payload: dict[str, Any] = {
        "schema": "planner_tool_history_window.v1",
        "step": item.get("step"),
        "substep": item.get("substep"),
        "tool": tool,
        "reason": raw_payload.get("reason"),
        "arguments": raw_payload.get("arguments"),
        "result_window": window,
    }
    if window.get("document_id") and window.get("has_more_after") is True:
        payload["planner_can_request_more"] = {
            "tool": "planner_scratchpad_read",
            "arguments": {
                "kind": "prompt_context_window",
                "document_id": window.get("document_id"),
                "offset": window.get("window_end"),
                "max_chars": window_chars,
            },
        }
    return drop_empty_dict_values(payload)


def planner_history_item_messages(
    item: dict[str, Any],
    *,
    root: Path,
    goal: str,
    window_chars: int,
    code_product_build_state_kind: str,
    store_prompt_text_window: StorePromptTextWindow,
) -> list[dict[str, Any]]:
    if not isinstance(item, dict):
        return []
    decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
    result = history_tool_result(item)
    messages: list[dict[str, Any]] = []
    if (
        decision.get("native_tool_call") is True
        and isinstance(decision.get("raw_native_tool_call"), dict)
    ):
        raw_native_call = decision["raw_native_tool_call"]
        raw_tool_name = str((raw_native_call.get("function") or {}).get("name") or "").lower()
        result_tool_name = str(result.get("tool") if isinstance(result, dict) else "").lower()
        is_controller_guard = result_tool_name == "controller_guard" or raw_tool_name == "controller_guard"
        if is_controller_guard:
            payload = planner_tool_result_message_payload(
                item,
                result,
                root=root,
                goal=goal,
                window_chars=window_chars,
                code_product_build_state_kind=code_product_build_state_kind,
                store_prompt_text_window=store_prompt_text_window,
            )
            messages.append({
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            })
            return messages
        messages.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [raw_native_call],
        })
        if result:
            tool_message = {
                "role": "tool",
                "tool_name": str(result.get("tool") or decision.get("tool") or ""),
                "content": json.dumps(
                    planner_tool_result_message_payload(
                        item,
                        result,
                        root=root,
                        goal=goal,
                        window_chars=window_chars,
                        code_product_build_state_kind=code_product_build_state_kind,
                        store_prompt_text_window=store_prompt_text_window,
                    ),
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
            }
            if raw_native_call.get("id"):
                tool_message["tool_call_id"] = raw_native_call.get("id")
            messages.append(tool_message)
        return messages
    if result:
        payload = planner_tool_result_message_payload(
            item,
            result,
            root=root,
            goal=goal,
            window_chars=window_chars,
            code_product_build_state_kind=code_product_build_state_kind,
            store_prompt_text_window=store_prompt_text_window,
        )
        messages.append({
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        })
    return messages


def planner_history_messages_for_ollama(
    history: list[dict[str, Any]],
    *,
    root: Path,
    goal: str,
    window_chars: int,
    max_chars: int,
    native_tools_enabled: bool,
    code_product_build_state_kind: str,
    store_prompt_text_window: StorePromptTextWindow,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    history_items = history if isinstance(history, list) else []
    if max_chars <= 0:
        return [], {
            "schema": "planner_history_messages.v1",
            "enabled": bool(native_tools_enabled),
            "included_history_items": 0,
            "skipped_history_items": len(history_items),
            "considered_history_items": len(history_items),
            "transportable_history_items": 0,
            "empty_history_items": 0,
            "oversized_history_items": 0,
            "candidate_message_chars": 0,
            "message_chars": 0,
            "max_chars": max_chars,
        }
    selected_reversed: list[list[dict[str, Any]]] = []
    total_chars = 0
    included = 0
    skipped = 0
    empty = 0
    oversized = 0
    transportable = 0
    candidate_message_chars = 0
    for item in reversed(history_items):
        item_messages = planner_history_item_messages(
            item,
            root=root,
            goal=goal,
            window_chars=window_chars,
            code_product_build_state_kind=code_product_build_state_kind,
            store_prompt_text_window=store_prompt_text_window,
        )
        if not item_messages:
            empty += 1
            continue
        transportable += 1
        item_chars = json_char_len(item_messages)
        candidate_message_chars += item_chars
        if selected_reversed and total_chars + item_chars > max_chars:
            skipped += 1
            oversized += 1
            continue
        if total_chars + item_chars > max_chars:
            skipped += 1
            oversized += 1
            continue
        selected_reversed.append(item_messages)
        total_chars += item_chars
        included += 1
    messages: list[dict[str, Any]] = []
    for group in reversed(selected_reversed):
        messages.extend(group)
    return messages, {
        "schema": "planner_history_messages.v1",
        "enabled": bool(native_tools_enabled),
        "included_history_items": included,
        "skipped_history_items": skipped,
        "considered_history_items": len(history_items),
        "transportable_history_items": transportable,
        "empty_history_items": empty,
        "oversized_history_items": oversized,
        "candidate_message_chars": candidate_message_chars,
        "omitted_history_items": max(0, transportable - included),
        "message_count": len(messages),
        "message_chars": json_char_len(messages),
        "max_chars": max_chars,
        "window_chars": window_chars,
    }
