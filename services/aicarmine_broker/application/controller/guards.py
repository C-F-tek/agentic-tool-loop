"""Controller guard and rejection signature helpers."""
from __future__ import annotations

import json
from typing import Any, Callable

from ...tool_contract import normalize_tool_name
from ..shared.history_queries import history_tool_result


SignatureKey = Callable[[dict[str, Any]], str]

SUPPORT_SUBTURN_TOOLS = frozenset({
    "planner_scratchpad_read",
    "planner_scratchpad_write",
    "runtime_sqlite_memory_search",
    "runtime_sqlite_memory_write",
})


def controller_guard_count(history: list[dict[str, Any]], kind: str) -> int:
    wanted = str(kind or "").lower()
    count = 0
    for item in history:
        if not isinstance(item, dict):
            continue
        result = history_tool_result(item)
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
        if result.get("tool") != "controller_guard":
            continue
        combined = " ".join(
            str(x or "") for x in (result.get("summary"), decision.get("reason"))
        ).lower()
        if wanted and wanted in combined:
            count += 1
    return count


def _stable_support_subturn_arguments(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    stable: dict[str, Any] = {}
    for key in (
        "kind",
        "mode",
        "tag",
        "section",
        "document_id",
        "target_file",
        "path",
        "offset",
        "max_chars",
        "query",
    ):
        value = args.get(key)
        if value not in (None, "", [], {}):
            stable[key] = value
    if tool == "planner_scratchpad_write":
        text = args.get("text") or args.get("content")
        if str(stable.get("kind") or "").strip() == "code_product_build_state" and isinstance(text, str):
            try:
                payload = json.loads(text)
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                for key in ("target_file", "status"):
                    value = payload.get(key)
                    if value not in (None, "", [], {}) and key not in stable:
                        stable[key] = value
    return stable


def controller_guard_rejection_signature(validation: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    violations = validation.get("violations") if isinstance(validation.get("violations"), list) else []
    tool = normalize_tool_name(str(decision.get("tool") or ""))
    rejected = {
        k: decision.get(k)
        for k in ("action", "tool", "arguments")
        if decision.get(k) not in (None, "", [], {})
    }
    if tool in SUPPORT_SUBTURN_TOOLS:
        args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
        rejected = {
            "action": str(decision.get("action") or "tool"),
            "tool": tool,
        }
        stable_args = _stable_support_subturn_arguments(tool, args)
        if stable_args:
            rejected["arguments"] = stable_args
    return {
        "violations": [str(v) for v in violations],
        "rejected_decision": rejected,
    }


def controller_guard_rejection_signature_count(
    history: list[dict[str, Any]],
    signature: dict[str, Any],
    *,
    invalid_decision_signature_key: SignatureKey,
) -> int:
    key = invalid_decision_signature_key(signature)
    if not key:
        return 0
    count = 0
    for item in history if isinstance(history, list) else []:
        result = history_tool_result(item)
        if result.get("tool") != "controller_guard":
            continue
        existing = result.get("invalid_decision_signature")
        if not isinstance(existing, dict) or not existing:
            existing = controller_guard_rejection_signature(
                {"violations": result.get("violations") if isinstance(result.get("violations"), list) else []},
                result.get("rejected_decision") if isinstance(result.get("rejected_decision"), dict) else {},
            )
        if invalid_decision_signature_key(existing) == key:
            count += 1
    return count


def recoverable_planner_block(decision: dict[str, Any]) -> bool:
    combined = " ".join(
        str(decision.get(k) or "").lower()
        for k in ("reason", "final_answer", "raw_planner_text", "raw_planner_text_preview")
    )
    markers = (
        "planner stream degenerate output", "planner forced stream degenerate output",
        "planner emitted non-repairable non-json output", "no_json_object_candidate",
        "dead_or_stop_token_output", "role_boundary_marker", "role-boundary",
        ".readbyte",
    )
    return any(marker in combined for marker in markers)


# ---------------------------------------------------------------------------
# Replay rules: guide planner away from repeated reads
# ---------------------------------------------------------------------------

def _detect_repeated_read_loop(history: list[dict[str, Any]], tool: str = "repo_read") -> dict[str, Any]:
    """Detect when the planner is stuck in a loop of repeated repo_read calls.

    Returns a dict with:
    - detected: bool
    - repeated_paths: list[str]
    - repeated_count: int
    - guidance: str
    """
    if not isinstance(history, list):
        return {"detected": False, "repeated_paths": [], "repeated_count": 0, "guidance": ""}

    # Collect successful repo_read calls with their paths
    successful_reads: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        result = history_tool_result(item)
        if result.get("tool") != tool or result.get("ok") is not True:
            continue
        successful_reads.append(result)

    if len(successful_reads) < 3:
        return {"detected": False, "repeated_paths": [], "repeated_count": 0, "guidance": ""}

    # Extract paths from successful reads
    path_counts: dict[str, int] = {}
    for read_result in successful_reads:
        path = str(read_result.get("path") or read_result.get("repo_path") or "")
        if path:
            path_counts[path] = path_counts.get(path, 0) + 1

    # Check for paths read multiple times
    repeated_paths = [path for path, count in path_counts.items() if count >= 2]
    if not repeated_paths:
        return {"detected": False, "repeated_paths": [], "repeated_count": 0, "guidance": ""}

    total_repeats = sum(count for path, count in path_counts.items() if count >= 2)
    guidance = (
        f"Planner is stuck in a read loop: {len(repeated_paths)} path(s) read {total_repeats}+ times total. "
        f"Repeated paths: {', '.join(repeated_paths[:5])}. "
        f"Do NOT call repo_read again for these paths. "
        f"Choose one of: (1) final with existing evidence if sufficient, "
        f"(2) repo_list_files for a NEW subdirectory, "
        f"(3) planner_scratchpad_read for a known window, "
        f"(4) typed block if no progress possible."
    )

    return {"detected": True, "repeated_paths": repeated_paths, "repeated_count": total_repeats, "guidance": guidance}


def _detect_repeated_list_files_loop(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Detect when the planner is stuck in a loop of repeated repo_list_files calls."""
    if not isinstance(history, list):
        return {"detected": False, "repeated_paths": [], "repeated_count": 0, "guidance": ""}

    successful_lists: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        result = history_tool_result(item)
        if result.get("tool") != "repo_list_files" or result.get("ok") is not True:
            continue
        successful_lists.append(result)

    if len(successful_lists) < 3:
        return {"detected": False, "repeated_paths": [], "repeated_count": 0, "guidance": ""}

    path_counts: dict[str, int] = {}
    for list_result in successful_lists:
        path = str(list_result.get("path") or ".")
        path_counts[path] = path_counts.get(path, 0) + 1

    repeated_paths = [path for path, count in path_counts.items() if count >= 2]
    if not repeated_paths:
        return {"detected": False, "repeated_paths": [], "repeated_count": 0, "guidance": ""}

    total_repeats = sum(count for path, count in path_counts.items() if count >= 2)
    guidance = (
        f"Planner is stuck in a list_files loop: {len(repeated_paths)} path(s) listed {total_repeats}+ times total. "
        f"Repeated paths: {', '.join(repeated_paths[:5])}. "
        f"Do NOT call repo_list_files again for these paths. "
        f"Choose one of: (1) final with existing evidence if sufficient, "
        f"(2) repo_read for a NEW file, "
        f"(3) planner_scratchpad_read for a known window, "
        f"(4) typed block if no progress possible."
    )

    return {"detected": True, "repeated_paths": repeated_paths, "repeated_count": total_repeats, "guidance": guidance}


def _detect_repeated_scratchpad_loop(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Detect when the planner is stuck in a loop of repeated planner_scratchpad_read calls."""
    if not isinstance(history, list):
        return {"detected": False, "repeated_paths": [], "repeated_count": 0, "guidance": ""}

    successful_reads: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        result = history_tool_result(item)
        if result.get("tool") != "planner_scratchpad_read" or result.get("ok") is not True:
            continue
        successful_reads.append(result)

    if len(successful_reads) < 2:
        return {"detected": False, "repeated_paths": [], "repeated_count": 0, "guidance": ""}

    # Check for repeated document_id or section calls
    doc_counts: dict[str, int] = {}
    for read_result in successful_reads:
        doc_id = str(read_result.get("document_id") or read_result.get("section") or "")
        if doc_id:
            doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1

    repeated_docs = [doc for doc, count in doc_counts.items() if count >= 2]
    if not repeated_docs:
        return {"detected": False, "repeated_paths": [], "repeated_count": 0, "guidance": ""}

    total_repeats = sum(count for doc, count in doc_counts.items() if count >= 2)
    guidance = (
        f"Planner is stuck in a scratchpad read loop: {len(repeated_docs)} document(s)/section(s) read {total_repeats}+ times total. "
        f"Repeated selectors: {', '.join(repeated_docs[:5])}. "
        f"Do NOT call planner_scratchpad_read again for these selectors. "
        f"Choose one of: (1) final with existing evidence if sufficient, "
        f"(2) repo_read for a NEW file, "
        f"(3) typed block if no progress possible."
    )

    return {"detected": True, "repeated_paths": repeated_docs, "repeated_count": total_repeats, "guidance": guidance}


def _generate_replay_guidance(history: list[dict[str, Any]], violations: list[str]) -> str:
    """Generate replay guidance based on detected loops and violations.

    This function detects repeated read patterns and generates specific guidance
    to help the planner choose different actions.
    """
    if not isinstance(history, list) or not violations:
        return ""

    # Detect repeated read loops
    read_loop = _detect_repeated_read_loop(history)
    list_loop = _detect_repeated_list_files_loop(history)
    scratchpad_loop = _detect_repeated_scratchpad_loop(history)

    # Build guidance from detected loops
    guidance_parts: list[str] = []

    if read_loop.get("detected"):
        guidance_parts.append(read_loop.get("guidance", ""))

    if list_loop.get("detected"):
        guidance_parts.append(list_loop.get("guidance", ""))

    if scratchpad_loop.get("detected"):
        guidance_parts.append(scratchpad_loop.get("guidance", ""))

    if not guidance_parts:
        return ""

    # Add violation-specific guidance
    violation_text = " ".join(str(v) for v in violations).lower()

    if "repo_read_already_successful" in violation_text:
        guidance_parts.append(
            "Violation: repo_read_already_successful. Do NOT repeat repo_read for already-read paths. "
            "Choose a NEW path or final/block."
        )

    if "repeated_same_tool_arguments_without_progress" in violation_text:
        guidance_parts.append(
            "Violation: repeated_same_tool_arguments_without_progress. The planner is repeating the same tool call "
            "without progress. Change the tool, change the arguments, or choose final/block."
        )

    if "repo_read_window_already_successful" in violation_text:
        guidance_parts.append(
            "Violation: repo_read_window_already_successful. Do NOT repeat repo_read for already-read windows. "
            "Choose a NEW window or final/block."
        )

    return "\n\n".join(g for g in guidance_parts if g)


def _should_attempt_vulkan_repair_for_repeated_reads(
    decision: dict[str, Any],
    validation: dict[str, Any],
    history: list[dict[str, Any]],
) -> bool:
    """Check if the planner is stuck in a repeated-read loop and needs repair guidance.

    This is a dedicated check for repeated-read loops that should trigger vulkan repair
    to provide the planner with alternative action guidance.
    """
    if not isinstance(history, list):
        return False

    violations = validation.get("violations") if isinstance(validation.get("violations"), list) else []
    if not violations:
        return False

    # Check for repeated-read violations
    repeated_read_violations = [
        v for v in violations
        if isinstance(v, str) and (
            "repo_read_already_successful" in v
            or "repo_read_window_already_successful" in v
            or "repeated_repo_read" in v
            or "repeated_same_tool_arguments_without_progress" in v
            or "repo_read_no_progress" in v
        )
    ]

    if not repeated_read_violations:
        return False

    # Detect the loop
    read_loop = _detect_repeated_read_loop(history)
    list_loop = _detect_repeated_list_files_loop(history)

    if read_loop.get("detected") or list_loop.get("detected"):
        return True

    return False
