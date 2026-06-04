"""Controller-owned SQLite memory helpers for planner jobs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


EvidenceContractBuilder = Callable[[str, list[dict[str, Any]]], dict[str, Any]]
MemoryWriter = Callable[[dict[str, Any], Path], dict[str, Any]]
TargetKeyBuilder = Callable[[str, dict[str, Any]], str]
ValueClipper = Callable[..., Any]


def controller_memory_lesson_text(
    job_id: str,
    state: dict[str, Any],
    status: str,
    final_summary: str,
    result: dict[str, Any],
    contract: dict[str, Any],
    target_key: str,
) -> str:
    history = result.get("history") if isinstance(result.get("history"), list) else []
    rejections = contract.get("validation_rejections_tail") if isinstance(contract.get("validation_rejections_tail"), list) else []
    last_rejection = next((r for r in reversed(rejections) if isinstance(r, dict) and r.get("summary")), {})
    reads = contract.get("successful_repo_read_paths") if isinstance(contract.get("successful_repo_read_paths"), list) else []
    lists = contract.get("repo_list_files_evidence") if isinstance(contract.get("repo_list_files_evidence"), list) else []
    list_paths = [str(row.get("path")) for row in lists if isinstance(row, dict) and row.get("path")]
    final_contract = contract.get("finalization_contract") if isinstance(contract.get("finalization_contract"), dict) else {}
    lines = [
        f"job={job_id}",
        f"target={target_key}",
        f"status={status}",
        f"goal={str(state.get('goal') or '')[:240]}",
        f"final_gate={str(final_contract.get('reason') or '')[:240]}",
    ]
    if reads:
        lines.append("successful_reads=" + ", ".join(str(p) for p in reads[:8]))
    if list_paths:
        lines.append("listed_paths=" + ", ".join(list_paths[:8]))
    if last_rejection:
        lines.append("do_not_repeat_error=" + str(last_rejection.get("summary") or "")[:240])
    blocker = result.get("blocked_by") or result.get("blocked_tool") or result.get("rejected_tool")
    if blocker:
        lines.append("blocker=" + str(blocker)[:240])
    lines.append("correct_next=" + str(final_summary or final_contract.get("reason") or "")[:260])
    lines.append(f"history_count={len(history)}")
    return "\n".join(lines)[:1200]


def write_controller_memory_lesson(
    job_id: str,
    state: dict[str, Any],
    status: str,
    final_summary: str,
    result: dict[str, Any],
    root: Path,
    *,
    planner_evidence_contract: EvidenceContractBuilder,
    controller_memory_target_key: TargetKeyBuilder,
    runtime_sqlite_memory_write: MemoryWriter,
) -> dict[str, Any]:
    result = result if isinstance(result, dict) else {}
    history = result.get("history") if isinstance(result.get("history"), list) else []
    goal = str(state.get("goal") or "")
    contract = planner_evidence_contract(goal, history)
    target_key = controller_memory_target_key(goal, contract)
    text = controller_memory_lesson_text(job_id, state, status, final_summary, result, contract, target_key)
    try:
        written = runtime_sqlite_memory_write({
            "kind": "controller_job_lesson",
            "tag": target_key,
            "text": text,
            "metadata": {
                "job_id": job_id,
                "status": status,
                "target_key": target_key,
                "target_kind": contract.get("target_kind"),
                "resolved_goal_scope": contract.get("resolved_goal_scope"),
                "resolved_goal_file": contract.get("resolved_goal_file"),
            },
        }, root)
    except Exception as exc:  # pragma: no cover - memory must not block job finalization
        written = {
            "ok": False,
            "tool": "runtime_sqlite_memory_write",
            "error": "controller_memory_lesson_write_failed",
            "error_type": type(exc).__name__,
            "details": str(exc)[:1000],
        }
    written["target_key"] = target_key
    written["controller_owned"] = True
    return written


def loop_turn_memory_text(
    job_id: str,
    state: dict[str, Any],
    row: dict[str, Any],
    contract: dict[str, Any],
    target_key: str,
    *,
    prompt_clip_value: ValueClipper,
) -> str:
    decision = row.get("decision") if isinstance(row.get("decision"), dict) else {}
    result = row.get("tool_result") if isinstance(row.get("tool_result"), dict) else {}
    args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
    rejected = decision.get("rejected_decision") if isinstance(decision.get("rejected_decision"), dict) else {}
    lines = [
        f"loop_turn_key={job_id}:{row.get('step')}:{row.get('substep') or row.get('preseed_index') or ''}",
        f"job={job_id}",
        f"target={target_key}",
        f"step={row.get('step')}",
        f"substep={row.get('substep') or ''}",
        f"preseed_index={row.get('preseed_index') or ''}",
        f"goal={str(state.get('goal') or '')[:240]}",
        f"decision_action={str(decision.get('action') or '')[:80]}",
        f"decision_tool={str(decision.get('tool') or '')[:120]}",
        f"decision_reason={str(decision.get('reason') or '')[:240]}",
        f"decision_args={json.dumps(prompt_clip_value(args, text_limit=180, list_limit=8), ensure_ascii=False, default=str)[:600]}",
        f"rejected_decision={json.dumps(prompt_clip_value(rejected, text_limit=180, list_limit=8), ensure_ascii=False, default=str)[:600]}",
        f"result_tool={str(result.get('tool') or '')[:120]}",
        f"result_ok={result.get('ok')}",
        f"guard_type={str(result.get('guard_type') or '')[:120]}",
        f"summary={str(result.get('summary') or result.get('error') or '')[:260]}",
        f"successful_reads={', '.join(str(p) for p in (contract.get('successful_repo_read_paths') or [])[-8:])}",
        f"required_next_progress={str(contract.get('required_next_progress') or '')[:320]}",
        f"history_count_after_turn={contract.get('history_count') or ''}",
    ]
    return "\n".join(line for line in lines if not line.endswith("="))[:4000]


def write_loop_turn_memory(
    job_id: str,
    state: dict[str, Any],
    row: dict[str, Any],
    root: Path,
    history: list[dict[str, Any]],
    *,
    planner_evidence_contract: EvidenceContractBuilder,
    controller_memory_target_key: TargetKeyBuilder,
    runtime_sqlite_memory_write: MemoryWriter,
    prompt_clip_value: ValueClipper,
) -> dict[str, Any]:
    """Persist one controller-visible loop turn in SQLite memory."""
    goal = str(state.get("goal") or "")
    contract = planner_evidence_contract(goal, history)
    target_key = controller_memory_target_key(goal, contract)
    text = loop_turn_memory_text(
        job_id,
        state,
        row,
        contract,
        target_key,
        prompt_clip_value=prompt_clip_value,
    )
    try:
        written = runtime_sqlite_memory_write({
            "kind": "controller_loop_turn",
            "tag": target_key,
            "text": text,
            "metadata": {
                "job_id": job_id,
                "step": row.get("step"),
                "substep": row.get("substep"),
                "preseed_index": row.get("preseed_index"),
                "target_key": target_key,
                "decision_action": (row.get("decision") or {}).get("action")
                if isinstance(row.get("decision"), dict) else None,
                "decision_tool": (row.get("decision") or {}).get("tool")
                if isinstance(row.get("decision"), dict) else None,
                "result_tool": (row.get("tool_result") or {}).get("tool")
                if isinstance(row.get("tool_result"), dict) else None,
                "result_ok": (row.get("tool_result") or {}).get("ok")
                if isinstance(row.get("tool_result"), dict) else None,
            },
        }, root)
    except Exception as exc:  # pragma: no cover - loop memory must not block routing
        written = {
            "ok": False,
            "tool": "runtime_sqlite_memory_write",
            "error": "controller_loop_turn_memory_write_failed",
            "error_type": type(exc).__name__,
            "details": str(exc)[:1000],
        }
    written["target_key"] = target_key
    written["controller_owned"] = True
    written["loop_turn_memory"] = True
    return written
