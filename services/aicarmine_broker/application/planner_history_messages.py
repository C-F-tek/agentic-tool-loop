"""Planner history message shaping for Ollama turns."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .clean_values import drop_empty_dict_values
from .history_queries import history_tool_result
from .prompt_context_windows import bounded_prompt_context_tool_result_payload
from .prompt_values import prompt_clip_text
from .tool_manifest_builder import json_char_len


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
    rejected = result.get("rejected_decision") if isinstance(result.get("rejected_decision"), dict) else {}
    operational = contract.get("operational_notes") if isinstance(contract.get("operational_notes"), dict) else {}
    content = rejected.get("content")
    payload: dict[str, Any] = {
        "schema": "planner_controller_guard_history.v1",
        "step": item.get("step"),
        "substep": item.get("substep"),
        "tool": "controller_guard",
        "ok": result.get("ok"),
        "guard_type": result.get("guard_type"),
        "violations": result.get("violations"),
        "summary": planner_history_summary(result.get("summary")),
        "rejected_action": rejected.get("action"),
        "rejected_final_answer_source": rejected.get("final_answer_source"),
        "rejected_content_keys": list(content.keys()) if isinstance(content, dict) else None,
        "required_next_progress": contract.get("required_next_progress"),
        "planner_may_choose_final": contract.get("planner_may_choose_final"),
        "next_instruction": result.get("next_instruction") or operational.get("next_instruction"),
        "successful_repo_read_count": contract.get("successful_repo_read_count"),
        "verified_content_read_count": contract.get("verified_content_read_count"),
    }
    return drop_empty_dict_values(clean_planner_history_value(payload))


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
    if max_chars <= 0:
        return [], {
            "schema": "planner_history_messages.v1",
            "enabled": bool(native_tools_enabled),
            "included_history_items": 0,
            "skipped_history_items": len(history if isinstance(history, list) else []),
            "message_chars": 0,
            "max_chars": max_chars,
        }
    selected_reversed: list[list[dict[str, Any]]] = []
    total_chars = 0
    included = 0
    skipped = 0
    for item in reversed(history if isinstance(history, list) else []):
        item_messages = planner_history_item_messages(
            item,
            root=root,
            goal=goal,
            window_chars=window_chars,
            code_product_build_state_kind=code_product_build_state_kind,
            store_prompt_text_window=store_prompt_text_window,
        )
        if not item_messages:
            continue
        item_chars = json_char_len(item_messages)
        if selected_reversed and total_chars + item_chars > max_chars:
            skipped += 1
            continue
        if total_chars + item_chars > max_chars:
            skipped += 1
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
        "message_count": len(messages),
        "message_chars": json_char_len(messages),
        "max_chars": max_chars,
        "window_chars": window_chars,
    }
