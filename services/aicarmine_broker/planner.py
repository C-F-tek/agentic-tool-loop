"""
aicarmine_broker.planner
========================
The controlled 30B planner loop.

Responsibilities:
- Post requests to 11434 (PLANNER_URL) with streaming
- Detect degenerate / role-boundary-contaminated output
- Ask Vulkan/GPU0 11435 for explicit IA repair when planner output is malformed or a tool decision is invalid
- Run the multi-step agentic loop ``run_agentic_planner_job``
- Manage job lifecycle transitions

No FastAPI routes or HTTP server code here.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
# keep it here dont delete
from aicarmine_broker.application.planner.goal_classifier import semantic_goal_classification as _classify_goal_deliverable
from aicarmine_broker.application.planner.evidence_contract_builder import planner_evidence_contract as _planner_evidence_contract_impl
from aicarmine_broker.application.prompt.tool_contract import tool_shape_examples_for_prompt as _tool_shape_examples_for_prompt
###########
from aicarmine_broker.application.evidence import user_scope_claims
from aicarmine_broker.application.evidence.repo_history import extract_key_lines, file_memory_from_history, rank_core_candidates, repo_list_evidence
from aicarmine_broker.application.evidence.repo_path_policy import dynamic_read_candidate_paths, path_under_scope
from aicarmine_broker.application.evidence.scope_conflict_resolution import target_scope_conflict_resolved
from aicarmine_broker.application.planner.planner_repair import *  # pyright: ignore[reportWildcardImportFromLibrary]
from aicarmine_broker.application.planner.planner_replan_specialist import (
    _specialist_route_audit,
    _FINAL_QUALITY_ROUTE_TOOLS,
)
from aicarmine_broker.application.planner.validation_rejections import *  # pyright: ignore[reportWildcardImportFromLibrary]
from aicarmine_broker.application.prompt.budget import *  # pyright: ignore[reportWildcardImportFromLibrary]
from aicarmine_broker.application.prompt.history_contract import *  # pyright: ignore[reportWildcardImportFromLibrary]
from aicarmine_broker.application.prompt.intrinsic_context import *  # pyright: ignore[reportWildcardImportFromLibrary]
from aicarmine_broker.application.prompt.text_windows import *  # pyright: ignore[reportWildcardImportFromLibrary]
from aicarmine_broker.application.prompt.values import *  # pyright: ignore[reportWildcardImportFromLibrary]
from aicarmine_broker.application.tool_surface.manifest_builder import *  # pyright: ignore[reportWildcardImportFromLibrary]
from aicarmine_broker.application.tool_surface.result_digest import *  # pyright: ignore[reportWildcardImportFromLibrary]
from aicarmine_broker.application.tool_surface.turn_surface_policy import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.evidence.final_quality import repo_analysis_final_answer_model_quality_request, sanitize_repo_analysis_final_model_quality
from .application.planner.decision_normalizer import _native_tool_calls_decision
from .config import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .job_store import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.shared.memory_tools import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .code_edit_proposal_contract import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .planner_core.json_io import _parse_strict_json_object
from .planner_core.cache import _repair_cache_key
from .planner_intrinsic_context import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .infrastructure.repo_tools import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.planner.agentic_v2 import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.planner.vulkan_repair import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.prompt.available_tools import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.controller.diagnostics import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.prompt.context_windows import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.evidence.required_working_set import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.code_product.required_working_set import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.prompt.pack_builder import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.prompt.evidence_contract import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.evidence.builder import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.planner.loop import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.planner.system_prompt import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.planner.turn import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.planner.validator import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.public_payload.final_state_result import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.evidence.execution_digest import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.evidence.final_quality import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.evidence.audit_guidance import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.evidence.initial_orientation import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.public_payload.openwebui_terminal_answer import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.public_payload.evidence_materializer import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.public_payload.openwebui_tool_context import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.tool_surface.candidate_actions import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.controller.guards import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.runtime_debug import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.npu_phi import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.controller.memory import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.controller.preseed import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.controller.orientation_lane import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.controller.rag_preseed import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.evidence.core_discovery import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.code_product.state import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.code_product.public_outputs import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.code_product.history import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.evidence.goal_classifier import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.evidence.goal_scope import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.shared.history_queries import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.shared.clean_values import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.shared.evidence_contract_summary import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.shared.history_ledger import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.prompt.history_messages import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.public_payload.tool_context import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.public_payload.terminal_sanitizer import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .application.public_payload.terminal_result import *  # pyright: ignore[reportWildcardImportFromLibrary]
from .infrastructure.json_files import *  # pyright: ignore[reportWildcardImportFromLibrary]

# ---------------------------------------------------------------------------
# Module-level constants and helpers
# ---------------------------------------------------------------------------


# NOTE: public_terminal_result_for_30b is imported from terminal_result above.
# It accepts (result, repo_read_item_full_content=...) and delegates to the
# extracted implementation in application/public_payload/terminal_result.py.




# ---------------------------------------------------------------------------
# Orientation shadow composition (behavior-neutral wiring)
# ---------------------------------------------------------------------------

ORIENTATION_SHADOW_MAX_SELECTED = 13


def _controller_initial_orientation_candidate_pool(
    root_result: dict[str, Any],
) -> list[dict[str, Any]]:
    return controller_initial_orientation_candidate_pool(
        root_result,
        repo_root=LAB_REPO,
        safe_rel_path=safe_rel_path,
        named_read_priority=_NAMED_READ_PRIORITY,
    )

# CUDA rewrite functions moved to application.planner.planner_cuda_rewrite
def _hard_budget_tool_shape_examples_for_prompt() -> dict[str, Any]:
    return hard_budget_tool_shape_examples_for_prompt(
        native_tools=AGENTIC_PLANNER_NATIVE_TOOLS,
    )


def _compact_history_for_prompt(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return compact_history_for_prompt(
        history,
        history_tail=AGENTIC_PLANNER_HISTORY_PROMPT_TAIL,
        prompt_preview_chars=AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS,
        ledger_builder=planner_history_ledger,
    )

def _compact_evidence_contract_for_prompt(contract: dict[str, Any]) -> dict[str, Any]:
    return compact_evidence_contract_for_prompt(
        contract,
        prompt_preview_chars=AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS,
    )


# Evidence contract key groups with clip limits — lookup table strategy (§8.4)
_EVIDENCE_CONTRACT_KEY_GROUPS: tuple[tuple[str, int, int], ...] = (
    # (key_group_name, text_limit, list_limit)
    ("semantic_fields", 300, 4),       # semantic_goal_classification, goal_requests_*, target_kind, resolved_*, counts, coverage, planner_may_choose_final, required_next_progress
    ("path_fields", 180, 20),          # successful_repo_read_paths, read_admissible_paths, validator_admissible_*, failed_*
    ("contract_fields", 260, 4),       # core_discovery_status, code_product_contract, finalization_contract, initial_orientation_surface
)

# Evidence contract window extracted to application.prompt.evidence_contract_window


def _windowed_evidence_contract_for_prompt(
    root: Path,
    *,
    goal: str,
    contract: dict[str, Any],
    window_chars: int,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from pathlib import Path as _Path
    from .application.prompt.evidence_contract_window import (
        windowed_evidence_contract_for_prompt as _inner,
    )
    return _inner(str(root), goal=goal, contract=contract, window_chars=window_chars, history=history)


def prompt_section_window_pack(
    root: Path,
    *,
    goal: str,
    section: str,
    value: Any,
    window_chars: int,
    reason: str,
) -> dict[str, Any]:
    window = _store_prompt_value_window(
        root,
        section=section,
        value=value,
        query=goal,
        max_chars=max(500, int(window_chars or 1000)),
        metadata={
            "kind": "planner_prompt_section",
            "section": section,
            "format": "json",
            "reason": reason,
        },
    )
    out = {
        "schema": "planner_prompt_section_window.v1",
        "store": "job_local_sqlite",
        "section": section,
        "reason": reason,
        "serialized_json_window": window,
    }
    if window.get("document_id") and window.get("has_more_after") is True:
        out["planner_can_request_more"] = {
            "tool": "planner_scratchpad_read",
            "arguments": {
                "kind": "prompt_context_window",
                "document_id": window.get("document_id"),
                "offset": window.get("window_end"),
                "max_chars": max(500, int(window_chars or 1000)),
            },
        }
    return out


def _hard_budget_evidence_contract_for_prompt(
    root: Path,
    *,
    goal: str,
    contract: dict[str, Any],
    window_chars: int,
    history: list[dict[str, Any]] | None = None,
    reason: str,
) -> dict[str, Any]:
    if not isinstance(contract, dict) or not contract:
        return {}
    window = _store_prompt_value_window(
        root,
        section="evidence_contract:hard_budget",
        value=contract,
        query=goal,
        max_chars=max(500, int(window_chars or 1000)),
        metadata={"kind": "evidence_contract", "format": "json", "reason": reason},
    )
    compact = hard_budget_evidence_contract_summary(contract, reason=reason)
    compact["full_evidence_contract_window"] = window
    if window.get("document_id") and window.get("has_more_after") is True:
        compact["planner_can_request_more_evidence_contract"] = {
            "tool": "planner_scratchpad_read",
            "arguments": {
                "kind": "prompt_context_window",
                "document_id": window.get("document_id"),
                "offset": window.get("window_end"),
                "max_chars": max(500, int(window_chars or 1000)),
            },
        }
        continuation = _evidence_contract_continuation_action(
            compact,
            history=history or [],
            window_chars=max(500, int(window_chars or 1000)),
        )
        if continuation:
            compact["optional_evidence_contract_next_window"] = continuation
    return compact


def _report_exceeds_generation_headroom(report: dict[str, Any], headroom_char_budget: int) -> bool:
    return report_exceeds_generation_headroom(report, headroom_char_budget)


def _preserve_required_next_tool_call_for_prompt(
    payload: dict[str, Any],
    previous_evidence_contract: dict[str, Any],
) -> None:
    preserve_required_next_tool_call_for_prompt(payload, previous_evidence_contract)


def _enforce_required_scratchpad_read_continuation_contract(
    contract: dict[str, Any],
    continuation: dict[str, Any],
) -> dict[str, Any]:
    return enforce_required_scratchpad_read_continuation_contract(
        contract,
        continuation,
    )


def _compact_intrinsic_context_for_prompt(context: dict[str, Any]) -> dict[str, Any]:
    return compact_intrinsic_context_for_prompt(
        context,
        prompt_preview_chars=AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS,
    )


def _windowed_optional_context_value(
    root: Path,
    *,
    goal: str,
    key: str,
    value: Any,
    window_chars: int,
) -> Any:
    if value in (None, "", [], {}):
        return value
    if json_char_len(value) <= max(800, int(window_chars or 1000)):
        return value
    window = _store_prompt_value_window(
        root,
        section=f"optional_context:{key}",
        value=value,
        query=goal,
        max_chars=window_chars,
        metadata={"kind": "optional_context", "key": key, "format": "json"},
    )
    out = {
        "schema": "planner_optional_context_window.v1",
        "source_key": key,
        "store": "job_local_sqlite",
        "serialized_json_window": window,
    }
    if window.get("document_id") and window.get("has_more_after") is True:
        out["planner_can_request_more"] = {
            "tool": "planner_scratchpad_read",
            "arguments": {
                "kind": "prompt_context_window",
                "document_id": window.get("document_id"),
                "offset": window.get("window_end"),
                "max_chars": window_chars,
            },
        }
    return out


def _optional_context_window_pack(
    root: Path,
    *,
    goal: str,
    optional_context: dict[str, Any],
    window_chars: int,
    reason: str,
) -> dict[str, Any]:
    source_keys = [
        str(key)
        for key, value in (optional_context or {}).items()
        if value not in (None, "", [], {})
    ]
    successful_payload_windows = (
        optional_context.get("successful_tool_payload_windows")
        if isinstance(optional_context.get("successful_tool_payload_windows"), list)
        else []
    )
    window_source = dict(optional_context or {})
    if successful_payload_windows:
        window_source.pop("successful_tool_payload_windows", None)
    window = _store_prompt_value_window(
        root,
        section="optional_context:hard_budget_pack",
        value=window_source,
        query=goal,
        max_chars=max(500, int(window_chars or 1000)),
        metadata={
            "kind": "optional_context_hard_budget_pack",
            "format": "json",
            "reason": reason,
            "source_keys": source_keys,
        },
    )
    out = {
        "schema": "planner_optional_context_window_pack.v1",
        "store": "job_local_sqlite",
        "reason": reason,
        "source_keys": source_keys,
        "serialized_json_window": window,
    }
    if successful_payload_windows:
        out["successful_tool_payload_windows"] = successful_payload_windows
    if window.get("document_id") and window.get("has_more_after") is True:
        out["planner_can_request_more"] = {
            "tool": "planner_scratchpad_read",
            "arguments": {
                "kind": "prompt_context_window",
                "document_id": window.get("document_id"),
                "offset": window.get("window_end"),
                "max_chars": max(500, int(window_chars or 1000)),
            },
        }
    return out


def _optional_context_for_prompt(
    *,
    root: Path,
    goal: str,
    history: list[dict[str, Any]],
    planner_memory: dict[str, Any],
    intrinsic_context: dict[str, Any],
    last_tool_result: dict[str, Any],
    compact_mode: bool,
    window_chars: int,
) -> dict[str, Any]:
    optional = {
        "planner_memory": prompt_clip_value(planner_memory, text_limit=360, list_limit=4),
        "intrinsic_context": _compact_intrinsic_context_for_prompt(intrinsic_context),
    }
    if AGENTIC_PLANNER_NATIVE_TOOLS:
        optional["history_transport"] = {
            "schema": "planner_history_transport.v1",
            "tool_history_and_results": "ollama_messages",
            "tool_result_payloads": "sqlite_windows",
            "read_more_tool": "planner_scratchpad_read",
            "history_items_available": len(history if isinstance(history, list) else []),
        }
    else:
        optional.update({
            "history_tail": _compact_history_for_prompt(history),
            "turn_memory": prompt_clip_value(_planner_turn_memory(history), list_limit=8),
            "last_tool_result_digest": prompt_clip_value(
                planner_last_result_digest(last_tool_result),
                text_limit=AGENTIC_PLANNER_PROMPT_PREVIEW_CHARS,
                list_limit=8,
            ),
        })
    if not compact_mode:
        return optional
    tool_payload_windows: list[dict[str, Any]] = []
    if not AGENTIC_PLANNER_NATIVE_TOOLS:
        for row in reversed(history if isinstance(history, list) else []):
            result = history_tool_result(row)
            if not result.get("ok"):
                continue
            if result.get("tool") == "controller_guard":
                continue
            raw_payload = _same_tool_artifact_payload(result)
            if not isinstance(raw_payload, dict):
                continue
            raw_text = json.dumps(raw_payload, ensure_ascii=False, indent=2, default=str)
            if not raw_text.strip():
                continue
            window = _store_prompt_text_window(
                root,
                section=f"tool_result:{row.get('step')}:{result.get('tool')}",
                text=raw_text,
                query=goal,
                max_chars=window_chars,
                metadata={
                    "kind": "successful_tool_result_payload",
                    "step": row.get("step"),
                    "tool": result.get("tool"),
                    "format": "json",
                },
            )
            item = {
                "step": row.get("step"),
                "tool": result.get("tool"),
                "window": window,
            }
            if window.get("document_id") and window.get("has_more_after") is True:
                item["planner_can_request_more"] = {
                    "tool": "planner_scratchpad_read",
                    "arguments": {
                        "kind": "prompt_context_window",
                        "document_id": window.get("document_id"),
                        "offset": window.get("window_end"),
                        "max_chars": window_chars,
                    },
                }
            tool_payload_windows.append(item)
            if len(tool_payload_windows) >= 4:
                break
    if tool_payload_windows:
        optional["successful_tool_payload_windows"] = list(reversed(tool_payload_windows))
    return {
        key: (
            value
            if key == "successful_tool_payload_windows"
            else _windowed_optional_context_value(
                root,
                goal=goal,
                key=key,
                value=value,
                window_chars=window_chars,
            )
        )
        for key, value in optional.items()
    }


def _planner_token_generation_reserve(num_ctx: int | None = None) -> int:
    try:
        ctx = int(num_ctx if num_ctx is not None else AGENTIC_PLANNER_NUM_CTX)
    except (ValueError, TypeError):
        ctx = 0
        # Log or emit diagnostic here if needed
    if ctx <= 0:
        return 0
    return max(512, min(32768, ctx // 16))


def _prompt_compaction_threshold() -> int:
    if AGENTIC_PLANNER_PROMPT_CHAR_BUDGET <= 0:
        return 0
    ratio = float(AGENTIC_PLANNER_PROMPT_COMPACT_RATIO or 0.5)
    ratio = max(0.1, min(ratio, 0.95))
    return max(1000, int(AGENTIC_PLANNER_PROMPT_CHAR_BUDGET * ratio))


def _prompt_generation_headroom_char_budget() -> int:
    budget = int(AGENTIC_PLANNER_PROMPT_CHAR_BUDGET or 0)
    if budget <= 0:
        return 0
    generation_reserve = int(_planner_token_generation_reserve() * PROMPT_CHARS_PER_TOKEN)
    generation_reserve = max(12000, min(max(12000, budget // 3), generation_reserve))
    char_budget_limit = budget - generation_reserve
    token_budget_limit = int(
        max(1, AGENTIC_PLANNER_NUM_CTX - _planner_token_generation_reserve()) * PROMPT_CHARS_PER_TOKEN
    )
    return max(1000, min(char_budget_limit, token_budget_limit))


def _prompt_window_chars(compact_mode: bool, attempt: int = 0) -> int:
    budget = int(AGENTIC_PLANNER_PROMPT_CHAR_BUDGET or 0)
    if compact_mode:
        base = max(4000, min(64000, budget // 16 if budget > 0 else 4000))
        sequence = (
            base,
            int(base * 0.75),
            int(base * 0.60),
            int(base * 0.45),
            int(base * 0.30),
            int(base * 0.20),
            int(base * 0.15),
            int(base * 0.10),
        )
        return sequence[min(max(0, attempt), len(sequence) - 1)]
    return max(1000, min(96000, budget // 8 if budget > 0 else 6000))


def _prompt_budget_report(
    user_payload: dict[str, Any],
    *,
    system_prompt: str = "",
    extra_prompt_sections: dict[str, int] | None = None,
) -> dict[str, Any]:
    sections = {
        key: json_char_len(value)
        for key, value in user_payload.items()
        if key not in {"available_tools"}
    }
    sections["available_tools"] = json_char_len(user_payload.get("available_tools"))
    extra_sections = {
        str(key): int(value)
        for key, value in (extra_prompt_sections or {}).items()
        if int(value or 0) > 0
    }
    sections.update(extra_sections)
    total_user = json_char_len(user_payload)
    system_chars = len(str(system_prompt or ""))
    extra_chars = sum(extra_sections.values())
    total = total_user + system_chars + extra_chars
    headroom_budget = _prompt_generation_headroom_char_budget()
    generation_reserve = max(0, AGENTIC_PLANNER_PROMPT_CHAR_BUDGET - headroom_budget)
    return {
        "schema": "planner_prompt_budget.v1",
        "char_budget": AGENTIC_PLANNER_PROMPT_CHAR_BUDGET,
        "generation_headroom_char_budget": headroom_budget,
        "generation_headroom_reserve_chars": generation_reserve,
        "num_ctx_effective": AGENTIC_PLANNER_NUM_CTX,
        "generation_token_reserve": _planner_token_generation_reserve(),
        "system_prompt_chars": system_chars,
        "total_user_payload_chars": total_user,
        "extra_prompt_chars": extra_chars,
        "total_prompt_chars": total,
        "over_budget": bool(
            AGENTIC_PLANNER_PROMPT_CHAR_BUDGET > 0
            and total > AGENTIC_PLANNER_PROMPT_CHAR_BUDGET
        ),
        "over_generation_headroom_budget": bool(headroom_budget > 0 and total > headroom_budget),
        "sections": sections,
    }


def _read_json_file(path: str) -> dict[str, Any]:
    if not path:
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (ValueError, TypeError, OSError, IOError):
        return {}
    return data if isinstance(data, dict) else {}


def _repo_read_file_content_from_repo(item: dict[str, Any], known_prefix: str = "") -> tuple[str, dict[str, Any]]:
    path = repo_rel_token(item.get("path") or "")
    meta: dict[str, Any] = {"source": "repo_file_rehydrate_unavailable", "path": path}
    if not path:
        meta["error"] = "missing_path"
        return "", meta
    try:
        rel = safe_rel_path(path)
        full = (LAB_REPO / rel).resolve(strict=False)
        full.relative_to(LAB_REPO)
        if not full.exists() or not full.is_file():
            meta["error"] = "file_not_found"
            return "", meta
        text = full.read_text(encoding="utf-8-sig", errors="replace")
        prefix = str(known_prefix or "")
        if prefix and not text.startswith(prefix):
            meta.update(
                {
                    "source": "repo_file_rehydrate_prefix_mismatch",
                    "error": "repo_file_no_longer_matches_repo_read_prefix",
                    "known_prefix_chars": len(prefix),
                    "file_chars": len(text),
                }
            )
            return "", meta
        meta.update(
            {
                "source": "repo_file_rehydrated_for_prompt_window",
                "file_chars": len(text),
                "known_prefix_matched": bool(prefix),
            }
        )
        return text, meta
    except (OSError, IOError, PermissionError) as exc:
        meta.update({"error": "repo_file_rehydrate_failed", "error_type": type(exc).__name__})
        return "", meta


def _repo_read_item_full_content(item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Extract full file content for a repo_read item using guard clauses (§8.3)."""
    meta: dict[str, Any] = {"source": "tool_result_inline"}
    artifact = str(item.get("artifact") or "")
    content = item.get("content")
    loaded = _read_json_file(artifact)
    artifact_content = loaded.get("content")
    preview = item.get("content_preview")
    known_prefix = (
        content if isinstance(content, str)
        else artifact_content if isinstance(artifact_content, str)
        else preview if isinstance(preview, str)
        else ""
    )

    # Guard 1: Artifact rehydration — prefer full content from artifact JSON
    if isinstance(artifact_content, str) and artifact_content:
        inline_prefix = content if isinstance(content, str) else preview if isinstance(preview, str) else ""
        if not inline_prefix or artifact_content.startswith(inline_prefix):
            meta.update(
                {
                    "source": "repo_read_artifact_rehydrated_for_prompt",
                    "artifact": artifact,
                    "artifact_chars": len(artifact_content),
                    "inline_prefix_matched": bool(inline_prefix),
                }
            )
            return artifact_content, meta

    # Guard 2: Truncated item — try rehydrating from repo filesystem
    if item.get("truncated") is True:
        repo_text, repo_meta = _repo_read_file_content_from_repo(item, known_prefix)
        if isinstance(repo_text, str) and repo_text:
            repo_meta["artifact"] = artifact
            return repo_text, repo_meta

    # Guard 3: Direct content available (not truncated) — use inline
    if isinstance(content, str) and item.get("truncated") is not True:
        return content, meta

    # Guard 4: Known prefix available — use it with truncated marker if needed
    if isinstance(known_prefix, str) and known_prefix:
        if item.get("truncated") is True:
            meta.update(
                {
                    "source": "tool_result_inline_truncated_prefix_only",
                    "artifact": artifact,
                }
            )
        return known_prefix, meta

    # Guard 5: Preview available — try rehydrating from repo, fall back to preview
    if isinstance(preview, str):
        repo_text, repo_meta = _repo_read_file_content_from_repo(item, preview)
        if isinstance(repo_text, str) and repo_text:
            repo_meta["artifact"] = artifact
            return repo_text, repo_meta
        meta.update({"source": "content_preview_only", "artifact": artifact})
        return preview, meta

    # Fallback: no content available
    return "", meta


def _store_prompt_text_window(
    root: Path,
    *,
    section: str,
    text: str,
    query: str,
    max_chars: int,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return planner_prompt_context_store_window(
        root,
        section=section,
        text=str(text or ""),
        query=query,
        max_chars=max(500, int(max_chars or 1000)),
        metadata=metadata or {},
    )


def _store_prompt_value_window(
    root: Path,
    *,
    section: str,
    value: Any,
    query: str,
    max_chars: int,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    return _store_prompt_text_window(
        root,
        section=section,
        text=text,
        query=query,
        max_chars=max_chars,
        metadata=metadata,
    )

def _prompt_window_consumed_offsets(history: list[dict[str, Any]]) -> dict[str, int]:
    return prompt_window_consumed_offsets(
        history,
        history_tool_result=history_tool_result,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _prompt_window_tracking_metadata_errors(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return prompt_window_tracking_metadata_errors(
        history,
        history_tool_result=history_tool_result,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def prompt_context_continue_action(window: dict[str, Any], *, max_chars: int, reason: str) -> dict[str, Any] | None:
    return prompt_context_continue_action(
        window,
        max_chars=max_chars,
        reason=reason,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _planner_scratchpad_next_window_action_from_history(
    args: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    return planner_scratchpad_next_window_action_from_history(
        args,
        history,
        history_tool_result=history_tool_result,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def repo_read_items_for_prompt(
    history: list[dict[str, Any]],
    paths: set[str],
    *,
    job_root: Path,
    goal: str,
    window_chars: int,
    compact_mode: bool,
) -> list[dict[str, Any]]:
    return repo_read_items_for_prompt(
        history,
        paths,
        job_root=job_root,
        goal=goal,
        window_chars=window_chars,
        compact_mode=compact_mode,
        history_tool_result=history_tool_result,
        repo_rel_token=repo_rel_token,
        repo_read_item_full_content=_repo_read_item_full_content,
        store_prompt_text_window=_store_prompt_text_window,
        window_text=window_text,
    )


def latest_code_product_for_prompt(
    history: list[dict[str, Any]],
    *,
    job_root: Path,
    goal: str,
    window_chars: int,
    compact_mode: bool,
) -> dict[str, Any]:
    return latest_code_product_for_prompt(
        history,
        job_root=job_root,
        goal=goal,
        window_chars=window_chars,
        compact_mode=compact_mode,
        store_prompt_text_window=_store_prompt_text_window,
        text_hash=text_hash,
    )


def _required_working_set_for_prompt(
    goal: str,
    history: list[dict[str, Any]],
    contract: dict[str, Any],
    *,
    job_root: Path,
    window_chars: int,
    compact_mode: bool,
    max_repo_read_items: int | None = None,
    max_total_repo_read_window_chars: int | None = None,
) -> dict[str, Any]:
    return required_working_set_for_prompt(
        goal,
        history,
        contract,
        job_root=job_root,
        window_chars=window_chars,
        compact_mode=compact_mode,
        repo_rel_token=repo_rel_token,
        goal_target_file=_goal_target_file,
        latest_code_product_build_state=latest_code_product_build_state,
        history_tool_result=history_tool_result,
        repo_read_item_full_content=_repo_read_item_full_content,
        store_prompt_text_window=_store_prompt_text_window,
        window_text=window_text,
        text_hash=text_hash,
        max_repo_read_items=max_repo_read_items,
        max_total_repo_read_window_chars=max_total_repo_read_window_chars,
    )


def _required_working_set_continuation_action(
    required_working_set: dict[str, Any],
    *,
    history: list[dict[str, Any]],
    window_chars: int,
) -> dict[str, Any] | None:
    return required_working_set_continuation_action(
        required_working_set,
        history=history,
        window_chars=window_chars,
        history_tool_result=history_tool_result,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _evidence_contract_continuation_action(
    evidence_contract: dict[str, Any],
    *,
    history: list[dict[str, Any]],
    window_chars: int,
) -> dict[str, Any] | None:
    return evidence_contract_continuation_action(
        evidence_contract,
        history=history,
        window_chars=window_chars,
        history_tool_result=history_tool_result,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _prompt_context_continuation_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return prompt_context_continuation_from_payload(
        payload,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _decision_matches_prompt_context_continuation(
    decision: dict[str, Any],
    continuation: dict[str, Any],
) -> bool:
    return decision_matches_prompt_context_continuation(decision, continuation)


def _required_next_tool_call_from_action(action: dict[str, Any]) -> dict[str, Any]:
    return required_next_tool_call_from_action(action)


def _forbidden_repeated_prompt_window_calls(
    history: list[dict[str, Any]],
    continuation_action: dict[str, Any],
) -> list[dict[str, Any]]:
    return forbidden_repeated_prompt_window_calls(
        history,
        continuation_action,
        history_tool_result=history_tool_result,
        required_next_tool_call_from_action=_required_next_tool_call_from_action,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _native_history_message_reserve_chars(history: list[dict[str, Any]], window_chars: int) -> int:
    if not AGENTIC_PLANNER_NATIVE_TOOLS:
        return 0
    if not any(history_tool_result(item) for item in (history if isinstance(history, list) else [])):
        return 0
    window = max(2500, int(window_chars or 0))
    return max(6000, window + 3000)


def _build_planner_user_payload(
    *,
    job_id: str,
    state: dict[str, Any],
    step: int,
    history: list[dict[str, Any]],
    tool_manifest: list[dict[str, Any]],
    evidence_contract: dict[str, Any],
    planner_memory: dict[str, Any],
    intrinsic_context: dict[str, Any],
    last_tool_result: dict[str, Any],
    native_tools_schema: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return build_planner_user_payload(
        job_id=job_id,
        state=state,
        step=step,
        history=history,
        tool_manifest=tool_manifest,
        evidence_contract=evidence_contract,
        planner_memory=planner_memory,
        intrinsic_context=intrinsic_context,
        last_tool_result=last_tool_result,
        native_tools_schema=native_tools_schema,
        deps={
            "available_tools_for_user_payload": available_tools_for_user_payload,
            "available_tools_window_pack": available_tools_window_pack,
            "compact_evidence_contract_for_prompt": _compact_evidence_contract_for_prompt,
            "compact_tool_manifest_for_prompt": compact_tool_manifest_for_prompt,
            "enforce_required_scratchpad_read_continuation_contract": (
                _enforce_required_scratchpad_read_continuation_contract
            ),
            "forbidden_repeated_prompt_window_calls": _forbidden_repeated_prompt_window_calls,
            "hard_budget_evidence_contract_for_prompt": _hard_budget_evidence_contract_for_prompt,
            "hard_budget_tool_shape_examples_for_prompt": _hard_budget_tool_shape_examples_for_prompt,
            "json_char_len": json_char_len,
            "native_history_message_reserve_chars": _native_history_message_reserve_chars,
            "optional_context_for_prompt": _optional_context_for_prompt,
            "optional_context_window_pack": _optional_context_window_pack,
            "planner_system_for_current_mode": _planner_system_for_current_mode,
            "preserve_required_next_tool_call_for_prompt": _preserve_required_next_tool_call_for_prompt,
            "prompt_budget_report": _prompt_budget_report,
            "prompt_compaction_threshold": _prompt_compaction_threshold,
            "prompt_generation_headroom_char_budget": _prompt_generation_headroom_char_budget,
            "prompt_window_chars": _prompt_window_chars,
            "report_exceeds_generation_headroom": _report_exceeds_generation_headroom,
            "required_next_tool_call_from_action": _required_next_tool_call_from_action,
            "required_working_set_continuation_action": _required_working_set_continuation_action,
            "required_working_set_for_prompt": _required_working_set_for_prompt,
            "tool_shape_examples_for_prompt": _tool_shape_examples_for_prompt,
            "windowed_evidence_contract_for_prompt": _windowed_evidence_contract_for_prompt,
            "agent_job_root": agent_job_root,
            "internal_tool_prompt": internal_tool_prompt,
        },
        config={
            "AGENTIC_PLANNER_NATIVE_TOOLS": AGENTIC_PLANNER_NATIVE_TOOLS,
            "AGENTIC_PLANNER_NUM_CTX": AGENTIC_PLANNER_NUM_CTX,
            "AGENTIC_PLANNER_NUM_CTX_CAP": AGENTIC_PLANNER_NUM_CTX_CAP,
            "AGENTIC_PLANNER_NUM_CTX_REQUESTED": AGENTIC_PLANNER_NUM_CTX_REQUESTED,
            "AGENTIC_PLANNER_PROMPT_CHAR_BUDGET": AGENTIC_PLANNER_PROMPT_CHAR_BUDGET,
            "AGENTIC_PLANNER_PROMPT_COMPACT_RATIO": AGENTIC_PLANNER_PROMPT_COMPACT_RATIO,
            "LAB_REPO": LAB_REPO,
        },
    )






# Pass-through wrappers removed: _drop_empty_dict_values (now uses drop_empty_dict_values directly)


# Pass-through wrappers removed (now use imported functions directly):
# - _planner_ollama_turn_from_decision → planner_ollama_turn_from_decision
# - _history_item_ollama_turn → history_item_ollama_turn
# - _history_tool_result → history_tool_result
# - _planner_history_summary → planner_history_summary
# - _clean_planner_history_value → clean_planner_history_value
# - _planner_history_arguments → planner_history_arguments
# - _planner_history_reason → planner_history_reason
# - _planner_controller_guard_history_payload → planner_controller_guard_history_payload
# - _planner_history_evidence_payload → planner_history_evidence_payload


def _planner_tool_result_message_payload(
    item: dict[str, Any],
    result: dict[str, Any],
    *,
    root: Path,
    goal: str,
    window_chars: int,
) -> dict[str, Any]:
    return planner_tool_result_message_payload(
        item,
        result,
        root=root,
        goal=goal,
        window_chars=window_chars,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
        store_prompt_text_window=_store_prompt_text_window,
    )


def _planner_history_item_messages(
    item: dict[str, Any],
    *,
    root: Path,
    goal: str,
    window_chars: int,
) -> list[dict[str, Any]]:
    return planner_history_item_messages(
        item,
        root=root,
        goal=goal,
        window_chars=window_chars,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
        store_prompt_text_window=_store_prompt_text_window,
    )


def _planner_history_messages_for_ollama(
    history: list[dict[str, Any]],
    *,
    root: Path,
    goal: str,
    window_chars: int,
    max_chars: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return planner_history_messages_for_ollama(
        history,
        root=root,
        goal=goal,
        window_chars=window_chars,
        max_chars=max_chars,
        native_tools_enabled=AGENTIC_PLANNER_NATIVE_TOOLS,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
        store_prompt_text_window=_store_prompt_text_window,
    )


def _decision_for_turn_memory(decision: dict[str, Any] | None) -> dict[str, Any]:
    return decision_for_turn_memory(decision)


def _strip_public_artifact_paths(value: Any) -> Any:
    return strip_public_artifact_paths(value)


def _strip_public_local_references(value: Any) -> Any:
    return strip_public_local_references(value)


def _same_tool_artifact_payload(result: dict[str, Any]) -> dict[str, Any]:
    return same_tool_artifact_payload(result)


def _public_tool_response(tool_result: dict[str, Any]) -> dict[str, Any]:
    return public_tool_response(
        tool_result,
        same_tool_artifact_payload=_same_tool_artifact_payload,
        repo_read_item_full_content=_repo_read_item_full_content,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _successful_tool_turns(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return successful_tool_turns(
        history,
        same_tool_artifact_payload=_same_tool_artifact_payload,
        repo_read_item_full_content=_repo_read_item_full_content,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _public_tool_artifact_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return public_tool_artifact_rows(
        history,
        same_tool_artifact_payload=_same_tool_artifact_payload,
        repo_read_item_full_content=_repo_read_item_full_content,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _public_tool_context_limits(artifact_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return public_tool_context_limits(artifact_rows)


def _ollama_turn_rows(
    history: list[dict[str, Any]],
    terminal_decision: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return ollama_turn_rows(history, terminal_decision)


def _planner_turn_memory(
    history: list[dict[str, Any]],
    terminal_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return planner_turn_memory(
        history,
        terminal_decision,
        same_tool_artifact_payload=_same_tool_artifact_payload,
        repo_read_item_full_content=_repo_read_item_full_content,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def _ollama_turn_summary_text(
    history: list[dict[str, Any]],
    terminal_decision: dict[str, Any] | None = None,
) -> str:
    return ollama_turn_summary_text(history, terminal_decision)


def _final_summary_with_ollama_done_reasons(
    status: str,
    final_summary: str,
    result: dict[str, Any],
) -> str:
    return final_summary_with_ollama_done_reasons(status, final_summary, result)


# ---------------------------------------------------------------------------
# Controller guards / loop integrity helpers
# ---------------------------------------------------------------------------


def _normalize_tool_name(value: str) -> str:
    from .tool_contract import normalize_tool_name  # noqa: PLC0415 (lazy)
    return normalize_tool_name(value)


def controller_guard_count(history: list[dict[str, Any]], kind: str) -> int:
    return controller_guard_count(history, kind)


def _controller_guard_rejection_signature(validation: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    return controller_guard_rejection_signature(validation, decision)


def _controller_guard_rejection_signature_count(
    history: list[dict[str, Any]],
    signature: dict[str, Any],
) -> int:
    return controller_guard_rejection_signature_count(
        history,
        signature,
        invalid_decision_signature_key=_invalid_decision_signature_key,
    )


def recoverable_planner_block(decision: dict[str, Any]) -> bool:
    return recoverable_planner_block(decision)


def semantic_goal_classification(goal: str) -> dict[str, Any]:
    return _classify_goal_deliverable(goal, repo_analysis=_repo_analysis_goal(goal))


def goal_requires_code_product_report(goal: str) -> bool:
    classification = semantic_goal_classification(goal)
    return bool(classification.get("must_produce_code_product"))


def goal_has_write_intent(goal: str) -> bool:
    return goal_requests_apply(goal)


def _code_product_build_state_duplicate_write(
    history: list[dict[str, Any]],
    *,
    target_file: str,
    text: str,
) -> bool:
    return code_product_build_state_duplicate_write(
        history,
        target_file=target_file,
        text=text,
    )


def code_product_build_state_from_result(result: dict[str, Any]) -> dict[str, Any]:
    return code_product_build_state_from_result(result)


def _code_product_build_state_read_action(state: dict[str, Any], target_file: str) -> dict[str, Any]:
    return code_product_build_state_read_action(state, target_file)


def code_product_source_windows_from_reads(
    history: list[dict[str, Any]],
    target_file: str,
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    return code_product_source_windows_from_reads(
        history,
        target_file,
        same_tool_artifact_payload=_same_tool_artifact_payload,
        repo_read_item_full_content=_repo_read_item_full_content,
        limit=limit,
    )


def _code_product_build_state_write_action(
    target_file: str,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return code_product_build_state_write_action(
        target_file,
        history,
        same_tool_artifact_payload=_same_tool_artifact_payload,
        repo_read_item_full_content=_repo_read_item_full_content,
    )


def _code_product_build_state_propose_action(
    state: dict[str, Any],
    latest_violations: list[str],
) -> dict[str, Any]:
    return code_product_build_state_propose_action(state, latest_violations)


def _code_product_candidate_action(
    *,
    target_file: str,
    latest_violations: list[str],
    goal: str = "",
) -> dict[str, Any]:
    return code_product_candidate_action(
        target_file=target_file,
        latest_violations=latest_violations,
        goal=goal,
    )




def _successful_window_signatures(history: list[dict[str, Any]], tool: str) -> set[str]:
    return successful_window_signatures(history, tool)


def _successful_repo_read_window_ranges(history: list[dict[str, Any]], target_file: str) -> list[tuple[int, int]]:
    return successful_repo_read_window_ranges(history, target_file)


def _code_product_payload_rejection_count(
    validation_rejections: list[dict[str, Any]],
    target_file: str = "",
) -> int:
    return code_product_payload_rejection_count(validation_rejections, target_file)


def _code_product_source_window_candidate(
    target_file: str,
    *,
    line_count: int = 0,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return code_product_source_window_candidate(
        target_file,
        line_count=line_count,
        history=history,
        single_file_prompt_read_chars=_single_file_prompt_read_chars(),
    )


def strip_duplicate_window_candidate(
    actions: list[dict[str, Any]],
    *,
    tool: str,
    signature: str,
) -> list[dict[str, Any]]:
    return strip_duplicate_window_candidate(actions, tool=tool, signature=signature)


def _apply_duplicate_window_replan_contract(
    contract: dict[str, Any],
    *,
    violation: str,
    tool: str,
    args: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    return apply_duplicate_window_replan_contract(
        contract,
        violation=violation,
        tool=tool,
        args=args,
        history=history,
        planner_scratchpad_next_window_action_from_history=_planner_scratchpad_next_window_action_from_history,
        same_tool_artifact_payload=_same_tool_artifact_payload,
        repo_read_item_full_content=_repo_read_item_full_content,
        single_file_prompt_read_chars=_single_file_prompt_read_chars(),
    )


def _code_product_low_signal_target(path: str, contract: dict[str, Any]) -> bool:
    return code_product_low_signal_target(path, contract)


def _canonical_invalid_code_product_decision_signature(
    decision: dict[str, Any],
    violations: list[Any] | tuple[Any, ...] | None = None,
) -> dict[str, Any]:
    return canonical_invalid_code_product_decision_signature(decision, violations)


def _invalid_decision_signature_key(signature: dict[str, Any]) -> str:
    return invalid_decision_signature_key(signature)


def invalid_code_product_decision_signature_from_history_item(item: dict[str, Any]) -> dict[str, Any]:
    return invalid_code_product_decision_signature_from_history_item(item)


def _invalid_code_product_decision_signature_count(
    history: list[dict[str, Any]],
    signature: dict[str, Any],
) -> int:
    return invalid_code_product_decision_signature_count(history, signature)


def _disallowed_invalid_code_product_signatures(
    validation_rejections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return disallowed_invalid_code_product_signatures(validation_rejections)


def _compact_validation_rejections_tail(
    validation_rejections: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    return compact_validation_rejections_tail(validation_rejections, limit=limit)


def summarize_history_artifacts(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return summarize_history_artifacts(history)


def planner_done_token(raw_text: str) -> bool:
    return planner_done_token(raw_text)


def extract_existing_goal_path(goal: str) -> str:
    return extract_existing_goal_path(goal, repo_root=LAB_REPO, safe_rel_path=safe_rel_path)



# ---------------------------------------------------------------------------
# Planner evidence contract / validation gate
# ---------------------------------------------------------------------------


def requested_file_limit_from_goal(goal: str, default: int = 0) -> int:
    return requested_file_limit_from_goal(goal, default)


def goal_requested_repo_scope(goal: str) -> str:
    return goal_requested_repo_scope(goal, repo_root=LAB_REPO, safe_rel_path=safe_rel_path)


def goal_requests_python_file_review(goal: str) -> bool:
    low = semantic_goal_low(goal)
    wants_python_files = has_any(low, ("python", ".py", "file py", "files py", "file python"))
    wants_read = has_any(low, ("leggi", "read", "analizza", "analizzare", "descrivi", "dimmi", "serve", "servono"))
    wants_explain = has_any(low, ("comportamento", "funzionamento", "cosa serv", "miglior", "improvement", "describe", "purpose"))
    return wants_python_files and wants_read and wants_explain


def _paths_from_result(result: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    raw_paths = result.get("paths_preview") or result.get("paths")
    if isinstance(raw_paths, list):
        paths.extend(str(x) for x in raw_paths if str(x).strip())
    files = result.get("files_preview") or result.get("files")
    if isinstance(files, list):
        for item in files:
            if isinstance(item, dict) and item.get("path"):
                paths.append(str(item.get("path")))
    entries = result.get("entries_preview") or result.get("entries")
    if isinstance(entries, list):
        for item in entries:
            if isinstance(item, dict) and item.get("path"):
                paths.append(str(item.get("path")))
            elif isinstance(item, str) and item.strip():
                paths.append(item)
    items = _list_or_empty(result.get("items"))
    for item in items:
        if isinstance(item, dict) and item.get("path"):
            paths.append(str(item.get("path")))
    out: list[str] = []
    for path in paths:
        n = repo_rel_token(path)
        if n and n not in out:
            out.append(n)
    return out


def _paths_from_list_rows(list_rows: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for row in list_rows if isinstance(list_rows, list) else []:
        if not isinstance(row, dict):
            continue
        for raw in row.get("paths_preview") or []:
            p = repo_rel_token(raw)
            if p and p not in out:
                out.append(p)
    return out


def latest_file_list_result(history: list[dict[str, Any]]) -> dict[str, Any]:
    for item in reversed(history):
        result = history_tool_result(item)
        if result.get("tool") in {"repo_list_files", "repo_tree"} and result.get("ok"):
            return result
    return {}


def successful_repo_read_paths(history: list[dict[str, Any]]) -> list[str]:
    return successful_repo_read_paths(
        history,
        same_tool_artifact_payload=_same_tool_artifact_payload,
    )


def _verified_repo_read_content_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Repo reads whose real content is present in the same successful result.

    Compact history may contain only path metadata or content_preview. The final
    gate must count only read evidence that can be transported to OpenWebUI as a
    real tool result: either the row already has ``content`` or the same
    successful repo_read result's artifact reloads to rows with ``content``.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in history if isinstance(history, list) else []:
        result = history_tool_result(item)
        if result.get("tool") != "repo_read" or result.get("ok") is not True:
            continue
        source = _same_tool_artifact_payload(result)
        raw_items = _list_or_empty(source.get("items"))
        if not raw_items and source.get("path"):
            raw_items = [source]
        for sub in raw_items:
            if not isinstance(sub, dict) or sub.get("ok") is False:
                continue
            path = repo_rel_token(sub.get("path") or sub.get("repo_path") or "")
            if not path or path == ".":
                continue
            text, content_meta = _repo_read_item_full_content(sub)
            if text in (None, ""):
                content = sub.get("content")
                text = str(content or "")
            if not text:
                continue
            if path in seen:
                continue
            seen.add(path)
            out.append(drop_empty_dict_values({
                "path": path,
                "line_count": sub.get("line_count"),
                "truncated": sub.get("truncated"),
                "content_chars": len(text),
                "source": content_meta.get("source") or "repo_read_tool_result",
            }))
    return out


def failed_repo_read_paths(history: list[dict[str, Any]]) -> list[str]:
    return failed_repo_read_paths(history)


def _repo_reference_mentioned(low: str) -> bool:
    return any(term in low for term in (
        "repo", "repository", "progetto", "project", "workspace", "codebase",
        "codice corrente", "current code", "codice nel workspace",
    ))


def _repo_analysis_intent_mentioned(low: str) -> bool:
    return any(term in low for term in (
        "analizza", "anlizza", "analisi", "analyze", "analyse", "analysis",
        "inspect", "inspection", "esplora", "scansiona", "struttura", "structure",
        "overview", "mappa", "review", "audit", "ispeziona", "trova", "trovare",
        "cerca", "ricerca",
    ))


def _repo_analysis_goal(goal: str) -> bool:
    low = goal_operational_intent_text(goal).lower()
    repo_terms = (
        "analyze the repository", "analizza la repo", "analizza il repo",
        "anlizza la repo", "anlizza il repo", "anlizza la repository",
        "repository structure", "repo structure", "struttura repo",
        "analyze repo", "analisi repo", "structure and content",
        "project inspection", "local project evidence", "workspace code",
        "codice corrente", "current code", "codebase",
        "documentation", "documentazione", "docs", "examples", "diagrams",
        "gpu coordination", "heap pointer", "recovery turns",
        "deferred evidence", "packet_review_only", "gpu1", "gpu0",
        "npu sidecar",
    )
    scoped_terms = (
        "analyze the ", "analyse the ", "analizza ", "analisi ",
        "directory", "cartella", "folder", "path",
    )
    if goal_has_write_intent(goal):
        return False
    if input_error_goal(goal):
        return False
    if any(t in low for t in repo_terms):
        return True
    if _repo_reference_mentioned(low) and _repo_analysis_intent_mentioned(low):
        return True
    # Scoped inspection requests such as "analyze the ai_carmine directory" are
    # repository-analysis goals even if they do not say "repository".  Without
    # this, final_allowed falls through to the generic default after one root
    # repo_tree and produces the repeated template answer.
    if goal_requested_repo_scope(goal) and any(t in low for t in scoped_terms):
        return True
    return False


def _should_preseed_root_surface(goal: str, original_args: dict[str, Any]) -> bool:
    """Decide whether the controller should expose root surface evidence first.

    This is deterministic evidence collection for clear, sparse repo-analysis
    goals. It does not choose the next planner action and does not finalize.
    """
    args = original_args if isinstance(original_args, dict) else {}
    requested_function = str(args.get("function") or "").strip()
    if requested_function == "repo_tree":
        return True
    if input_error_goal(goal) or goal_has_write_intent(goal):
        return False
    low = semantic_goal_low(goal)
    generic_repo_terms = (
        "analizza la repo", "analizza il repo", "analizza la repository",
        "anlizza la repo", "anlizza il repo", "anlizza la repository",
        "analisi repo", "analisi della repo", "analisi della repository",
        "analyze repo", "analyze the repo", "analyze the repository",
        "repository analysis", "repo analysis", "repo structure",
        "repository structure", "struttura repo", "struttura della repo",
        "struttura della repository", "project structure", "surface project",
        "suggerimenti implementativi", "implementation suggestions",
        "dai suggerimenti", "find problems", "trova problemi",
    )
    return any(term in low for term in generic_repo_terms) or (
        _repo_reference_mentioned(low) and _repo_analysis_intent_mentioned(low)
    )


def _goal_existing_file_candidates(goal: str) -> list[str]:
    return extract_existing_goal_paths(
        goal,
        repo_root=LAB_REPO,
        safe_rel_path=safe_rel_path,
    )


def _goal_target_file(goal: str) -> str:
    candidates = _goal_existing_file_candidates(goal)
    if not candidates:
        return ""
    # Broad repository-analysis goals often enumerate multiple canonical files.
    # Do not collapse those requests to the first incidental file mention.
    if _repo_analysis_goal(goal) and len(candidates) > 1:
        return ""
    return candidates[0]


def _goal_target_scope(goal: str) -> str:
    return _agentic_v2_goal_scope(goal, {}) or goal_requested_repo_scope(goal)


def _goal_target_kind(goal: str) -> str:
    if _goal_target_file(goal):
        return "file"
    if _goal_target_scope(goal):
        return "directory"
    if _repo_analysis_goal(goal):
        return "repository"
    return "other"


def _controller_memory_target_key(goal: str, contract: dict[str, Any] | None = None) -> str:
    contract = contract if isinstance(contract, dict) else {}
    target_file = str(contract.get("resolved_goal_file") or _goal_target_file(goal) or "")
    if target_file:
        return "file:" + repo_rel_token(target_file)
    target_scope = str(contract.get("resolved_goal_scope") or _goal_target_scope(goal) or "")
    if target_scope:
        return "scope:" + repo_rel_token(target_scope)
    return "repo:root" if _repo_analysis_goal(goal) else "goal:general"


def _planner_prompt_budget_value(default: int = 24000) -> int:
    try:
        return int(AGENTIC_PLANNER_PROMPT_CHAR_BUDGET or default)
    except (ValueError, TypeError):
        return int(default)


def _single_file_prompt_read_chars() -> int:
    budget = _planner_prompt_budget_value()
    return max(2000, min(120000, budget // 4))


def _multi_file_prompt_read_chars() -> int:
    budget = _planner_prompt_budget_value()
    return max(2000, min(64000, budget // 8))


def _controller_preseed_plan(goal: str, original_args: dict[str, Any]) -> dict[str, Any] | None:
    target_file = _goal_target_file(goal)
    if target_file:
        return {
            "event": "controller_preseed_file_surface",
            "result_event": "controller_preseed_file_surface_result",
            "tool": "repo_read",
            "arguments": {"path": target_file, "max_chars": _single_file_prompt_read_chars()},
            "reason": "explicit_file_request_needs_file_surface",
            "artifact_suffix": "file_surface-repo_read",
        }
    target_scope = _goal_target_scope(goal)
    if target_scope:
        return {
            "event": "controller_preseed_scope_surface",
            "result_event": "controller_preseed_scope_surface_result",
            "tool": "repo_list_files",
            "arguments": {"path": target_scope, "limit": 120},
            "reason": "explicit_directory_request_needs_scope_surface",
            "artifact_suffix": "scope_surface-repo_list_files",
        }
    if _should_preseed_root_surface(goal, original_args):
        return {
            "event": "controller_preseed_root_surface",
            "result_event": "controller_preseed_root_surface_result",
            "tool": "repo_tree",
            "arguments": {"path": ".", "max_depth": 2, "max_files": 300},
            "reason": "generic_repo_request_needs_root_surface",
            "artifact_suffix": "root_surface-repo_tree",
            "dynamic_initial_orientation": True,
        }
    return None


def _controller_preplanner_rag_query_plan(goal: str) -> dict[str, Any]:
    return controller_preplanner_rag_query_plan(
        goal,
        post_json=post_json, # pyright: ignore[reportUndefinedVariable]
        planner_url=PLANNER_URL,
        planner_model=PLANNER_MODEL,
        keep_alive=OLLAMA_KEEP_ALIVE,
        num_ctx=AGENTIC_PLANNER_NUM_CTX,
        timeout=AGENTIC_PLANNER_STEP_TIMEOUT,
    )


def _controller_preplanner_rag_preseed_plan(
    goal: str,
    original_args: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any], list[dict[str, Any]]]:
    return controller_preplanner_rag_preseed_plan(
        goal,
        original_args,
        repo_root=LAB_REPO,
        safe_rel_path=safe_rel_path,
        named_read_priority=_NAMED_READ_PRIORITY,
        generic_readable_suffixes=_GENERIC_READABLE_SUFFIXES,
        multi_file_prompt_read_chars=_multi_file_prompt_read_chars(),
    )


def _controller_file_code_product_orientation_preseed_plan(goal: str) -> dict[str, Any] | None:
    if not _goal_target_file(goal) or not goal_requires_code_product_report(goal):
        return None
    return {
        "event": "controller_preseed_file_code_product_orientation",
        "result_event": "controller_preseed_file_code_product_orientation_result",
        "tool": "repo_tree",
        "arguments": {"path": ".", "max_depth": 2, "max_files": 300},
        "reason": "file_code_product_request_needs_dynamic_repo_orientation",
        "artifact_suffix": "file_code_product_orientation-repo_tree",
        "dynamic_initial_orientation": True,
    }


SCOPED_CONCRETE_READ_TARGET = 10
REPO_CONCRETE_READ_TARGET = 20

_NAMED_READ_PRIORITY = {
    "agents.md": 0,
    "readme.md": 1,
}

_INITIAL_DOC_NAME_PRIORITY = {
    "AGENTS.md": 0,
    "README.md": 1,
}

_GENERIC_READABLE_SUFFIXES = (
    ".bat", ".c", ".cfg", ".cmd", ".cpp", ".cs", ".csv", ".go", ".h",
    ".ini", ".java", ".js", ".json", ".jsx", ".kt", ".md", ".ps1", ".py",
    ".rs", ".sh", ".toml", ".ts", ".tsx", ".txt", ".yaml", ".yml",
)


def repo_existing_file(path: str) -> bool:
    return repo_existing_file(path, repo_root=LAB_REPO, safe_rel_path=safe_rel_path)


def repo_existing_dir(path: str) -> bool:
    return repo_existing_dir(path, repo_root=LAB_REPO, safe_rel_path=safe_rel_path)


def root_surface_entries(result: dict[str, Any]) -> list[dict[str, Any]]:
    return root_surface_entries(result, repo_root=LAB_REPO)


def root_surface_file_paths(result: dict[str, Any]) -> list[str]:
    return root_surface_file_paths(result, repo_root=LAB_REPO, safe_rel_path=safe_rel_path)


def root_surface_dir_paths(result: dict[str, Any]) -> list[str]:
    return root_surface_dir_paths(result, repo_root=LAB_REPO, safe_rel_path=safe_rel_path)


def initial_doc_sort_key(path: str) -> tuple[int, int, str]:
    return initial_doc_sort_key(path, named_read_priority=_NAMED_READ_PRIORITY)


def controller_initial_doc_preseed_plan(root_result: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    return controller_initial_doc_preseed_plan(
        root_result,
        repo_root=LAB_REPO,
        safe_rel_path=safe_rel_path,
        named_read_priority=_NAMED_READ_PRIORITY,
        initial_doc_name_priority=_INITIAL_DOC_NAME_PRIORITY,
        scoped_concrete_read_target=SCOPED_CONCRETE_READ_TARGET,
        multi_file_prompt_read_chars=_multi_file_prompt_read_chars(),
    )


def initial_area_sort_key(path: str) -> tuple[int, str]:
    return initial_area_sort_key(path)


def controller_initial_area_list_plans(root_result: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return controller_initial_area_list_plans(
        root_result,
        repo_root=LAB_REPO,
        safe_rel_path=safe_rel_path,
    )


def list_result_file_paths(result: dict[str, Any]) -> list[str]:
    return list_result_file_paths(result, repo_root=LAB_REPO, safe_rel_path=safe_rel_path)


def initial_area_file_sort_key(path: str) -> tuple[int, int, str]:
    return initial_area_file_sort_key(
        path,
        repo_root=LAB_REPO,
        named_read_priority=_NAMED_READ_PRIORITY,
    )


def controller_initial_area_read_plan(list_result: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    return controller_initial_area_read_plan(
        list_result,
        repo_root=LAB_REPO,
        safe_rel_path=safe_rel_path,
        named_read_priority=_NAMED_READ_PRIORITY,
        single_file_prompt_read_chars=_single_file_prompt_read_chars(),
    )


def repo_path_kind(path: str) -> str:
    return repo_path_kind(path, repo_root=LAB_REPO)


def repo_doc_or_config(path: str) -> bool:
    return repo_doc_or_config(path, repo_root=LAB_REPO)


def repo_code_file(path: str) -> bool:
    return repo_code_file(path)


def repo_readable_evidence_file(path: str) -> bool:
    return repo_readable_evidence_file(
        path,
        repo_root=LAB_REPO,
        generic_readable_suffixes=_GENERIC_READABLE_SUFFIXES,
    )


def read_candidate_sort_key(path: str) -> tuple[int, int, int, int, str]:
    return read_candidate_sort_key(
        path,
        repo_root=LAB_REPO,
        named_read_priority=_NAMED_READ_PRIORITY,
    )


def _dynamic_read_candidate_paths(
    paths: list[str],
    *,
    read_ok: set[str] | None = None,
    target_scope: str = "",
) -> list[str]:
    return dynamic_read_candidate_paths(
        paths,
        read_ok=read_ok,
        target_scope=target_scope,
        repo_root=LAB_REPO,
        named_read_priority=_NAMED_READ_PRIORITY,
        generic_readable_suffixes=_GENERIC_READABLE_SUFFIXES,
    )


def scope_candidate_source_paths(list_rows: list[dict[str, Any]], target_scope: str) -> list[str]:
    return scope_candidate_source_paths(list_rows, target_scope)


def scope_read_candidates_from_evidence(
    list_rows: list[dict[str, Any]],
    target_scope: str,
    *,
    read_ok: list[str] | set[str] | None = None,
) -> list[str]:
    return scope_read_candidates_from_evidence(
        list_rows,
        target_scope,
        read_ok=read_ok,
        repo_root=LAB_REPO,
        named_read_priority=_NAMED_READ_PRIORITY,
        generic_readable_suffixes=_GENERIC_READABLE_SUFFIXES,
    )


def meaningful_read_candidates_from_evidence(
    list_rows: list[dict[str, Any]],
    *,
    read_ok: list[str] | set[str] | None = None,
) -> list[str]:
    return meaningful_read_candidates_from_evidence(
        list_rows,
        read_ok=read_ok,
        repo_root=LAB_REPO,
        named_read_priority=_NAMED_READ_PRIORITY,
        generic_readable_suffixes=_GENERIC_READABLE_SUFFIXES,
    )


def scoped_required_read_count(available_candidates: list[str]) -> int:
    if not available_candidates:
        return 1
    return min(SCOPED_CONCRETE_READ_TARGET, len(available_candidates))


def _repo_required_read_count(available_candidates: list[str]) -> int:
    if not available_candidates:
        return 1
    return min(REPO_CONCRETE_READ_TARGET, len(available_candidates))


def top_dir(path: str) -> str:
    return top_dir(path)


def low_signal_top_dir(path: str) -> bool:
    return low_signal_top_dir(path)


def append_unique(seq: list[Any], value: Any) -> None:
    append_unique(seq, value)


def read_items_from_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return read_items_from_history(history, same_tool_artifact_payload=_same_tool_artifact_payload)


def extract_headings(content: str) -> list[str]:
    return extract_headings(content)


def _extract_key_lines(content: str) -> list[str]:
    return extract_key_lines(content)


def extract_mentioned_paths(content: str) -> list[str]:
    return extract_mentioned_paths(content)


def _file_memory_from_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return file_memory_from_history(history, same_tool_artifact_payload=_same_tool_artifact_payload)


def _repo_list_evidence(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return repo_list_evidence(history, same_tool_artifact_payload=_same_tool_artifact_payload)


def failed_repo_list_files_paths(history: list[dict[str, Any]]) -> list[str]:
    return failed_repo_list_files_paths(history)


def _rank_core_candidates(file_memory: list[dict[str, Any]], list_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return rank_core_candidates(
        file_memory,
        list_rows,
        repo_root=LAB_REPO,
        safe_rel_path=safe_rel_path,
    )


def normalize_scope_claim_text(text: str) -> str:
    return normalize_scope_claim_text(text)


def claim_area_from_user_token(raw_area: str, target_scope: str = "") -> str:
    return claim_area_from_user_token(
        raw_area,
        target_scope,
        path_exists_repo_relative=_path_exists_repo_relative,
    )


def _user_scope_claims(goal: str, target_scope: str = "") -> list[dict[str, Any]]:
    return user_scope_claims(
        goal,
        target_scope,
        path_exists_repo_relative=_path_exists_repo_relative,
    )


def _scope_claim_conflict_for_path(path: str, claims: list[dict[str, Any]]) -> dict[str, Any]:
    return scope_claim_conflict_for_path(path, claims)


def add_core_discovery_candidate(
    out: list[dict[str, Any]],
    seen: set[str],
    *,
    path: str,
    source: str,
    rank: int,
    reason: str,
    read_ok: set[str],
    target_scope: str,
    user_scope_claims: list[dict[str, Any]],
    score: Any = None,
    ranking_source: str = "",
) -> bool:
    return add_core_discovery_candidate(
        out,
        seen,
        path=path,
        source=source,
        rank=rank,
        reason=reason,
        read_ok=read_ok,
        target_scope=target_scope,
        user_scope_claims=user_scope_claims,
        lab_repo_label=str(LAB_REPO),
        path_under_scope=_path_under_scope,
        path_exists_repo_relative=_path_exists_repo_relative,
        repo_readable_evidence_file=repo_readable_evidence_file,
        score=score,
        ranking_source=ranking_source,
    )


def _core_discovery_candidates_from_intrinsic(
    *,
    intrinsic_context: dict[str, Any] | None,
    list_rows: list[dict[str, Any]],
    read_ok: list[str],
    target_scope: str,
    user_scope_claims: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return core_discovery_candidates_from_intrinsic(
        intrinsic_context=intrinsic_context,
        list_rows=list_rows,
        read_ok=read_ok,
        target_scope=target_scope,
        user_scope_claims=user_scope_claims,
        lab_repo_label=str(LAB_REPO),
        path_under_scope=_path_under_scope,
        path_exists_repo_relative=_path_exists_repo_relative,
        repo_readable_evidence_file=repo_readable_evidence_file,
        scope_read_candidates_from_evidence=lambda rows, scope, read_ok_set: scope_read_candidates_from_evidence(
            rows,
            scope,
            read_ok=read_ok_set,
        ),
        meaningful_read_candidates_from_evidence=lambda rows, read_ok_set: meaningful_read_candidates_from_evidence(
            rows,
            read_ok=read_ok_set,
        ),
    )


def _core_discovery_read_paths(
    candidates: list[dict[str, Any]] | None,
    *,
    read_ok: set[str],
    target_scope: str,
    limit: int,
) -> list[str]:
    return core_discovery_read_paths(
        candidates,
        read_ok=read_ok,
        target_scope=target_scope,
        limit=limit,
        path_under_scope=_path_under_scope,
        path_exists_repo_relative=_path_exists_repo_relative,
        repo_readable_evidence_file=repo_readable_evidence_file,
    )


SCOPE_CONFLICT_RATIONALE_TERMS = None


def _target_scope_conflict_resolved(path: str, args: dict[str, Any], contract: dict[str, Any]) -> bool:
    return target_scope_conflict_resolved(path, args, contract)


def _candidate_actions_from_evidence(
    goal: str,
    file_memory: list[dict[str, Any]],
    list_rows: list[dict[str, Any]],
    read_ok: list[str],
    final_allowed: bool,
    failed_list_paths: list[str] | None = None,
    core_discovery_candidates: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    return candidate_actions_from_evidence(
        goal,
        file_memory,
        list_rows,
        read_ok,
        final_allowed,
        failed_list_paths=failed_list_paths,
        core_discovery_candidates=core_discovery_candidates,
        repo_rel_token=repo_rel_token,
        repo_analysis_goal=_repo_analysis_goal,
        repo_doc_or_config=repo_doc_or_config,
        low_signal_top_dir=low_signal_top_dir,
        rank_core_candidates=_rank_core_candidates,
        path_exists_repo_relative=_path_exists_repo_relative,
        goal_target_scope=_goal_target_scope,
        input_error_goal=input_error_goal,
        path_under_scope=_path_under_scope,
        core_discovery_read_paths=_core_discovery_read_paths,
        scoped_concrete_read_target=SCOPED_CONCRETE_READ_TARGET,
        repo_concrete_read_target=REPO_CONCRETE_READ_TARGET,
        scope_read_candidates_from_evidence=scope_read_candidates_from_evidence,
        multi_file_prompt_read_chars=_multi_file_prompt_read_chars,
        meaningful_read_candidates_from_evidence=meaningful_read_candidates_from_evidence,
        single_file_prompt_read_chars=_single_file_prompt_read_chars,
        repo_code_file=repo_code_file,
        repo_readable_evidence_file=repo_readable_evidence_file,
    )



def _build_operational_notebook(goal: str, contract: dict[str, Any]) -> dict[str, Any]:
    memory = _list_or_empty(contract.get("file_memory"))
    list_rows = _list_or_empty(contract.get("repo_list_files_evidence"))
    core = _list_or_empty(contract.get("ranked_core_candidate_dirs"))
    final_contract = _dict_or_empty(contract.get("finalization_contract"))
    final_allowed = bool(final_contract.get("final_allowed"))
    validation_rejections_tail = _list_or_empty(contract.get("validation_rejections_tail"))
    return {
        "schema": "agentic_loop_operational_notes.v1",
        "goal": goal,
        "final_allowed": final_allowed,
        "next_instruction": (
            "Quality gate is satisfied and final is allowed, not required. Prefer final from read_notes, "
            "mentioned_paths, core_candidates, workflow/problems evidence, and limits when no concrete "
            "evidence gap remains; otherwise name the gap and choose one selective evidence-bound tool."
            if final_allowed else
            "Continue only with one evidence-bound unread doc/code candidate. Do not repeat prior tool calls."
        ),
        "read_notes": [
            {
                "path": item.get("path"),
                "headings": (item.get("headings") or [])[:8],
                "key_lines": (item.get("key_lines") or [])[:10],
                "mentioned_paths": (item.get("mentioned_paths") or [])[:14],
                "excerpt": str(item.get("content_excerpt") or "")[:700],
            }
            for item in memory[:18]
            if isinstance(item, dict)
        ],
        "list_notes": list_rows[-8:],
        "core_candidates": core[:8],
        "candidate_next_actions": contract.get("candidate_next_actions") or [],
        "recent_rejections": validation_rejections_tail[-8:],
        "known_problem": (
            "Do not reduce this job to path counters or directory names. Use read_notes as the working scratchpad "
            "and cite concrete evidence from them."
        ),
    }


def _initial_orientation_surface_from_history(
    history: list[dict[str, Any]],
    skipped: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return initial_orientation_surface_from_history(
        history,
        skipped,
        repo_rel_token=repo_rel_token,
        repo_doc_or_config=repo_doc_or_config,
        low_signal_top_dir=low_signal_top_dir,
        path_under_scope=_path_under_scope,
    )


# ---------------------------------------------------------------------------
# Planner evidence contract / validation gate
# ---------------------------------------------------------------------------


def planner_evidence_contract(
    goal: str,
    history: list[dict[str, Any]],
    intrinsic_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return  _planner_evidence_contract_impl(
        goal,
        history,
        intrinsic_context,
        deps={
            "agentic_v2_decision_paths": _agentic_v2_decision_paths,
            "agentic_v2_enrich_evidence_contract": _agentic_v2_enrich_evidence_contract,
            "agentic_v2_goal_scope": _agentic_v2_goal_scope,
            "apply_turn_surface_policy": apply_turn_surface_policy,
            "build_operational_notebook": _build_operational_notebook,
            "candidate_actions_from_evidence": _candidate_actions_from_evidence,
            "canonical_invalid_code_product_decision_signature": _canonical_invalid_code_product_decision_signature,
            "code_product_action_has_complete_payload": code_product_action_has_complete_payload,
            "code_product_build_state_propose_action": _code_product_build_state_propose_action,
            "code_product_build_state_read_action": _code_product_build_state_read_action,
            "code_product_build_state_write_action": _code_product_build_state_write_action,
            "code_product_candidate_action": _code_product_candidate_action,
            "code_product_payload_rejection_count": _code_product_payload_rejection_count,
            "code_product_payload_violations": code_product_payload_violations,
            "code_product_source_window_candidate": _code_product_source_window_candidate,
            "compact_validation_rejections_tail": _compact_validation_rejections_tail,
            "core_discovery_candidates_from_intrinsic": _core_discovery_candidates_from_intrinsic,
            "disallowed_invalid_code_product_signatures": _disallowed_invalid_code_product_signatures,
            "failed_code_edit_proposal_validation_row": failed_code_edit_proposal_validation_row,
            "file_memory_from_history": _file_memory_from_history,
            "goal_exact_text_block": goal_exact_text_block,
            "goal_target_file": _goal_target_file,
            "goal_target_kind": _goal_target_kind,
            "initial_orientation_surface_from_history": _initial_orientation_surface_from_history,
            "input_error_goal": input_error_goal,
            "latest_code_product_build_state": latest_code_product_build_state,
            "low_signal_top_dir": low_signal_top_dir,
            "meaningful_read_candidates_from_evidence": meaningful_read_candidates_from_evidence,
            "path_exists_repo_relative": _path_exists_repo_relative,
            "path_under_scope": _path_under_scope,
            "paths_from_list_rows": _paths_from_list_rows,
            "paths_from_result": _paths_from_result,
            "planner_scratchpad_window_signature": planner_scratchpad_window_signature,
            "rank_core_candidates": _rank_core_candidates,
            "repo_analysis_goal": _repo_analysis_goal,
            "repo_code_file": repo_code_file,
            "repo_doc_or_config": repo_doc_or_config,
            "repo_list_evidence": repo_list_evidence,
            "repo_read_window_signature": repo_read_window_signature,
            "repo_readable_evidence_file": repo_readable_evidence_file,
            "repo_rel_token": repo_rel_token,
            "repo_required_read_count": _repo_required_read_count,
            "scope_read_candidates_from_evidence": scope_read_candidates_from_evidence,
            "scoped_required_read_count": scoped_required_read_count,
            "user_scope_claims": _user_scope_claims,
            "verified_repo_read_content_rows": _verified_repo_read_content_rows,
            "goal_requested_repo_scope": goal_requested_repo_scope,
            "goal_requires_code_security_coverage": goal_requires_code_security_coverage,
            "goal_requests_apply": goal_requests_apply,
            "goal_requests_code_product": goal_requests_code_product,
            "goal_requests_python_file_review": goal_requests_python_file_review,
            "history_has_tool": history_has_tool,
            "latest_file_list_result": latest_file_list_result,
            "requested_file_limit_from_goal": requested_file_limit_from_goal,
            "semantic_goal_classification": semantic_goal_classification,
            "successful_window_signatures": _successful_window_signatures,
            "successful_code_edit_proposals": successful_code_edit_proposals,
            "successful_repo_read_paths": successful_repo_read_paths,
            "failed_repo_read_paths": failed_repo_read_paths,
            "failed_repo_list_files_paths": failed_repo_list_files_paths,
        },
        config={
            "CODE_PRODUCT_BUILD_STATE_KIND": CODE_PRODUCT_BUILD_STATE_KIND,
            "LAB_REPO": LAB_REPO,
            "REPO_CONCRETE_READ_TARGET": REPO_CONCRETE_READ_TARGET,
            "SCOPED_CONCRETE_READ_TARGET": SCOPED_CONCRETE_READ_TARGET,
        },
    )

def _path_exists_repo_relative(path: str) -> bool:
    try:
        rel = safe_rel_path(path)
        full = (LAB_REPO / rel).resolve(strict=False)
        full.relative_to(LAB_REPO)
        return full.exists()
    except Exception:
        return False


def _path_under_scope(path: str, scope: str) -> bool:
    return path_under_scope(path, scope)


def _argument_value_present(args: dict[str, Any], key: str) -> bool:
    value = (args if isinstance(args, dict) else {}).get(key)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def _argument_group_present(args: dict[str, Any], keys: list[str] | tuple[str, ...]) -> bool:
    return all(_argument_value_present(args, str(key)) for key in keys)


def _any_argument_group_present(args: dict[str, Any], groups: list[list[str]] | tuple[tuple[str, ...], ...]) -> bool:
    return any(_argument_group_present(args, [str(key) for key in group]) for group in groups)


def _planner_scratchpad_read_selector_present(args: dict[str, Any]) -> bool:
    args = args if isinstance(args, dict) else {}
    kind = str(args.get("kind") or "")
    if kind in {"prompt_context_window", CODE_PRODUCT_BUILD_STATE_KIND}:
        return _any_argument_group_present(
            args,
            [["document_id"], ["section"], ["tag"], ["query"], ["target_file"]],
        )
    return _any_argument_group_present(
        args,
        [["document_id"], ["section"], ["tag"], ["query"], ["kind"]],
    )


def _repo_read_selector_present(args: dict[str, Any]) -> bool:
    return _any_argument_group_present(
        args if isinstance(args, dict) else {},
        [["path"], ["paths"], ["item"], ["items"]],
    )


def _native_required_tool_decision_has_transport_provenance(decision: dict[str, Any]) -> bool:
    if decision.get("native_tool_call") is not True:
        return False
    return isinstance(decision.get("raw_native_tool_call"), dict)


def _native_required_repaired_tool_decision_disallowed(decision: dict[str, Any]) -> bool:
    action = str((decision if isinstance(decision, dict) else {}).get("action") or "").strip().lower()
    return bool(
        AGENTIC_PLANNER_NATIVE_TOOLS
        and action == "tool"
    )


def _verified_repo_read_contents_for_path(history: list[dict[str, Any]], target_file: str) -> list[str]:
    target = repo_rel_token(target_file)
    if not target or target == ".":
        return []
    out: list[str] = []
    seen_hashes: set[str] = set()
    for item in history if isinstance(history, list) else []:
        result = history_tool_result(item)
        if result.get("tool") != "repo_read" or result.get("ok") is not True:
            continue
        source = _same_tool_artifact_payload(result)
        raw_items = _list_or_empty(source.get("items"))
        if not raw_items and source.get("path"):
            raw_items = [source]
        for sub in raw_items:
            if not isinstance(sub, dict) or sub.get("ok") is False:
                continue
            path = repo_rel_token(sub.get("path") or sub.get("repo_path") or "")
            if path != target:
                continue
            text, _content_meta = _repo_read_item_full_content(sub)
            if not text:
                text = str(sub.get("content") or "")
            if not text:
                continue
            digest = text_hash(text)
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)
            out.append(text)
    return out


def _old_text_verified_by_repo_read(history: list[dict[str, Any]], target_file: str, old_text: Any) -> bool:
    if not isinstance(old_text, str) or not old_text:
        return False
    return any(old_text in content for content in _verified_repo_read_contents_for_path(history, target_file))


def _apply_unverified_old_text_replan_contract(
    contract: dict[str, Any],
    *,
    target_file: str,
    violation: str,
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    target = repo_rel_token(target_file)
    def admissible_replan_candidate(item: Any) -> bool:
        if not isinstance(item, dict):
            return False
        tool_name = str(item.get("tool") or "")
        arguments = _dict_or_empty(item.get("arguments"))
        if tool_name == "planner_scratchpad_read":
            return True
        if tool_name == "repo_read":
            return target in {
                repo_rel_token(path)
                for path in _agentic_v2_decision_paths(tool_name, arguments)
            }
        if tool_name == "planner_scratchpad_write" and arguments.get("kind") == CODE_PRODUCT_BUILD_STATE_KIND:
            text = str(arguments.get("text") or arguments.get("content") or "")
            state = code_product_build_state_parse(text)
            return bool(
                state
                and (
                    code_product_build_state_has_collecting_progress(state)
                    or code_product_build_state_ready_payload(state)
                    or (
                        str(state.get("status") or "") == "blocked_incomplete"
                        and str(state.get("blocker") or "").strip()
                    )
                )
            )
        if item.get("action") == "block":
            return True
        return False

    existing = [
        item for item in (contract.get("candidate_next_actions") or [])
        if admissible_replan_candidate(item)
    ]
    preferred: list[dict[str, Any]] = []
    for item in existing:
        tool_name = str(item.get("tool") or "")
        if tool_name == "planner_scratchpad_read":
            preferred.append(item)
        elif tool_name == "repo_read" and target in {
            repo_rel_token(path)
            for path in _agentic_v2_decision_paths(
                tool_name,
                item.get("arguments") if isinstance(item.get("arguments"), dict) else {},
            )
        }:
            preferred.append(item)
    route_candidate = _code_product_source_window_candidate(target, history=history)
    if route_candidate:
        preferred.insert(0, route_candidate)
    if not preferred:
        preferred.append(
            {
                "action": "block",
                "reason": "code_product_old_text_not_verifiable",
                "final_answer": (
                    f"{violation}: old_text is not verified in repo_read content for {target}. "
                    "No further source window is available; cannot build a valid diff."
                ),
            }
        )
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in [*preferred, *existing]:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    contract["candidate_next_actions"] = merged[:15]
    contract["required_next_progress"] = (
        f"{violation}. Change decision now: use a real planner_scratchpad_read window from "
        "required_working_set/candidate_next_actions if available, otherwise read a useful target "
        "window or return a typed block. Do not repeat placeholder old_text/new_text."
    )
    return contract


def repo_analysis_final_answer_model_quality(
    final_answer: str,
    contract: dict[str, Any],
    *,
    goal: str,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    request = repo_analysis_final_answer_model_quality_request(
        final_answer,
        contract,
        goal=goal,
    )
    user_payload = _dict_or_empty(request.get("user_payload"))
    options = {
        "temperature": GLOBAL_TEMPERATURE,
        "num_predict": 1000,
        "num_ctx": max(
            4096,
            min(int(AGENTIC_PLANNER_NUM_CTX_CAP or AGENTIC_PLANNER_NUM_CTX or 8192), int(AGENTIC_PLANNER_NUM_CTX or 8192)),
        ),
    }
    payload = {
        "model": PLANNER_MODEL,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "think": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": str(request.get("system") or "")},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, default=str)},
        ],
        "options": options,
    }
    timeout_seconds = min(90, max(20, int(AGENTIC_PLANNER_STEP_TIMEOUT or 30)))
    response = post_json(PLANNER_URL, payload, timeout_seconds) # pyright: ignore[reportUndefinedVariable]
    if response.get("backend_unreachable") or response.get("backend_timeout") or response.get("error"):
        quality = sanitize_repo_analysis_final_model_quality(None, contract)
        quality.update({
            "violations": ["repo_analysis_final_model_quality_unavailable"],
            "required_next_progress": (
                "Final answer rejected because the model final-quality judge was unavailable. "
                "Retry final-quality evaluation; do not accept the final through deterministic heuristics."
            ),
            "planner_model": PLANNER_MODEL,
            "planner_url": PLANNER_URL,
            "timeout_seconds": timeout_seconds,
            "backend_error": response.get("error") or response.get("error_type") or "planner_backend_error",
        })
        return quality

    message = _dict_or_empty(response.get("message"))
    raw_text = str(message.get("content") or response.get("response") or response.get("partial_content") or "")
    parse_diagnostics = parse_strict_json_object_diagnostics(raw_text) # pyright: ignore[reportUndefinedVariable]
    repaired_raw_text = ""
    repair_diagnostics: dict[str, Any] = {}
    decoded = parse_diagnostics.get("decoded") if parse_diagnostics.get("ok") is True else {}
    if (
        not decoded
        or str(decoded.get("decision") or "").strip().lower()
        not in {"accept", "reject", "continue_required"}
    ):
        repair_payload = {
            "model": PLANNER_MODEL,
            "stream": False,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "think": False,
            "format": "json",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        str(request.get("system") or "")
                        + "\n\nThe previous final-quality judge response was invalid JSON. "
                        "Re-evaluate the same request now and return exactly one strict JSON object."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "schema": "repo_analysis_final_model_quality_repair_request.v1",
                            "original_request": user_payload,
                            "invalid_response_preview": raw_text[:2000],
                            "invalid_response_chars": len(raw_text),
                            "json_parse_error_type": parse_diagnostics.get("error_type"),
                            "json_parse_error": parse_diagnostics.get("error"),
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                },
            ],
            "options": options,
        }
        repair_response = post_json(PLANNER_URL, repair_payload, timeout_seconds) # pyright: ignore[reportUndefinedVariable]
        repair_diagnostics = {
            "attempted": True,
            "planner_model": PLANNER_MODEL,
            "planner_url": PLANNER_URL,
            "timeout_seconds": timeout_seconds,
        }
        if (
            repair_response.get("backend_unreachable")
            or repair_response.get("backend_timeout")
            or repair_response.get("error")
        ):
            repair_diagnostics.update({
                "ok": False,
                "error": repair_response.get("error") or repair_response.get("error_type") or "planner_backend_error",
                "error_type": repair_response.get("error_type"),
            })
        else:
            repair_message = _dict_or_empty(repair_response.get("message"))
            repaired_raw_text = str(
                repair_message.get("content")
                or repair_response.get("response")
                or repair_response.get("partial_content")
                or ""
            )
            repair_parse = parse_strict_json_object_diagnostics(repaired_raw_text) # pyright: ignore[reportUndefinedVariable]
            repair_diagnostics.update({
                "ok": repair_parse.get("ok") is True,
                "raw_response_chars": len(repaired_raw_text),
            })
            if repair_parse.get("ok") is True:
                decoded = repair_parse.get("decoded") if isinstance(repair_parse.get("decoded"), dict) else {}
            else:
                repair_diagnostics.update({
                    "json_parse_error_type": repair_parse.get("error_type"),
                    "json_parse_error": repair_parse.get("error"),
                    "raw_response_preview": repaired_raw_text[:2000],
                })
    quality = sanitize_repo_analysis_final_model_quality(decoded, contract)
    quality.update({
        "planner_model": PLANNER_MODEL,
        "planner_url": PLANNER_URL,
        "timeout_seconds": timeout_seconds,
    })
    if repair_diagnostics:
        quality["json_repair_attempt"] = repair_diagnostics
        if quality.get("model_decision_available"):
            quality["json_repaired_by_final_quality_model"] = True
    if not quality.get("model_decision_available"):
        quality["raw_response_preview"] = raw_text[:2000]
        quality["raw_response_chars"] = len(raw_text)
        if parse_diagnostics.get("ok") is not True:
            quality["json_parse_error_type"] = parse_diagnostics.get("error_type")
            if parse_diagnostics.get("error") not in (None, "", [], {}):
                quality["json_parse_error"] = parse_diagnostics.get("error")
        quality["violations"] = ["repo_analysis_final_model_quality_invalid"]
        quality["required_next_progress"] = (
            "Final answer rejected because the model final-quality judge did not return valid JSON. "
            "Retry final-quality evaluation; do not accept the final through deterministic heuristics."
        )
    history_for_audit = history if isinstance(history, list) else []
    required_route = (
        quality.get("required_next_tool_call")
        if isinstance(quality.get("required_next_tool_call"), dict)
        else {}
    )
    if required_route:
        route_audit = _specialist_route_audit(
            required_route,
            history_for_audit,
            source="repo_analysis_final_quality",
            allowed_tools=_FINAL_QUALITY_ROUTE_TOOLS,
        )
        if route_audit.get("accepted") is not True:
            retry_user_payload = dict(user_payload)
            retry_rules = retry_user_payload.get("decision_rules")
            retry_rules = list(retry_rules) if isinstance(retry_rules, list) else []
            retry_rules.append(
                "A previous required_next_tool_call failed prevalidation. Do not repeat it. "
                "Choose one different valid route, or omit required_next_tool_call and require "
                "a corrected final answer from existing evidence."
            )
            retry_user_payload["decision_rules"] = retry_rules
            retry_user_payload["prevalidation_feedback"] = prompt_clip_value(
                route_audit,
                text_limit=900,
                list_limit=8,
            )
            retry_payload = {
                "model": PLANNER_MODEL,
                "stream": False,
                "keep_alive": OLLAMA_KEEP_ALIVE,
                "think": False,
                "format": "json",
                "messages": [
                    {"role": "system", "content": str(request.get("system") or "")},
                    {"role": "user", "content": json.dumps(retry_user_payload, ensure_ascii=False, default=str)},
                ],
                "options": options,
            }
            retry_response = post_json(PLANNER_URL, retry_payload, timeout_seconds) # pyright: ignore[reportUndefinedVariable]
            retry_quality: dict[str, Any]
            retry_audit: dict[str, Any] = {}
            if (
                retry_response.get("backend_unreachable")
                or retry_response.get("backend_timeout")
                or retry_response.get("error")
            ):
                retry_quality = sanitize_repo_analysis_final_model_quality(None, contract)
                retry_quality["backend_error"] = (
                    retry_response.get("error")
                    or retry_response.get("error_type")
                    or "planner_backend_error"
                )
            else:
                retry_message = _dict_or_empty(retry_response.get("message"))
                retry_raw_text = str(
                    retry_message.get("content")
                    or retry_response.get("response")
                    or retry_response.get("partial_content")
                    or ""
                )
                retry_parse = parse_strict_json_object_diagnostics(retry_raw_text) # pyright: ignore[reportUndefinedVariable]
                retry_decoded = retry_parse.get("decoded") if retry_parse.get("ok") is True else {}
                retry_quality = sanitize_repo_analysis_final_model_quality(retry_decoded, contract)
                retry_quality["raw_response_preview"] = retry_raw_text[:1200]
                retry_quality["raw_response_chars"] = len(retry_raw_text)
                if retry_parse.get("ok") is not True:
                    retry_quality["json_parse_error_type"] = retry_parse.get("error_type")
            retry_route = (
                retry_quality.get("required_next_tool_call")
                if isinstance(retry_quality.get("required_next_tool_call"), dict)
                else {}
            )
            if retry_route:
                retry_audit = _specialist_route_audit(
                    retry_route,
                    history_for_audit,
                    source="repo_analysis_final_quality_retry",
                    allowed_tools=_FINAL_QUALITY_ROUTE_TOOLS,
                )
            if retry_route and retry_audit.get("accepted") is True:
                quality = retry_quality
                quality["judge_route_prevalidation_retry"] = {
                    "attempted": True,
                    "first_audit": route_audit,
                    "retry_audit": retry_audit,
                    "accepted": True,
                }
            else:
                quality["stale_or_invalid_judge_route"] = {
                    "attempted_retry": True,
                    "first_audit": route_audit,
                    "retry_audit": retry_audit,
                    "retry_quality": prompt_clip_value(retry_quality, text_limit=700, list_limit=8),
                }
                quality.pop("required_next_tool_call", None)
                quality["required_next_progress"] = (
                    "Final-quality judge route was stale or invalid after one retry. "
                    "Rewrite action=final from existing verified evidence if sufficient, "
                    "choose a different concrete evidence gap, or return a typed action=block."
                )
    return quality


def validate_planner_decision_against_evidence(
    goal: str,
    decision: dict[str, Any],
    history: list[dict[str, Any]],
    require_native_tool_call: bool = False,
) -> dict[str, Any]:
    return validate_planner_decision_against_evidence(
        goal,
        decision,
        history,
        require_native_tool_call=require_native_tool_call,
        deps={
            "agentic_v2_decision_paths": _agentic_v2_decision_paths,
            "agentic_v2_goal_scope": _agentic_v2_goal_scope,
            "agentic_v2_read_has_window": _agentic_v2_read_has_window,
            "agentic_v2_successful_read_paths": _agentic_v2_successful_read_paths,
            "any_argument_group_present": _any_argument_group_present,
            "apply_duplicate_window_replan_contract": _apply_duplicate_window_replan_contract,
            "apply_unverified_old_text_replan_contract": _apply_unverified_old_text_replan_contract,
            "argument_value_present": _argument_value_present,
            "canonical_invalid_code_product_decision_signature": _canonical_invalid_code_product_decision_signature,
            "code_product_build_state_duplicate_write": _code_product_build_state_duplicate_write,
            "code_product_build_state_has_collecting_progress": code_product_build_state_has_collecting_progress,
            "code_product_build_state_parse": code_product_build_state_parse,
            "code_product_build_state_ready_payload": code_product_build_state_ready_payload,
            "code_product_low_signal_target": _code_product_low_signal_target,
            "code_product_payload_violations": code_product_payload_violations,
            "contract_final_required_now": contract_final_required_now,
            "copyable_example_text": copyable_example_text,
            "decision_matches_prompt_context_continuation": _decision_matches_prompt_context_continuation,
            "decision_paths": decision_paths,
            "enforce_required_scratchpad_read_continuation_contract": (
                _enforce_required_scratchpad_read_continuation_contract
            ),
            "final_answer_is_action_plan_without_code_product": final_answer_is_action_plan_without_code_product,
            "final_composition_tool_names_from_candidates": final_composition_tool_names_from_candidates,
            "repo_analysis_final_answer_model_quality": repo_analysis_final_answer_model_quality,
            "repo_analysis_final_answer_quality": repo_analysis_final_answer_quality,
            "goal_requires_code_product_report": goal_requires_code_product_report,
            "invalid_code_product_decision_signature_count": _invalid_code_product_decision_signature_count,
            "invalid_decision_signature_key": _invalid_decision_signature_key,
            "native_required_tool_decision_has_transport_provenance": _native_required_tool_decision_has_transport_provenance,
            "normalize_terminal_planner_decision": _normalize_terminal_planner_decision,
            "normalize_tool_name": _normalize_tool_name,
            "old_text_verified_by_repo_read": _old_text_verified_by_repo_read,
            "path_exists_repo_relative": _path_exists_repo_relative,
            "path_under_scope": _path_under_scope,
            "planner_scratchpad_read_selector_present": _planner_scratchpad_read_selector_present,
            "planner_scratchpad_window_signature": planner_scratchpad_window_signature,
            "prompt_window_consumed_offsets": _prompt_window_consumed_offsets,
            "prompt_window_tracking_metadata_errors": _prompt_window_tracking_metadata_errors,
            "repo_analysis_goal": _repo_analysis_goal,
            "repo_path_kind": repo_path_kind,
            "repo_read_selector_present": _repo_read_selector_present,
            "repo_read_window_signature": repo_read_window_signature,
            "repo_readable_evidence_file": repo_readable_evidence_file,
            "repo_rel_token": repo_rel_token,
            "repeated_tool_call_count": repeated_tool_call_count, # pyright: ignore[reportUndefinedVariable]
            "scope_claim_conflict_for_path": _scope_claim_conflict_for_path,
            "successful_window_signatures": _successful_window_signatures,
            "target_scope_conflict_resolved": _target_scope_conflict_resolved,
            "latest_file_list_result": latest_file_list_result,
            "planner_evidence_contract": planner_evidence_contract,
            "successful_code_edit_proposals": successful_code_edit_proposals,
            "validate_unified_diff_text": validate_unified_diff_text,
        },
        config={
            "AGENTIC_PLANNER_NATIVE_TOOLS": AGENTIC_PLANNER_NATIVE_TOOLS,
            "CODE_PRODUCT_BUILD_STATE_KIND": CODE_PRODUCT_BUILD_STATE_KIND,
            "VALID_INTERNAL_TOOLS": VALID_INTERNAL_TOOLS,
            "AICARMINE_ORIENTATION_LANE_MODE": AICARMINE_ORIENTATION_LANE_MODE,
        },
    )



def _decision_raw_planner_text(decision: dict[str, Any]) -> str:
    if not isinstance(decision, dict):
        return ""
    return str(
        decision.get("raw_planner_text")
        or decision.get("raw_planner_text_preview")
        or decision.get("partial_content")
        or ""
    )


# --- Vulkan repair, CUDA rewrite, controller guard ---
# NOTE: Core helper functions extracted to application/planner/vulkan_repair.py


def vulkan_repair_invalid_planner_decision(
    *,
    goal: str,
    step: int,
    decision: dict[str, Any],
    validation: dict[str, Any],
    history: list[dict[str, Any]],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Ask Vulkan/GPU0 11435 for one explicit repair of the planner emission.

    This is not a hidden controller fallback. 11435 receives the original
    planner emission/proposal and must return one pure JSON decision. The raw
    planner output is preserved and surfaced even when repair succeeds.
    """
    raw_planner_text = _decision_raw_planner_text(decision)
    repair_key = _repair_cache_key(raw_planner_text)
    if _vulkan_repair_seen(history) >= 1:
        return {
            "ok": False,
            "error": "vulkan_repair_already_attempted_for_this_job",
            "raw_planner_text_preview": raw_planner_text[:2000],
            "repair_cache_key": repair_key,
            "repaired_decision": None,
        }

    payload = {
        "model": OLLAMA_TASK_MODEL,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "think": False,
        "format": "json",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Sei il lane Vulkan/GPU0/11435 di riparazione esplicita del loop. "
                    "Non scegliere tu una sequenza deterministica. Non nascondere errori. "
                    "Ricevi una emissione/proposta del planner e devi restituire UN SOLO "
                    "oggetto JSON puro con action=tool|final|block. "
                    "Se la emissione contiene una risposta naturale utile, mettila dentro "
                    "final_answer. Se contiene una tool call utile, correggi solo il JSON. "
                    "Se non puoi riparare senza inventare, ritorna action=block con final_answer."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({
                    "task": "explicit_vulkan_gpu0_repair_planner_emission",
                    "goal": goal,
                    "step": step,
                    "original_planner_decision": decision,
                    "raw_planner_text": raw_planner_text[:20000],
                    "validator_violations": validation.get("violations"),
                    "repair_role_guidance": role_guidance_for_goal("repair", goal),
                    "evidence_contract": _compact_vulkan_repair_evidence_contract(
                        _dict_or_empty(validation.get("evidence_contract"))
                    ),
                    "evidence_contract_bounded_for_repair": True,
                    "history_tail": _compact_repair_history(history),
                    "available_tools": internal_tool_prompt(exclude_vulkan=False),
                    "rules": [
                        "Return pure JSON only; no markdown fences, no prose outside JSON.",
                        "Do not invent paths or claim files were read if evidence does not show it.",
                        "A natural-language answer is allowed only inside final_answer.",
                        "A tool call is allowed only if action=tool, tool is valid, and arguments are explicit.",
                        "Expose uncertainty in final_answer rather than hiding it.",
                    ],
                }, ensure_ascii=False, default=str),
            },
        ],
        "options": ollama_options(num_predict=1600),
    }

    response = post_json(OLLAMA_TASK_URL, payload, timeout=min(90, max(30, AGENTIC_PLANNER_STEP_TIMEOUT))) # pyright: ignore[reportUndefinedVariable]
    if response.get("backend_unreachable") or response.get("backend_timeout") or response.get("error"):
        return {
            "ok": False,
            "error": response.get("error") or response.get("error_type") or "vulkan_repair_backend_error",
            "raw_response": response,
            "raw_planner_text_preview": raw_planner_text[:2000],
            "repair_cache_key": repair_key,
            "repaired_decision": None,
        }

    message = _dict_or_empty(response.get("message"))
    raw_text = str(message.get("content") or response.get("response") or "")
    parse_diagnostics = parse_strict_json_object_diagnostics(raw_text) # pyright: ignore[reportUndefinedVariable]
    repaired = parse_diagnostics.get("decoded") if parse_diagnostics.get("ok") is True else {}
    if not isinstance(repaired, dict) or not repaired:
        return {
            "ok": False,
            "error": "vulkan_repair_no_pure_json_decision",
            "json_parse_error_type": parse_diagnostics.get("error_type"),
            "json_parse_error": parse_diagnostics.get("error"),
            "raw_response_chars": len(raw_text),
            "raw_text_preview": raw_text[:2000],
            "raw_planner_text_preview": raw_planner_text[:2000],
            "repair_cache_key": repair_key,
            "repaired_decision": None,
        }

    repaired["repaired_by_vulkan_gpu0_11435"] = True
    repaired["original_planner_decision"] = {
        k: decision.get(k)
        for k in ("action", "tool", "arguments", "reason", "final_answer")
        if decision.get(k) not in (None, "", [], {})
    }
    if raw_planner_text:
        repaired["raw_planner_text_before_repair"] = raw_planner_text[:4000]
    return {
        "ok": True,
        "repaired_decision": repaired,
        "raw_text_preview": raw_text[:2000],
        "raw_planner_text_preview": raw_planner_text[:2000],
        "repair_cache_key": repair_key,
    }


def controller_guard_result_for_validation(
    validation: dict[str, Any],
    decision: dict[str, Any],
    *,
    job_id: str = "",
    step: int = 0,
    goal: str = "",
) -> dict[str, Any]:
    violations = _list_or_empty(validation.get("violations"))
    contract = _dict_or_empty(validation.get("evidence_contract"))
    required_continuation = (
        validation.get("required_prompt_context_continuation")
        if isinstance(validation.get("required_prompt_context_continuation"), dict)
        else {}
    )
    if required_continuation:
        contract = _enforce_required_scratchpad_read_continuation_contract(
            contract,
            required_continuation,
        )
        validation = dict(validation)
        validation["evidence_contract"] = contract
    contract_summary, contract_chars, contract_sha256 = _evidence_contract_storage_summary(contract)
    contract_overlay = _controller_guard_contract_overlay(contract)
    guard = {
        "tool": "controller_guard",
        "ok": True,
        "kind": "validator_feedback",
        "source": "validator",
        "guard_type": "planner_decision_validation",
        "summary": (
            "planner_decision_validation_failed: " + "; ".join(str(v) for v in violations)
            if violations else "planner_decision_validation_failed"
        ),
        "violations": violations,
        "evidence_contract_summary": contract_summary,
        "evidence_contract_chars": contract_chars,
        "evidence_contract_sha256": contract_sha256,
        "rejected_decision": {
            k: (
                _prompt_clip_text(decision.get(k), 12000)
                if k == "final_answer" else decision.get(k)
            )
            for k in (
                "action", "tool", "arguments", "reason", "selected_by_3572",
                "coerced_by_3572", "planner_stream_meta", "final_answer",
            )
            if decision.get(k) not in (None, "", [], {})
        },
        "ollama_turn": planner_ollama_turn_from_decision(decision),
    }
    if contract_overlay:
        guard["evidence_contract_overlay"] = contract_overlay
    if validation.get("semantic_goal_classification") not in (None, "", [], {}):
        guard["semantic_goal_classification"] = validation.get("semantic_goal_classification")
    if validation.get("invalid_decision_signature") not in (None, "", [], {}):
        guard["invalid_decision_signature"] = validation.get("invalid_decision_signature")
    if validation.get("invalid_decision_repeat_count") not in (None, "", [], {}):
        guard["invalid_decision_repeat_count"] = validation.get("invalid_decision_repeat_count")
    replan_specialist = _dict_or_empty(validation.get("planner_replan_specialist"))
    if replan_specialist:
        guard["planner_replan_specialist"] = replan_specialist
    required_next_progress = str(contract.get("required_next_progress") or "").strip()
    if required_next_progress:
        guard["next_instruction"] = required_next_progress
    required_next_tool_call = _dict_or_empty(contract.get("required_next_tool_call"))
    if required_next_tool_call:
        guard["required_next_tool_call"] = required_next_tool_call
        guard["planner_may_choose_final"] = False
    candidate_next_actions = _list_or_empty(contract.get("candidate_next_actions"))
    if candidate_next_actions:
        guard["candidate_next_actions"] = candidate_next_actions[:6]
    if validation.get("action_plan_candidate") not in (None, "", [], {}):
        guard["action_plan_candidate"] = _prompt_clip_text(
            validation.get("action_plan_candidate"),
            12000,
        )
        if not guard.get("next_instruction"):
            guard["next_instruction"] = (
                "Treat action_plan_candidate as an intermediate plan only. "
                "Do not final with it. Use it to choose repo_read evidence and then "
                "repo_propose_code_edit with a complete inline diff/ops payload."
            )
    runtime_debug_extra: dict[str, Any] = {}
    npu_phi_attempt = maybe_enqueue_npu_phi_diagnostic(
        goal=goal,
        evidence_contract=contract,
        validation=validation,
    )
    if (
        npu_phi_attempt.get("attempted")
        or npu_phi_attempt.get("status") not in {"disabled", "not_applicable", ""}
    ):
        runtime_debug_extra["npu_phi"] = npu_phi_attempt
    guard["runtime_debug_packet"] = build_runtime_debug_packet(
        job_id=job_id,
        step=step,
        phase="VALIDATE_DECISION",
        goal=goal,
        decision=decision,
        validator_result=validation,
        evidence_contract=contract_summary,
        extra=runtime_debug_extra or None,
    )
    return guard


# ---------------------------------------------------------------------------
# Planner decision (single step)
# ---------------------------------------------------------------------------

def _planner_system_for_current_mode() -> str:
    return planner_system_for_current_mode(
        native_tools=AGENTIC_PLANNER_NATIVE_TOOLS,
    )


def planner_decision(
    job_id: str,
    state: dict[str, Any],
    step: int,
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    return planner_decision(
        job_id,
        state,
        step,
        history,
        deps={
            "build_planner_user_payload": _build_planner_user_payload,
            "controller_memory_target_key": _controller_memory_target_key,
            "filter_tool_manifest_for_names": filter_tool_manifest_for_names,
            "history_tool_result": history_tool_result,
            "input_error_goal": input_error_goal,
            "native_tool_calls_decision": _native_tool_calls_decision,
            "native_tools_schema_for_planner": native_tools_schema_for_planner,
            "normalize_terminal_planner_decision": _normalize_terminal_planner_decision,
            "parse_strict_json_object": _parse_strict_json_object,
            "planner_history_messages_for_ollama": _planner_history_messages_for_ollama,
            "planner_system_for_current_mode": _planner_system_for_current_mode,
            "planner_token_generation_reserve": _planner_token_generation_reserve,
            "prompt_context_continuation_from_payload": _prompt_context_continuation_from_payload,
            "prompt_generation_headroom_char_budget": _prompt_generation_headroom_char_budget,
            "prompt_window_chars": _prompt_window_chars,
            "tool_surface_names_for_turn": tool_surface_names_for_turn,
            "agent_job_planner_stream_path": agent_job_planner_stream_path,
            "agent_job_root": agent_job_root,
            "append_agent_event": append_agent_event,
            "build_planner_intrinsic_context": build_planner_intrinsic_context,
            "goal_has_write_intent": goal_has_write_intent,
            "goal_requires_code_product_report": goal_requires_code_product_report,
            "history_has_tool": history_has_tool,
            "internal_tools_list": internal_tools_list,
            "normalize_planner_decision": normalize_planner_decision, # pyright: ignore[reportUndefinedVariable]
            "planner_done_token": planner_done_token,
            "planner_evidence_contract": planner_evidence_contract,
            "planner_memory_surface": planner_memory_surface,
            "post_json_stream_to_file": post_json_stream_to_file, # pyright: ignore[reportUndefinedVariable]
            "successful_code_edit_proposals": successful_code_edit_proposals,
            "summarize_history_artifacts": summarize_history_artifacts,
            "write_json": write_json,
        },
        config={
            "AGENTIC_PLANNER_NATIVE_TOOLS": AGENTIC_PLANNER_NATIVE_TOOLS,
            "AGENTIC_PLANNER_NUM_CTX": AGENTIC_PLANNER_NUM_CTX,
            "AGENTIC_PLANNER_NUM_CTX_CAP": AGENTIC_PLANNER_NUM_CTX_CAP,
            "AGENTIC_PLANNER_NUM_CTX_REQUESTED": AGENTIC_PLANNER_NUM_CTX_REQUESTED,
            "AGENTIC_PLANNER_NUM_PREDICT": AGENTIC_PLANNER_NUM_PREDICT,
            "AGENTIC_PLANNER_PROMPT_CHAR_BUDGET": AGENTIC_PLANNER_PROMPT_CHAR_BUDGET,
            "AGENTIC_PLANNER_STEP_TIMEOUT": AGENTIC_PLANNER_STEP_TIMEOUT,
            "AGENTIC_PLANNER_TEMPERATURE": AGENTIC_PLANNER_TEMPERATURE,
            "AGENTIC_PLANNER_TOP_K": AGENTIC_PLANNER_TOP_K,
            "AGENTIC_PLANNER_TOP_P": AGENTIC_PLANNER_TOP_P,
            "AGENTIC_PLANNER_PRESENCE_PENALTY": AGENTIC_PLANNER_PRESENCE_PENALTY,
            "OLLAMA_KEEP_ALIVE": OLLAMA_KEEP_ALIVE,
            "PLANNER_INTRINSIC_CONTEXT_MAX_CHARS": PLANNER_INTRINSIC_CONTEXT_MAX_CHARS,
            "PLANNER_INTRINSIC_RAG_CHAR_BUDGET": PLANNER_INTRINSIC_RAG_CHAR_BUDGET,
            "PLANNER_INTRINSIC_RAG_TOP_K": PLANNER_INTRINSIC_RAG_TOP_K,
            "PLANNER_MODEL": PLANNER_MODEL,
            "PLANNER_RAG_DB": PLANNER_RAG_DB,
            "PLANNER_RAG_EMBEDDING_BATCH_SIZE": PLANNER_RAG_EMBEDDING_BATCH_SIZE,
            "PLANNER_RAG_EXTERNAL_RERANKER_URL": PLANNER_RAG_EXTERNAL_RERANKER_URL,
            "PLANNER_RAG_RERANKING_ENGINE": PLANNER_RAG_RERANKING_ENGINE,
            "PLANNER_RAG_RERANKING_MODEL": PLANNER_RAG_RERANKING_MODEL,
            "PLANNER_RAG_RERANK_TIMEOUT_SECONDS": PLANNER_RAG_RERANK_TIMEOUT_SECONDS,
            "PLANNER_URL": PLANNER_URL,
        },
    )


# ---------------------------------------------------------------------------
# Full agentic loop
# ---------------------------------------------------------------------------


def compact_final_state_result(result: dict[str, Any] | None) -> dict[str, Any]:
    return compact_final_state_result(
        result,
        history_ledger_builder=planner_history_ledger,
    )


_PUBLIC_TERMINAL_POINTER_KEYS = None


def public_terminal_content_key(key: Any) -> bool:
    return public_terminal_content_key(key)


def _public_terminal_sanitize_text(value: Any, *, content: bool = False) -> str:
    return public_terminal_sanitize_text(value, content=content)


def public_terminal_sanitize_value(value: Any, *, key: str = "", depth: int = 0) -> Any:
    return public_terminal_sanitize_value(value, key=key, depth=depth)


def public_terminal_history_ledger(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return public_terminal_history_ledger(
        history,
        repo_read_item_full_content=_repo_read_item_full_content,
    )




def terminal_context_alias() -> dict[str, Any]:
    return terminal_context_alias()



def planner_decision_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from .application.public_payload.terminal_context_rows import planner_decision_rows as _inner
    return _inner(history)


def validation_rejection_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from .application.public_payload.terminal_context_rows import validation_rejection_rows as _inner
    return _inner(history)


def executed_tool_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from .application.public_payload.terminal_context_rows import executed_tool_rows as _inner
    return _inner(history)


def repo_read_content_views(
    history: list[dict[str, Any]],
    *,
    per_item_limit: int = 60000,
    total_limit: int = 180000,
) -> list[dict[str, Any]]:
    return repo_read_content_views(
        history,
        repo_read_item_full_content=_repo_read_item_full_content,
        per_item_limit=per_item_limit,
        total_limit=total_limit,
    )


def execution_evidence_digest_text(result: dict[str, Any] | None, limit: int = 12000) -> str:
    return execution_evidence_digest_text(
        result,
        repo_read_item_full_content=_repo_read_item_full_content,
        extract_key_lines=_extract_key_lines,
        limit=limit,
    )


def compact_evidence_guide_for_30b(
    *,
    goal: Any,
    status: str,
    answer: str,
    tool_context: dict[str, Any],
    limit: int = 12000,
) -> str:
    artifacts = tool_context.get("artifacts") if isinstance(tool_context.get("artifacts"), list) else []
    artifact_rows: list[str] = []
    for index, row in enumerate(artifacts[:12]):
        if not isinstance(row, dict):
            continue
        artifact = row.get("artifact") if isinstance(row.get("artifact"), dict) else {}
        label = str(artifact.get("kind") or row.get("tool") or "tool_result")
        path = artifact.get("repo_path") or artifact.get("target_file")
        if path:
            label += f":{path}"
        artifact_rows.append(f"{index}:{label}")
    digest = str(tool_context.get("evidence_digest_for_30b") or "").strip()
    answer_text = str(answer or "").strip()
    lines = [
        "GUIDA ALL'EVIDENZA INLINE PER IL 30B.",
        "Guida compatta: non duplica file, diff o digest estesi.",
        (
            "Ordine di lettura: primary_payload_for_30b.primary_location; "
            "payload_index_for_30b.concrete_results; "
            "tool_context_for_30b.artifacts[*].artifact."
        ),
        f"status={status}; artifacts={len(artifacts)}",
        f"richiesta_utente={str(goal or '').strip()}",
    ]
    if artifact_rows:
        suffix = f" (+{len(artifacts) - len(artifact_rows)} altri)" if len(artifacts) > len(artifact_rows) else ""
        lines.append("artifact_order=" + ", ".join(artifact_rows) + suffix)
    if answer_text:
        lines.extend([
            "",
            "Sommario/risposta del planner da usare come guida:",
            _prompt_clip_text(answer_text, 6000),
        ])
    if status != "completed" and digest and digest not in answer_text:
        lines.extend([
            "",
            "Evidenza eseguita inline breve:",
            _prompt_clip_text(digest, 4000),
        ])
    return _public_terminal_sanitize_text(_prompt_clip_text("\n".join(lines), limit))


def latest_code_product_payload(history: list[dict[str, Any]]) -> dict[str, Any]:
    return latest_code_product_payload(history)


def code_product_answer_text(result: dict[str, Any] | None, limit: int = 180000) -> str:
    return code_product_answer_text(result, limit=limit)


def partial_product_clean_text(value: Any, limit: int = 40000) -> str:
    return partial_product_clean_text(value, limit)


def partial_products_for_30b(history: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    return partial_products_for_30b(
        history,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
        limit=limit,
    )


def best_partial_product_for_30b(history: list[dict[str, Any]]) -> dict[str, Any]:
    return best_partial_product_for_30b(
        history,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
    )


def partial_product_answer_text(result: dict[str, Any] | None, limit: int = 60000) -> str:
    return partial_product_answer_text(
        result,
        code_product_build_state_kind=CODE_PRODUCT_BUILD_STATE_KIND,
        limit=limit,
    )


def agent_flow_diagnostics(
    goal: str,
    history: list[dict[str, Any]],
    planner_memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from .application.planner.planner_decision import _planner_incomprehensible_retry_count as _inner_pirc
    return agent_flow_diagnostics(
        goal,
        history,
        planner_memory,
        native_tools_enabled=AGENTIC_PLANNER_NATIVE_TOOLS,
        evidence_contract_builder=planner_evidence_contract,
        planner_incomprehensible_retry_count=_inner_pirc,
    )



def answer_for_openwebui(status: str, final_summary: str, result: dict[str, Any] | None) -> str:
    return answer_for_openwebui(
        status,
        final_summary,
        result,
        code_product_answer_text=code_product_answer_text,
        execution_evidence_digest_text=execution_evidence_digest_text,
        partial_product_answer_text=partial_product_answer_text,
    )


def next_action_for_openwebui(status: str, result: dict[str, Any] | None) -> dict[str, Any]:
    return next_action_for_openwebui(status, result)


def build_tool_context_for_30b(
    job_id: str,
    state: dict[str, Any],
    status: str,
    final_summary: str,
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    return build_tool_context_for_30b(
        job_id,
        state,
        status,
        final_summary,
        result,
        planner_model=PLANNER_MODEL,
        planner_url=PLANNER_URL,
        job_root_for_id=agent_job_root,
        planner_composed_answer=planner_composed_answer,
        agent_flow_diagnostics=agent_flow_diagnostics,
        partial_products_for_30b=partial_products_for_30b,
        best_partial_product_for_30b=best_partial_product_for_30b,
        answer_for_openwebui=answer_for_openwebui,
        execution_evidence_digest_text=execution_evidence_digest_text,
        repo_read_content_views=repo_read_content_views,
        next_action_for_openwebui=next_action_for_openwebui,
        initial_orientation_surface_from_history=_initial_orientation_surface_from_history,
        planner_decision_rows=planner_decision_rows,
        validation_rejection_rows=validation_rejection_rows,
        executed_tool_rows=executed_tool_rows,
        planner_turn_memory=_planner_turn_memory,
        compact_final_state_result=compact_final_state_result,
        public_tool_artifact_rows=_public_tool_artifact_rows,
        public_tool_context_limits=_public_tool_context_limits,
        planner_evidence_contract=planner_evidence_contract,
        planner_history_ledger=planner_history_ledger,
        strip_public_local_references=_strip_public_local_references,
    )


def controller_memory_lesson_text(
    job_id: str,
    state: dict[str, Any],
    status: str,
    final_summary: str,
    result: dict[str, Any],
    contract: dict[str, Any],
    target_key: str,
) -> str:
    return controller_memory_lesson_text(
        job_id,
        state,
        status,
        final_summary,
        result,
        contract,
        target_key,
    )


def _write_controller_memory_lesson(
    job_id: str,
    state: dict[str, Any],
    status: str,
    final_summary: str,
    result: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    return write_controller_memory_lesson(
        job_id,
        state,
        status,
        final_summary,
        result,
        root,
        planner_evidence_contract=planner_evidence_contract,
        controller_memory_target_key=_controller_memory_target_key,
        runtime_sqlite_memory_write=runtime_sqlite_memory_write,
    )


def loop_turn_memory_text(
    job_id: str,
    state: dict[str, Any],
    row: dict[str, Any],
    contract: dict[str, Any],
    target_key: str,
) -> str:
    return loop_turn_memory_text(
        job_id,
        state,
        row,
        contract,
        target_key,
        prompt_clip_value=prompt_clip_value,
    )


def _write_loop_turn_memory(
    job_id: str,
    state: dict[str, Any],
    row: dict[str, Any],
    root: Path,
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    return write_loop_turn_memory(
        job_id,
        state,
        row,
        root,
        history,
        planner_evidence_contract=planner_evidence_contract,
        controller_memory_target_key=_controller_memory_target_key,
        runtime_sqlite_memory_write=runtime_sqlite_memory_write,
        prompt_clip_value=prompt_clip_value,
    )


def _terminal_judge_fallback_report(
    *,
    status: str,
    goal: str,
    history: list[dict[str, Any]],
    artifacts: list[Any],
    error: str,
) -> dict[str, Any]:
    return {
        "schema": "terminal_judge_fallback.v1",
        "available": False,
        "provider_attempted": True,
        "provider_ok": False,
        "provider_available": False,
        "fallback_used": True,
        "status": status,
        "goal": goal,
        "history_rows": len(history),
        "artifacts_count": len(artifacts),
        "root_cause_class": "terminal_judge_provider_unavailable",
        "root_cause": error or "terminal judge provider returned no valid report",
        "operator_summary": (
            f"Terminal status={status}; provider-backed terminal judge was attempted but "
            f"did not return a valid report. Evidence remains available: "
            f"artifacts={len(artifacts)}, history_rows={len(history)}."
        ),
    }


def _terminal_judge_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Terminal judge report",
        "",
        f"- schema: `{report.get('schema') or ''}`",
        f"- decision: `{report.get('decision') or ''}`",
        f"- root_cause_class: `{report.get('root_cause_class') or ''}`",
        f"- provider_ok: `{report.get('provider_ok') is True}`",
        f"- fallback_used: `{report.get('fallback_used') is True}`",
        "",
        "## Root cause",
        "",
        str(report.get("root_cause") or ""),
        "",
        "## Operator summary",
        "",
        str(report.get("operator_summary") or ""),
    ]
    recommendations = report.get("recommended_patch_targets")
    if isinstance(recommendations, list) and recommendations:
        lines.extend(["", "## Recommended patch targets", ""])
        lines.extend(f"- {str(item)}" for item in recommendations[:20])
    return "\n".join(lines).rstrip() + "\n"


def _sanitize_terminal_judge_provider_report(
    value: Any,
    *,
    status: str,
    goal: str,
    history_count: int,
    artifact_count: int,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    root_cause = str(value.get("root_cause") or "").strip()
    operator_summary = str(value.get("operator_summary") or "").strip()
    if not root_cause or not operator_summary:
        return {}
    decision = str(value.get("decision") or "blocked_with_diagnosis").strip().lower()
    if decision != "blocked_with_diagnosis":
        decision = "blocked_with_diagnosis"
    return {
        "schema": "blocked_needs_attention_judge_report.v2",
        "available": True,
        "provider_attempted": True,
        "provider_ok": True,
        "provider_available": True,
        "fallback_used": False,
        "provider": "gpu1_planner",
        "planner_model": PLANNER_MODEL,
        "planner_url": PLANNER_URL,
        "decision": decision,
        "status": status,
        "goal": goal,
        "history_rows": history_count,
        "artifacts_count": artifact_count,
        "root_cause_class": str(value.get("root_cause_class") or "unspecified")[:160],
        "root_cause": _prompt_clip_text(root_cause, 6000),
        "evidence_status": prompt_clip_value(
            value.get("evidence_status"), text_limit=1200, list_limit=20
        ),
        "lane_diagnostics": prompt_clip_value(
            value.get("lane_diagnostics"), text_limit=1200, list_limit=24
        ),
        "operator_summary": _prompt_clip_text(operator_summary, 8000),
        "recommended_patch_targets": prompt_clip_value(
            value.get("recommended_patch_targets"), text_limit=800, list_limit=20
        ),
        "confidence": value.get("confidence"),
    }


def judge_blocked_job(
    job_id: str,
    root: Path,
    state: dict[str, Any],
    status: str,
    final_summary: str,
    result: dict[str, Any],
    tool_context: dict[str, Any],
) -> dict[str, Any]:
    """Run the same GPU1 planner model in terminal-judge role.

    This lane diagnoses a terminal failure. It cannot execute tools, reopen the
    loop, mark the job completed, or bypass the validator. The deterministic
    report is used only when the GPU1 provider is unavailable or returns invalid JSON.
    """
    result = dict(result) if isinstance(result, dict) else {}
    goal = str(state.get("goal") or "")
    history = result.get("history") if isinstance(result.get("history"), list) else []
    artifacts = tool_context.get("artifacts") if isinstance(tool_context.get("artifacts"), list) else []
    evidence_contract = planner_evidence_contract(goal, history)
    repo_read_views = repo_read_content_views(
        history,
        per_item_limit=12000,
        total_limit=120000,
    )
    request_payload = {
        "schema": "blocked_needs_attention_judge_request.v1",
        "task": "diagnose_terminal_agentic_loop_without_reopening_it",
        "role": "terminal_judge",
        "goal": goal,
        "status": status,
        "final_summary": _prompt_clip_text(final_summary, 12000),
        "blocked_by": result.get("blocked_by"),
        "validation_rejections": prompt_clip_value(
            validation_rejection_rows(history)[-20:], text_limit=2000, list_limit=20
        ),
        "planner_decision_tail": prompt_clip_value(
            planner_decision_rows(history)[-20:], text_limit=2000, list_limit=20
        ),
        "tool_results_tail": prompt_clip_value(
            executed_tool_rows(history)[-24:], text_limit=1600, list_limit=24
        ),
        "repo_read_evidence_windows": repo_read_views[:20],
        "final_quality": prompt_clip_value(
            evidence_contract.get("repo_analysis_final_quality"),
            text_limit=2000,
            list_limit=20,
        ),
        "evidence_contract": _compact_vulkan_repair_evidence_contract(evidence_contract),
        "tool_context_summary": {
            "artifact_count": len(artifacts),
            "history_rows": len(history),
            "payload_available": bool(artifacts),
            "primary_payload": prompt_clip_value(
                tool_context.get("primary_payload_for_30b"),
                text_limit=1200,
                list_limit=12,
            ),
        },
        "rules": [
            "Return strict JSON only.",
            "Do not execute tools or reopen the loop.",
            "Do not mark the job completed and do not bypass the validator.",
            "Distinguish missing evidence from evidence present but not consumed.",
            "Distinguish bad final composition from contradictory controller state.",
            "Treat successful repo_read artifacts as evidence even when prompt previews were truncated.",
            "Produce an operational diagnosis for the operator, not a synthetic count summary.",
        ],
        "required_json_shape": {
            "decision": "blocked_with_diagnosis",
            "root_cause_class": "short machine class",
            "root_cause": "concrete causal explanation",
            "evidence_status": {},
            "lane_diagnostics": {},
            "operator_summary": "usable report",
            "recommended_patch_targets": ["repo-relative file or function"],
            "confidence": 0.0,
        },
    }
    payload = {
        "model": PLANNER_MODEL,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "think": False,
        "format": "json",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are the terminal judge lane of the same GPU1 planner model. "
                    "Read the terminal job evidence and diagnose why no validator-accepted "
                    "final was produced. You are not the main planner and cannot execute tools, "
                    "reopen the loop, mark completed, or bypass the validator. Return strict JSON only."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(request_payload, ensure_ascii=False, default=str),
            },
        ],
        "options": {
            "temperature": GLOBAL_TEMPERATURE,
            "num_predict": 2200,
            "num_ctx": max(
                4096,
                min(
                    int(AGENTIC_PLANNER_NUM_CTX_CAP or AGENTIC_PLANNER_NUM_CTX or 8192),
                    int(AGENTIC_PLANNER_NUM_CTX or 8192),
                ),
            ),
        },
    }
    timeout_seconds = min(180, max(30, int(AGENTIC_PLANNER_STEP_TIMEOUT or 30)))
    step = state.get("current_step")
    try:
        append_agent_event(
            job_id,
            "planner_role_call_started",
            "Terminal judge role started on GPU1.",
            {
                "role": "terminal_judge",
                "provider": "gpu1_planner",
                "planner_model": PLANNER_MODEL,
                "planner_url": PLANNER_URL,
                "timeout_seconds": timeout_seconds,
            },
            step=step,
        )
    except (OSError, IOError, TimeoutError, ValueError):
        pass

    provider_error = ""
    decoded: dict[str, Any] = {}
    try:
        response = post_json(PLANNER_URL, payload, timeout_seconds) # pyright: ignore[reportUndefinedVariable]
        if response.get("backend_unreachable") or response.get("backend_timeout") or response.get("error"):
            provider_error = str(
                response.get("error")
                or response.get("error_type")
                or "terminal_judge_backend_error"
            )
        else:
            message = response.get("message") if isinstance(response.get("message"), dict) else {}
            raw_text = str(
                message.get("content")
                or response.get("response")
                or response.get("partial_content")
                or ""
            )
            diagnostics = parse_strict_json_object_diagnostics(raw_text) # pyright: ignore[reportUndefinedVariable]
            if diagnostics.get("ok") is True and isinstance(diagnostics.get("decoded"), dict):
                decoded = dict(diagnostics["decoded"])
            else:
                provider_error = str(
                    diagnostics.get("error_type")
                    or diagnostics.get("error")
                    or "terminal_judge_invalid_json"
                )
    except (OSError, IOError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        provider_error = f"{type(exc).__name__}: {exc}"

    judge_report = _sanitize_terminal_judge_provider_report(
        decoded,
        status=status,
        goal=goal,
        history_count=len(history),
        artifact_count=len(artifacts),
    )
    if not judge_report:
        judge_report = _terminal_judge_fallback_report(
            status=status,
            goal=goal,
            history=history,
            artifacts=artifacts,
            error=provider_error,
        )

    result["terminal_judge_report"] = judge_report
    judge_path = root / "blocked_judge_report.json"
    judge_markdown_path = root / "blocked_judge_report.md"
    judge_artifact = {
        "schema": "terminal_judge_artifact.v2",
        "job_id": job_id,
        "root_path": str(root),
        "status": status,
        "report": judge_report,
    }
    try:
        write_json(judge_path, judge_artifact)
        write_json(root / "terminal-judge.json", judge_artifact)
        judge_markdown_path.write_text(
            _terminal_judge_markdown(judge_report),
            encoding="utf-8",
        )
    except (OSError, IOError) as exc:
        judge_report["persistence_ok"] = False
        judge_report["persistence_error_type"] = type(exc).__name__
        judge_report["persistence_error"] = str(exc)[:1000]
        try:
            append_agent_event(
                job_id,
                "planner_role_call_failed",
                f"Terminal judge persistence failed for status={status}.",
                judge_report,
                step=step,
            )
        except (OSError, IOError):
            pass
        return result

    judge_report["persistence_ok"] = True
    result["terminal_judge_artifact"] = str(judge_path)
    result["terminal_judge_markdown_artifact"] = str(judge_markdown_path)

    try:
        append_agent_event(
            job_id,
            "planner_role_call_completed",
            f"Terminal judge role completed for status={status}.",
            judge_artifact,
            step=step,
        )
        judge_report["event_emit_ok"] = True
    except (OSError, IOError, TimeoutError) as exc:
        judge_report["event_emit_ok"] = False
        judge_report["event_emit_error_type"] = type(exc).__name__
        judge_report["event_emit_error"] = str(exc)[:1000]
        try:
            append_agent_event(
                job_id,
                "planner_role_call_failed",
                f"Terminal judge event emission failed for status={status}.",
                judge_report,
                step=step,
            )
        except (OSError, IOError):
            pass

    return result


def finalize_agentic_job(
    job_id: str,
    state: dict[str, Any],
    status: str,
    final_summary: str,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = agent_job_root(job_id)
    result = dict(result or {})
    # Issue 2: Call judge_blocked_job for blocked_needs_attention and max_steps_reached
    if status in {"blocked_needs_attention", "max_steps_reached"}:
        tool_context = build_tool_context_for_30b(job_id, state, status, final_summary, result)
        result = judge_blocked_job(
            job_id=job_id,
            root=root,
            state=state,
            status=status,
            final_summary=final_summary,
            result=result,
            tool_context=tool_context,
        )
    final_summary_with_turns = _final_summary_with_ollama_done_reasons(status, final_summary, result)
    controller_memory = _write_controller_memory_lesson(
        job_id, state, status, final_summary_with_turns, result, root
    )
    result["controller_memory_write"] = controller_memory
    state["controller_memory_last_write"] = controller_memory
    tool_context = build_tool_context_for_30b(job_id, state, status, final_summary_with_turns, result)
    if tool_context.get("partial_products_for_30b") not in (None, "", [], {}):
        result["partial_products_for_30b"] = tool_context.get("partial_products_for_30b")
    if tool_context.get("best_partial_product_for_30b") not in (None, "", [], {}):
        result["best_partial_product_for_30b"] = tool_context.get("best_partial_product_for_30b")
    public_result = public_terminal_result_for_30b(result)
    answer = answer_for_openwebui(status, final_summary_with_turns, result)
    evidence_guide = compact_evidence_guide_for_30b(
        goal=state.get("goal"),
        status=status,
        answer=answer,
        tool_context=tool_context,
    )
    public_final_summary = (
        answer
        if status == "completed" and latest_code_product_payload(_list_or_empty(result.get("history")))
        else final_summary_with_turns
    )
    next_action = tool_context.get("next_action_for_30b") or {}
    materialized = materialize_public_evidence(
        tool_context=tool_context,
        evidence_guide=evidence_guide,
        completed=status == "completed",
        internal_job_status={
            "completed": status == "completed",
            "status": status,
            "payload_available": bool(tool_context.get("artifacts")),
            "source": "internal_3572_job_status",
        },
    )
    final = {
        "ok": status == "completed",
        "job_id": job_id,
        "status": status,
        "goal": state.get("goal"),
        "final_summary": public_final_summary,
        "planner_final_summary": final_summary,
        "evidence_guide_for_30b": evidence_guide,
        "primary_payload_for_30b": materialized["primary_payload_for_30b"],
        "payload_index_for_30b": materialized["payload_index_for_30b"],
        "priority_evidence_for_30b": materialized["priority_evidence_for_30b"],
        "materialization_report": materialized["materialization_report"],
        "next_action_for_30b": next_action,
        "result": public_result,
        "agent_flow_diagnostics": tool_context.get("agent_flow_diagnostics"),
        "tool_context_for_30b": tool_context,
        "agent_context_for_30b": terminal_context_alias(),
        "structured_context_for_30b": terminal_context_alias(),
        "structured_result_for_30b": terminal_context_alias(),
        "events_path": str(root / "events.ndjson"),
    }
    write_json(root / "final.json", final)
    (root / "final.md").write_text(answer, encoding="utf-8")
    state = load_agent_job_state(job_id) or state
    state.update({
        "status": status,
        "final_path": str(root / "final.json"),
        "final_markdown_path": str(root / "final.md"),
        "final_summary": public_final_summary,
        "planner_final_summary": final_summary,
        "evidence_guide_for_30b": evidence_guide,
        "primary_payload_for_30b": materialized["primary_payload_for_30b"],
        "payload_index_for_30b": materialized["payload_index_for_30b"],
        "priority_evidence_for_30b": materialized["priority_evidence_for_30b"],
        "materialization_report": materialized["materialization_report"],
        "next_action_for_30b": next_action,
        "result": compact_final_state_result(public_result),
        "tool_context_for_30b": tool_context,
        "agent_context_for_30b": terminal_context_alias(),
        "structured_context_for_30b": terminal_context_alias(),
        "structured_result_for_30b": terminal_context_alias(),
    })
    write_agent_job_state(state)
    append_agent_event(
        job_id, "job_finished", f"Job finished status={status}.", {"status": status},
        step=state.get("current_step"),
    )
    return final
# run_agentic_planner_job moved to application.planner.planner_loop


def agentic_tool_allowed(
    tool: str, args: dict[str, Any], approval_mode: str
) -> tuple[bool, str]:
    """Delegate to the extracted planner_loop module."""
    from .planner_loop import _agentic_tool_allowed as _inner
    return _inner(tool, args, approval_mode)
