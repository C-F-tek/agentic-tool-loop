"""Deterministic terminal diagnostics for the agentic loop."""

from __future__ import annotations

import re
from typing import Any, Callable


EvidenceContractBuilder = Callable[[str, list[dict[str, Any]]], dict[str, Any]]
RetryCount = Callable[[list[dict[str, Any]]], int]


def agent_flow_diagnostics(
    goal: str,
    history: list[dict[str, Any]],
    planner_memory: dict[str, Any] | None = None,
    *,
    native_tools_enabled: bool,
    evidence_contract_builder: EvidenceContractBuilder,
    planner_incomprehensible_retry_count: RetryCount,
) -> dict[str, Any]:
    """Compact deterministic diagnostics for terminal artifacts."""
    history = history if isinstance(history, list) else []
    contract = evidence_contract_builder(goal, history)
    final_contract = contract.get("finalization_contract") if isinstance(contract, dict) else {}
    guard_counts: dict[str, int] = {}
    raw_previews: list[str] = []
    repeated_cache_keys: list[str] = []
    preseed_root_surface = False
    preseed_scope_surface = False
    preseed_file_surface = False
    deterministic_strip_count = 0
    native_tool_calls_seen = 0
    native_tool_call_validated = 0
    native_tool_call_repaired_by_gpu0 = 0
    native_tool_batch_executed = 0
    native_tool_batch_substeps = 0
    native_tool_batch_steps: set[Any] = set()
    vulkan_repair_attempted = 0
    memory_tool_calls = 0
    scratchpad_entries = 0
    persistent_memory_records_written = 0
    persistent_memory_cleanup_dry_run = 0
    planner_memory_false_unavailable_claims = 0

    for item in history:
        if not isinstance(item, dict):
            continue
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        if (
            result.get("tool") == "repo_tree"
            and result.get("ok")
            and bool(result.get("controller_preseed"))
            and str(result.get("path") or ".") in {"", "."}
        ):
            preseed_root_surface = True
        if result.get("tool") in {"repo_list_files", "repo_tree"} and result.get("ok") and result.get("preseed_reason") == "explicit_directory_request_needs_scope_surface":
            preseed_scope_surface = True
        if result.get("tool") == "repo_read" and result.get("ok") and result.get("preseed_reason") == "explicit_file_request_needs_file_surface":
            preseed_file_surface = True
        if decision.get("deterministic_strip"):
            deterministic_strip_count += 1
        if decision.get("native_tool_call"):
            native_tool_calls_seen += int(decision.get("native_tool_calls_seen") or 1)
            if result.get("ok") and result.get("tool") not in {None, "", "controller_guard"}:
                native_tool_call_validated += 1
        tool_name = str(result.get("tool") or decision.get("tool") or "")
        if tool_name in {
            "planner_scratchpad_read",
            "planner_scratchpad_write",
            "runtime_sqlite_memory_search",
            "runtime_sqlite_memory_write",
            "runtime_sqlite_memory_cleanup",
        }:
            memory_tool_calls += 1
        if tool_name == "planner_scratchpad_write" and result.get("ok"):
            scratchpad_entries += 1
        if tool_name == "runtime_sqlite_memory_write" and result.get("ok"):
            persistent_memory_records_written += 1
        if tool_name == "runtime_sqlite_memory_cleanup" and result.get("dry_run"):
            persistent_memory_cleanup_dry_run += 1
        raw = str(result.get("raw_planner_text_preview") or decision.get("raw_planner_text_before_deterministic_strip") or "")
        if raw.strip():
            compact_raw = re.sub(r"\s+", " ", raw).strip()[:700]
            if compact_raw and compact_raw not in raw_previews:
                raw_previews.append(compact_raw)
        if result.get("tool") == "controller_guard":
            guard_type = str(result.get("guard_type") or result.get("summary") or "unknown")
            guard_counts[guard_type] = guard_counts.get(guard_type, 0) + 1
            if guard_type == "planner_memory_false_unavailable_claim":
                planner_memory_false_unavailable_claims += 1
            cache_key = str(result.get("cache_key") or "")
            if cache_key and cache_key not in repeated_cache_keys:
                repeated_cache_keys.append(cache_key)
            repair = result.get("vulkan_repair") if isinstance(result.get("vulkan_repair"), dict) else {}
            if repair:
                vulkan_repair_attempted += 1
                if decision.get("native_tool_call") or (
                    isinstance(result.get("rejected_decision"), dict)
                    and result["rejected_decision"].get("native_tool_call")
                ):
                    native_tool_call_repaired_by_gpu0 += 1
        if isinstance(result.get("vulkan_repair"), dict):
            vulkan_repair_attempted += 1
        if decision.get("action") == "tool_batch":
            native_tool_batch_executed += 1
        if item.get("substep") not in (None, "", 0) and decision.get("reason") == "native_tool_call_batch":
            native_tool_batch_substeps += 1
            native_tool_batch_steps.add(item.get("step"))

    return {
        "planner_native_tools_enabled": bool(native_tools_enabled),
        "native_tool_calls_seen": native_tool_calls_seen,
        "native_tool_call_validated": native_tool_call_validated,
        "native_tool_call_repaired_by_gpu0": native_tool_call_repaired_by_gpu0,
        "native_tool_batch_executed": max(native_tool_batch_executed, len(native_tool_batch_steps)),
        "native_tool_batch_substeps": native_tool_batch_substeps,
        "planner_retry_required_count": guard_counts.get("planner_retry_required", 0),
        "planner_retry_streak": planner_incomprehensible_retry_count(history),
        "vulkan_repair_attempted": vulkan_repair_attempted > 0,
        "memory_tool_calls": memory_tool_calls,
        "scratchpad_entries": scratchpad_entries,
        "persistent_memory_records_written": persistent_memory_records_written,
        "persistent_memory_cleanup_dry_run": persistent_memory_cleanup_dry_run,
        "planner_memory_surface_available": bool(
            isinstance(planner_memory, dict) and planner_memory.get("available") is True
        ),
        "planner_memory_records_injected": int(
            planner_memory.get("record_count") or 0
        ) if isinstance(planner_memory, dict) else 0,
        "planner_memory_false_unavailable_claims": planner_memory_false_unavailable_claims,
        "preseed_root_surface": preseed_root_surface,
        "preseed_scope_surface": preseed_scope_surface,
        "preseed_file_surface": preseed_file_surface,
        "final_gate_blocker": final_contract.get("reason") if isinstance(final_contract, dict) else None,
        "final_allowed": bool(final_contract.get("final_allowed")) if isinstance(final_contract, dict) else False,
        "last_non_empty_raw_previews": raw_previews[-5:],
        "repeated_cache_keys": repeated_cache_keys[-10:],
        "guard_count": sum(guard_counts.values()),
        "guard_counts_by_type": guard_counts,
        "deterministic_strip_count": deterministic_strip_count,
    }
