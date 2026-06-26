"""Terminal output and public result formatting extracted from planner.py.

These functions handle compact final state results, public terminal sanitization,
history ledgers, decision rows, evidence digests, partial product formatting,
and tool context building for OpenWebUI 30B display.
"""
from __future__ import annotations

import json
from typing import Any

from aicarmine_broker.application.planner.evidence_contract_builder import planner_evidence_contract


# ---------------------------------------------------------------------------
# Compact final state result
# ---------------------------------------------------------------------------

def compact_final_state_result(result: dict[str, Any] | None) -> dict[str, Any]:
    """Create a compact representation of the final state result."""
    from .agentic_v2 import compact_final_state_result as _inner
    return _inner(result, history_ledger_builder=_planner_history_ledger)


# ---------------------------------------------------------------------------
# Public terminal sanitization
# ---------------------------------------------------------------------------

_PUBLIC_TERMINAL_POINTER_KEYS = None


def public_terminal_content_key(key: Any) -> bool:
    """Check if a key should be included in terminal content."""
    from ..public_payload.terminal_sanitizer import public_terminal_content_key as _inner
    return _inner(key)


def _public_terminal_sanitize_text(value: Any, *, content: bool = False) -> str:
    """Sanitize text for terminal display."""
    from ..public_payload.terminal_sanitizer import public_terminal_sanitize_text as _inner
    return _inner(value, content=content)


def public_terminal_sanitize_value(value: Any, *, key: str = "", depth: int = 0) -> Any:
    """Sanitize arbitrary values for terminal display."""
    from ..public_payload.terminal_sanitizer import public_terminal_sanitize_value as _inner
    return _inner(value, key=key, depth=depth)


# ---------------------------------------------------------------------------
# Terminal history ledger
# ---------------------------------------------------------------------------

def public_terminal_history_ledger(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build a compact history ledger for terminal display."""
    from ..public_payload.terminal_result import public_terminal_history_ledger as _inner
    return _inner(history, repo_read_item_full_content=_repo_read_item_full_content)


def terminal_context_alias() -> dict[str, Any]:
    """Return the terminal context alias structure."""
    from ..public_payload.terminal_context_rows import terminal_context_alias as _inner
    return _inner()


# ---------------------------------------------------------------------------
# Decision and validation rows
# ---------------------------------------------------------------------------

def planner_decision_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract planner decision rows from history."""
    from .agentic_v2 import planner_decision_rows as _inner
    return _inner(history)


def validation_rejection_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract validation rejection rows from history."""
    from .agentic_v2 import validation_rejection_rows as _inner
    return _inner(history)


def executed_tool_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract executed tool result rows from history."""
    from .agentic_v2 import executed_tool_rows as _inner
    return _inner(history)


# ---------------------------------------------------------------------------
# Repo read content views
# ---------------------------------------------------------------------------

def repo_read_content_views(
    history: list[dict[str, Any]],
    *,
    per_item_limit: int = 60000,
    total_limit: int = 180000,
) -> list[dict[str, Any]]:
    """Extract repo read content views for evidence display."""
    from .agentic_v2 import repo_read_content_views as _inner
    return _inner(history, repo_read_item_full_content=_repo_read_item_full_content,
                  per_item_limit=per_item_limit, total_limit=total_limit)


# ---------------------------------------------------------------------------
# Evidence digest
# ---------------------------------------------------------------------------

def execution_evidence_digest_text(result: dict[str, Any] | None, limit: int = 12000) -> str:
    """Generate a compact evidence digest from the result."""
    from .agentic_v2 import execution_evidence_digest_text as _inner
    return _inner(result, repo_read_item_full_content=_repo_read_item_full_content,
                  extract_key_lines=_extract_key_lines, limit=limit)


# ---------------------------------------------------------------------------
# Compact evidence guide for 30B
# ---------------------------------------------------------------------------

def compact_evidence_guide_for_30b(
    *,
    goal: Any,
    status: str,
    answer: str,
    tool_context: dict[str, Any],
    limit: int = 12000,
) -> str:
    """Build a compact evidence guide for the 30B model display."""
    from .agentic_v2 import _prompt_clip_text as _clip

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
            _clip(answer_text, 6000),
        ])
    if status != "completed" and digest and digest not in answer_text:
        lines.extend([
            "",
            "Evidenza eseguita inline breve:",
            _clip(digest, 4000),
        ])
    return _public_terminal_sanitize_text(_clip("\n".join(lines), limit))


# ---------------------------------------------------------------------------
# Code product payload and answer text
# ---------------------------------------------------------------------------

def latest_code_product_payload(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract the latest code product payload from history."""
    from .agentic_v2 import latest_code_product_payload as _inner
    return _inner(history)


def code_product_answer_text(result: dict[str, Any] | None, limit: int = 180000) -> str:
    """Generate answer text from a code product result."""
    from .agentic_v2 import code_product_answer_text as _inner
    return _inner(result, limit=limit)


def partial_product_clean_text(value: Any, limit: int = 40000) -> str:
    """Clean partial product text for display."""
    from .agentic_v2 import partial_product_clean_text as _inner
    return _inner(value, limit)


def partial_products_for_30b(history: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    """Extract partial products for the 30B model context."""
    from .agentic_v2 import partial_products_for_30b as _inner
    return _inner(history, code_product_build_state_kind="code_product_build_state", limit=limit)


def best_partial_product_for_30b(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract the best partial product for the 30B model context."""
    from .agentic_v2 import best_partial_product_for_30b as _inner
    return _inner(history, code_product_build_state_kind="code_product_build_state")


def partial_product_answer_text(result: dict[str, Any] | None, limit: int = 60000) -> str:
    """Generate answer text from a partial product result."""
    from .agentic_v2 import partial_product_answer_text as _inner
    return _inner(result, code_product_build_state_kind="code_product_build_state", limit=limit)


# ---------------------------------------------------------------------------
# Answer and next action for OpenWebUI
# ---------------------------------------------------------------------------

def answer_for_openwebui(status: str, final_summary: str, result: dict[str, Any] | None) -> str:
    """Generate the answer text for OpenWebUI display."""
    from .agentic_v2 import answer_for_openwebui as _inner
    return _inner(status, final_summary, result,
                  code_product_answer_text=code_product_answer_text,
                  execution_evidence_digest_text=execution_evidence_digest_text,
                  partial_product_answer_text=partial_product_answer_text)


def next_action_for_openwebui(status: str, result: dict[str, Any] | None) -> dict[str, Any]:
    """Generate the next action recommendation for OpenWebUI."""
    from .agentic_v2 import next_action_for_openwebui as _inner
    return _inner(status, result)


# ---------------------------------------------------------------------------
# Tool context building for 30B
# ---------------------------------------------------------------------------

def build_tool_context_for_30b(
    job_id: str,
    state: dict[str, Any],
    status: str,
    final_summary: str,
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the complete tool context for the 30B model display."""
    from aicarmine_broker.config import PLANNER_MODEL, PLANNER_URL
    from .planner_loop import agent_job_root
    from .agentic_v2 import (
        planner_composed_answer, planner_history_ledger, strip_public_local_references,
    )
    from ..shared.tool_result import public_tool_artifact_rows, public_tool_context_limits

    return {
        "schema": "tool_context_for_30b.v1",
        "planner_model": PLANNER_MODEL,
        "planner_url": PLANNER_URL,
        "job_root": str(agent_job_root(job_id)),
        "composed_answer": planner_composed_answer(status, final_summary, result),
        "agent_flow_diagnostics": agent_flow_diagnostics(
            state.get("goal", ""),
            result.get("history", []) if isinstance(result, dict) else [],
        ),
        "partial_products_for_30b": partial_products_for_30b(
            result.get("history", []) if isinstance(result, dict) else []
        ),
        "best_partial_product_for_30b": best_partial_product_for_30b(
            result.get("history", []) if isinstance(result, dict) else []
        ),
        "answer_for_openwebui": answer_for_openwebui(status, final_summary, result),
        "execution_evidence_digest_text": execution_evidence_digest_text(result),
        "repo_read_content_views": repo_read_content_views(
            result.get("history", []) if isinstance(result, dict) else []
        ),
        "next_action_for_openwebui": next_action_for_openwebui(status, result),
        "initial_orientation_surface": initial_orientation_surface_from_history(
            result.get("history", []) if isinstance(result, dict) else []
        ),
        "planner_decision_rows": planner_decision_rows(
            result.get("history", []) if isinstance(result, dict) else []
        ),
        "validation_rejection_rows": validation_rejection_rows(
            result.get("history", []) if isinstance(result, dict) else []
        ),
        "executed_tool_rows": executed_tool_rows(
            result.get("history", []) if isinstance(result, dict) else []
        ),
        "planner_turn_memory": _planner_turn_memory(
            result.get("history", []) if isinstance(result, dict) else [],
        ),
        "compact_final_state_result": compact_final_state_result(result),
        "public_tool_artifact_rows": public_tool_artifact_rows(
            result.get("history", []) if isinstance(result, dict) else []
        ),
        "public_tool_context_limits": public_tool_context_limits(
            result.get("history", []) if isinstance(result, dict) else []
        ),
        "evidence_contract": planner_evidence_contract(
            state.get("goal", ""),
            result.get("history", []) if isinstance(result, dict) else [],
        ),
        "history_ledger": planner_history_ledger(
            result.get("history", []) if isinstance(result, dict) else []
        ),
        "strip_public_local_references": strip_public_local_references(
            result if isinstance(result, dict) else {}
        ),
    }


# ---------------------------------------------------------------------------
# Agent flow diagnostics
# ---------------------------------------------------------------------------

def agent_flow_diagnostics(
    goal: str,
    history: list[dict[str, Any]],
    planner_memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate diagnostics about the agentic loop flow."""
    from .agentic_v2 import AGENTIC_PLANNER_NATIVE_TOOLS
    from ..evidence.builder import planner_evidence_contract
    from .planner_decision import _planner_incomprehensible_retry_count

    return {
        "schema": "agent_flow_diagnostics.v1",
        "goal": goal,
        "history_rows": len(history),
        "native_tools_enabled": AGENTIC_PLANNER_NATIVE_TOOLS,
        "evidence_contract": planner_evidence_contract(goal, history),
        "incomprehensible_retry_count": _planner_incomprehensible_retry_count(history),
        "planner_memory": planner_memory or {},
    }


# ---------------------------------------------------------------------------
# Local helper imports used by terminal output functions
# ---------------------------------------------------------------------------

def _extract_key_lines(content: str) -> list[str]:
    """Extract key lines from file content."""
    from .agentic_v2 import extract_key_lines as _inner
    return _inner(content)


def _planner_history_ledger(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build a history ledger for the planner."""
    from .agentic_v2 import planner_history_ledger as _inner
    return _inner(history)


def _repo_read_item_full_content(item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Extract full content from a repo_read history item."""
    from .prompt_budget import _repo_read_item_full_content as _inner
    return _inner(item)


def _planner_turn_memory(
    history: list[dict[str, Any]],
    terminal_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract turn memory from history."""
    from .agentic_v2 import planner_turn_memory as _inner
    return _inner(history, terminal_decision,
                  same_tool_artifact_payload=_same_tool_artifact_payload,
                  repo_read_item_full_content=_repo_read_item_full_content,
                  code_product_build_state_kind="code_product_build_state")


def _same_tool_artifact_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Extract the artifact payload from a tool result."""
    from .agentic_v2 import same_tool_artifact_payload as _inner
    return _inner(result)


def initial_orientation_surface_from_history(
    history: list[dict[str, Any]],
    skipped: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build initial orientation surface from history."""
    from .agentic_v2 import initial_orientation_surface_from_history as _inner
    return _inner(history, skipped, repo_rel_token=_repo_rel_token,
                  repo_doc_or_config=_repo_doc_or_config, low_signal_top_dir=low_signal_top_dir,
                  path_under_scope=_path_under_scope)


def _repo_rel_token(path: str) -> str:
    """Normalize a repo path token."""
    from aicarmine_broker.infrastructure.repo_tools import repo_rel_token as _inner
    return _inner(path)


def _repo_doc_or_config(path: str) -> bool:
    """Check if path is a doc or config file."""
    from .goal_classifier import repo_doc_or_config as _inner
    return _inner(path)


def low_signal_top_dir(path: str) -> bool:
    """Check if top-level directory has low signal."""
    from .agentic_v2 import low_signal_top_dir as _inner
    return _inner(path)


def _path_under_scope(path: str, scope: str) -> bool:
    """Check if path is under the given scope."""
    from .agentic_v2 import path_under_scope as _inner
    return _inner(path, scope)


# ---------------------------------------------------------------------------
# Local aliases for backward compatibility with planner.py imports
# ---------------------------------------------------------------------------
compact_final_state_result = compact_final_state_result
public_terminal_content_key = public_terminal_content_key
_public_terminal_sanitize_text = _public_terminal_sanitize_text
public_terminal_sanitize_value = public_terminal_sanitize_value
public_terminal_history_ledger = public_terminal_history_ledger
terminal_context_alias = terminal_context_alias
planner_decision_rows = planner_decision_rows
validation_rejection_rows = validation_rejection_rows
executed_tool_rows = executed_tool_rows
repo_read_content_views = repo_read_content_views
execution_evidence_digest_text = execution_evidence_digest_text
compact_evidence_guide_for_30b = compact_evidence_guide_for_30b
latest_code_product_payload = latest_code_product_payload
code_product_answer_text = code_product_answer_text
partial_product_clean_text = partial_product_clean_text
partial_products_for_30b = partial_products_for_30b
best_partial_product_for_30b = best_partial_product_for_30b
partial_product_answer_text = partial_product_answer_text
answer_for_openwebui = answer_for_openwebui
next_action_for_openwebui = next_action_for_openwebui
build_tool_context_for_30b = build_tool_context_for_30b
agent_flow_diagnostics = agent_flow_diagnostics

__all__ = [
    "compact_final_state_result",
    "public_terminal_content_key",
    "_public_terminal_sanitize_text",
    "public_terminal_sanitize_value",
    "public_terminal_history_ledger",
    "terminal_context_alias",
    "planner_decision_rows",
    "validation_rejection_rows",
    "executed_tool_rows",
    "repo_read_content_views",
    "execution_evidence_digest_text",
    "compact_evidence_guide_for_30b",
    "latest_code_product_payload",
    "code_product_answer_text",
    "partial_product_clean_text",
    "partial_products_for_30b",
    "best_partial_product_for_30b",
    "partial_product_answer_text",
    "answer_for_openwebui",
    "next_action_for_openwebui",
    "build_tool_context_for_30b",
    "agent_flow_diagnostics",
]