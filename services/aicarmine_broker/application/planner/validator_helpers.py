"""
Extracted helper functions from validator.py validate_planner_decision_against_evidence.

This module contains all nested helper functions extracted to reduce cyclomatic complexity
of the parent function from CC 616 to an estimated CC ~150.

Import pattern:
    from .validator_helpers import *
"""

from collections.abc import Mapping
import json
from typing import Any
from dataclasses import dataclass, field


@dataclass
class ValidationContext:
    """Holds all closure variables that nested helpers need access to."""
    contract: dict = field(default_factory=dict)
    history: list = field(default_factory=list)
    deps: Any = None
    config: Any = None
    # Cached references from deps
    repo_rel_token: Any = None
    path_exists_repo_relative: Any = None
    repo_readable_evidence_file: Any = None
    normalize_tool_name: Any = None
    decision_paths: Any = None
    prompt_window_consumed_offsets: Any = None
    successful_read_paths: Any = None


# ==============================================================================
# Answer chunk helpers
# ==============================================================================

def _answer_chunk_misuses_terminal_payload_shape(ctx: ValidationContext, text: str) -> bool:
    """Check if answer chunk misuses terminal payload shape."""
    try:
        parsed = json.loads(str(text or ""))
    except Exception:
        return False
    if not isinstance(parsed, dict):
        return False
    return any(str(key) in parsed for key in ("final_answer", "answer", "summary"))


def _successful_answer_chunk_signatures(ctx: ValidationContext) -> set[str]:
    """Extract successful answer chunk signatures from history."""
    signatures: set[str] = set()
    for row in ctx.history if isinstance(ctx.history, list) else []:
        if not isinstance(row, dict):
            continue
        decision_row = row.get("decision") if isinstance(row.get("decision"), dict) else {}
        result_row = row.get("tool_result") if isinstance(row.get("tool_result"), dict) else {}
        tool_name = str(decision_row.get("tool") or result_row.get("tool") or "")
        if ctx.normalize_tool_name and tool_name:
            tool_name = ctx.normalize_tool_name(tool_name)
        if tool_name != "planner_scratchpad_write":
            continue
        raw_args = decision_row.get("arguments") if isinstance(decision_row.get("arguments"), dict) else {}
        written = result_row.get("written") if isinstance(result_row.get("written"), dict) else {}
        kind = str(raw_args.get("kind") or written.get("kind") or "").strip()
        if kind not in {"answer_chunk", "final_answer_chunk"} or result_row.get("ok") is not True:
            continue
        tag = str(raw_args.get("tag") or written.get("tag") or "").strip()
        if tag:
            signatures.add(f"{kind}:{tag}")
    return signatures


# ==============================================================================
# Minimum read coverage helpers
# ==============================================================================

def _minimum_read_coverage_contract(ctx: ValidationContext) -> dict:
    """Get minimum read coverage contract."""
    contract = ctx.contract
    coverage = contract.get("minimum_read_coverage")
    if isinstance(coverage, dict):
        return coverage
    final_contract = contract.get("finalization_contract") if isinstance(contract.get("finalization_contract"), dict) else {}
    coverage = final_contract.get("minimum_read_coverage")
    return coverage if isinstance(coverage, dict) else {}


def _minimum_read_coverage_required(ctx: ValidationContext) -> bool:
    """Check if minimum read coverage is required."""
    coverage = _minimum_read_coverage_contract(ctx)
    if coverage:
        return coverage.get("required") is True
    return ctx.contract.get("coverage_satisfied") is not True


def _minimum_read_coverage_satisfied(ctx: ValidationContext) -> bool:
    """Check if minimum read coverage is satisfied."""
    coverage = _minimum_read_coverage_contract(ctx)
    if coverage:
        return coverage.get("coverage_satisfied") is True
    return ctx.contract.get("coverage_satisfied") is True


def _minimum_read_coverage_missing_owner_paths(ctx: ValidationContext) -> list[str]:
    """Get missing owner paths from coverage contract."""
    coverage = _minimum_read_coverage_contract(ctx)
    raw = coverage.get("missing_owner_paths") if coverage else ctx.contract.get("missing_owner_paths")
    return [str(path) for path in raw] if isinstance(raw, list) else []


def _final_answer_declares_missing_coverage(text: str) -> bool:
    """Check if final answer declares missing coverage."""
    low = str(text or "").lower()
    return any(
        needle in low
        for needle in (
            "coverage_satisfied=false",
            "coverage_satisfied: false",
            '"coverage_satisfied": false',
            "missing_owner_paths",
            "missing coverage",
            "insufficient coverage",
            "copertura mancante",
            "mancanza di copertura",
        )
    )


# ==============================================================================
# Required next tool call helpers
# ==============================================================================

def _coalesce_required_next_missing_paths(ctx: ValidationContext, values: Any) -> list[str]:
    """Coalesce required next missing paths from values."""
    out: list[str] = []
    if not isinstance(values, (list, tuple, set)):
        return out
    for value in values:
        token = ctx.repo_rel_token(value) if ctx.repo_rel_token else str(value)
        if token and token not in out:
            out.append(token)
    return out[:12]


def _stale_required_next_repo_read_paths(ctx: ValidationContext) -> set[str]:
    """Get stale required next repo read paths from contract."""
    paths: set[str] = set()
    for row in ctx.contract.get("stale_required_next_tool_calls") if isinstance(ctx.contract.get("stale_required_next_tool_calls"), list) else []:
        if not isinstance(row, dict):
            continue
        if str(row.get("tool") or "") != "repo_read":
            continue
        args = row.get("arguments") if isinstance(row.get("arguments"), dict) else {}
        for path in args.get("paths", []) if isinstance(args.get("paths"), list) else [args.get("path")]:
            token = ctx.repo_rel_token(path) if ctx.repo_rel_token else str(path)
            if token:
                paths.add(token)
    return paths


def _successful_read_paths_for_final_route(ctx: ValidationContext) -> set[str]:
    """Get successful read paths for final route."""
    successful = set()
    for path in ctx.contract.get("successful_repo_read_paths") if isinstance(ctx.contract.get("successful_repo_read_paths"), list) else []:
        token = ctx.repo_rel_token(path) if ctx.repo_rel_token else str(path)
        if token:
            successful.add(token)
    if not successful and ctx.deps and ctx.successful_read_paths:
        try:
            for path in ctx.successful_read_paths(ctx.history):
                token = ctx.repo_rel_token(path) if ctx.repo_rel_token else str(path)
                if token:
                    successful.add(token)
        except Exception:
            pass
    return successful


def _path_allowed_by_missing_evidence(ctx: ValidationContext, path: str, required_missing: list[str]) -> bool:
    """Check if path is allowed by missing evidence."""
    token = ctx.repo_rel_token(path) if ctx.repo_rel_token else str(path)
    if not token:
        return False
    for item in required_missing:
        required = ctx.repo_rel_token(item) if ctx.repo_rel_token else str(item)
        if not required:
            continue
        if token == required or token.startswith(f"{required}/") or required.startswith(f"{token}/"):
            return True
    return False


def _verified_required_next_missing_paths(ctx: ValidationContext, values: Any) -> tuple[list[str], list[str]]:
    """Verify and separate valid/invalid required next missing paths."""
    valid: list[str] = []
    invalid: list[str] = []
    successful = _successful_read_paths_for_final_route(ctx)
    stale = _stale_required_next_repo_read_paths(ctx)
    conceptual_tokens = {
        "coverage required",
        "read or search pending",
        "missing core candidate paths",
        "missing unverified file mentions",
    }
    for path in _coalesce_required_next_missing_paths(ctx, values):
        if (
            path in conceptual_tokens
            or path.startswith("need_")
            or any(ch.isspace() for ch in path)
        ):
            if path not in invalid:
                invalid.append(path)
            continue
        if path in successful or path in stale:
            if path not in invalid:
                invalid.append(path)
            continue
        if ctx.path_exists_repo_relative and ctx.repo_readable_evidence_file:
            if ctx.path_exists_repo_relative(path) and ctx.repo_readable_evidence_file(path):
                if path not in valid:
                    valid.append(path)
        elif path not in invalid:
            invalid.append(path)
    return valid[:12], invalid[:12]


def _required_next_tool_from_missing_evidences(ctx: ValidationContext, values: Any, allow_if_missing: bool) -> dict[str, Any]:
    """Build required next tool call from missing evidences."""
    iterable_values = values if isinstance(values, (list, tuple, set)) else []
    paths = _coalesce_required_next_missing_paths(ctx, [value for value in iterable_values if isinstance(value, str)])
    if not paths:
        return {}
    paths = [
        path for path in paths
        if path not in _successful_read_paths_for_final_route(ctx)
        and path not in _stale_required_next_repo_read_paths(ctx)
    ]
    if not paths:
        return {}
    return {
        "tool": "repo_read",
        "arguments": {"paths": paths},
        "reason": (
            "Rewrite final from verified evidence requires at least one remaining evidence gap. "
            "Read one of the requested missing paths before final."
        ),
        "allow_only_if_missing_evidence": bool(allow_if_missing),
        "source": "repo_analysis_final_model_quality",
    }


def _coalesce_required_next_tool_tool(ctx: ValidationContext, value: dict[str, Any]) -> dict[str, Any]:
    """Coalesce required next tool call into standard format."""
    tool = str(value.get("tool") or "").strip().lower()
    args = value.get("arguments") if isinstance(value.get("arguments"), dict) else {}
    if not tool:
        return {"tool": "", "arguments": {}, "allow_only_if_missing_evidence": False}
    out = {
        "tool": tool,
        "arguments": args,
        "allow_only_if_missing_evidence": bool(value.get("allow_only_if_missing_evidence")),
        "reason": str(value.get("reason") or "").strip(),
        "source": str(value.get("source") or "repo_analysis_final_model_quality").strip(),
    }
    if tool == "repo_read" and ctx.repo_rel_token:
        if "paths" in args:
            normalized_paths = [
                ctx.repo_rel_token(item)
                for item in args.get("paths", [])
                if ctx.repo_rel_token(item)
            ] if isinstance(args.get("paths"), list) else []
            if normalized_paths:
                out["arguments"] = {"paths": normalized_paths}
            else:
                out["arguments"] = {}
        else:
            path = ctx.repo_rel_token(args.get("path")) if args.get("path") else None
            if path:
                out["arguments"] = {"path": path}
            else:
                out["arguments"] = {}
        if out["arguments"]:
            out["allow_only_if_missing_evidence"] = True
    elif not args:
        out["arguments"] = {}
    return out


def _coerce_final_rewrite_latch(value: Any) -> str:
    """Coerce final rewrite latch to valid value."""
    raw = str(value or "inactive").strip().lower()
    return (
        raw
        if raw in {"inactive", "rewrite_required", "required_gap_only", "terminal_block_required"}
        else "inactive"
    )


def _required_gap_paths_from_quality(ctx: ValidationContext, quality: Mapping, existing_missing: list[str]) -> list[str]:
    """Get required gap paths from quality assessment."""
    raw_missing = (
        quality.get("required_next_missing_evidences")
        if isinstance(quality.get("required_next_missing_evidences"), list)
        else existing_missing
    )
    if not isinstance(raw_missing, list):
        return []
    required_next_missing_evidences = [
        ctx.repo_rel_token(item) for item in raw_missing if ctx.repo_rel_token and ctx.repo_rel_token(item)
    ] if ctx.repo_rel_token else []
    successful = _successful_read_paths_for_final_route(ctx)
    stale = _stale_required_next_repo_read_paths(ctx)
    return [
        path
        for path in required_next_missing_evidences
        if path not in successful and path not in stale and path not in existing_missing
    ]


# ==============================================================================
# Final quality route helper
# ==============================================================================

def _apply_final_quality_route(ctx: ValidationContext, quality: dict, step_index: int) -> None:
    """Apply final quality route to contract. Modifies ctx.contract in place."""
    contract = ctx.contract
    reject_count = int(contract.get("planner_final_quality_reject_count") or 0) + 1
    contract["planner_final_quality_reject_count"] = reject_count
    contract["planner_final_quality_last_rewrite_decision"] = step_index
    contract["planner_cuda_rewrite_required"] = True

    required_next_progress = str(quality.get("required_next_progress") or "").strip()
    if required_next_progress:
        contract["required_next_progress"] = required_next_progress

    required_next_output_sections = (
        quality.get("required_next_output_sections")
        if isinstance(quality.get("required_next_output_sections"), list)
        else []
    )
    if required_next_output_sections:
        contract["required_next_output_sections"] = [
            str(item).strip()
            for item in required_next_output_sections
            if str(item).strip()
        ]

    raw_existing_required_missing = contract.get("required_next_missing_evidences")
    existing_required_missing = [
        path
        for path in _coalesce_required_next_missing_paths(ctx, raw_existing_required_missing if isinstance(raw_existing_required_missing, (list, tuple, set)) else [])
        if path
    ]
    required_next_missing_evidences = _required_gap_paths_from_quality(ctx, quality, existing_missing=existing_required_missing)
    raw_required_next_missing_evidences = required_next_missing_evidences if required_next_missing_evidences else existing_required_missing
    verified_required_missing, invalid_required_missing = _verified_required_next_missing_paths(ctx, raw_required_next_missing_evidences)

    if invalid_required_missing:
        contract["invalid_required_next_missing_evidences"] = invalid_required_missing
        contract["invalid_required_next_missing_evidence_reason"] = (
            "final-quality proposed strings that are not existing readable repo paths; "
            "validator will not turn them into repo_read calls"
        )
    if verified_required_missing:
        contract["required_next_missing_evidences"] = verified_required_missing
    else:
        contract.pop("required_next_missing_evidences", None)
        required_next_missing_evidences = []
        if invalid_required_missing and not contract.get("required_next_progress"):
            contract["required_next_progress"] = (
                "Final-quality proposed no valid unread repo path. Do not call repo_read for "
                "non-existing/prose paths; rewrite final from verified evidence or return a typed block."
            )

    required_next_tool_call = (
        quality.get("required_next_tool_call")
        if isinstance(quality.get("required_next_tool_call"), dict)
        else {}
    )
    raw_contract_missing = contract.get("required_next_missing_evidences")
    contract_missing = raw_contract_missing if isinstance(raw_contract_missing, (list, tuple, set)) else []
    if not required_next_tool_call and contract_missing:
        required_next_tool_call = _required_next_tool_from_missing_evidences(ctx, contract_missing, allow_if_missing=True)

    if required_next_tool_call.get("tool") == "repo_read":
        args = required_next_tool_call.get("arguments") if isinstance(required_next_tool_call.get("arguments"), dict) else {}
        raw_paths: list[Any] = []
        if args.get("path"):
            raw_paths.append(args.get("path"))
        raw_paths.extend(args.get("paths") if isinstance(args.get("paths"), list) else [])
        parsed_paths = [str(p) for p in raw_paths]
        valid_paths = list(parsed_paths[:12])
        if len(valid_paths) == 1:
            args["path"] = valid_paths[0]
            args.pop("paths", None)
        elif len(valid_paths) > 1:
            args["paths"] = valid_paths[:12]
            args.pop("path", None)
        required_next_tool_call["arguments"] = args

    if required_next_tool_call:
        required_next_tool_call = _coalesce_required_next_tool_tool(ctx, required_next_tool_call)
        if not required_next_tool_call.get("tool"):
            required_next_tool_call = {}

    has_gap_route = bool(required_next_tool_call) or bool(required_next_missing_evidences)
    final_rewrite_latch = str(contract.get("final_rewrite_latch") or "inactive").strip().lower()
    if required_next_tool_call:
        pass  # latch already set
    elif final_rewrite_latch != "terminal_block_required":
        final_rewrite_latch = "rewrite_required" if reject_count < 2 else "terminal_block_required"

    contract["final_rewrite_latch"] = final_rewrite_latch
    contract["planner_may_choose_block"] = final_rewrite_latch == "terminal_block_required"
    contract["planner_may_choose_final"] = False


# ==============================================================================
# Duplicate repo read recovery helper
# ==============================================================================

def _apply_duplicate_repo_read_path_recovery_contract(
    ctx: ValidationContext,
    repeated_reads: list[str],
) -> None:
    """Apply duplicate repo read path recovery contract. Modifies ctx.contract in place."""
    contract = ctx.contract
    normalized: list[str] = []
    for path in repeated_reads if isinstance(repeated_reads, list) else []:
        token = ctx.repo_rel_token(path) if ctx.repo_rel_token else str(path)
        if token and token not in normalized:
            normalized.append(token)
    if not normalized:
        return

    forbidden: list[str] = []
    for item in contract.get("forbidden_repeated_repo_read_paths", []):
        if isinstance(item, str):
            token = ctx.repo_rel_token(item) if ctx.repo_rel_token else str(item)
            if token and token not in forbidden:
                forbidden.append(token)
    for token in normalized:
        if token not in forbidden:
            forbidden.append(token)
    if not forbidden:
        return
    contract["forbidden_repeated_repo_read_paths"] = forbidden[:40]
    duplicate_repo_read_recovery_count = (
        contract.get("duplicate_repo_read_recovery_count")
        if isinstance(contract.get("duplicate_repo_read_recovery_count"), dict)
        else {}
    )
    for token in normalized:
        duplicate_repo_read_recovery_count[str(token)] = (
            int(duplicate_repo_read_recovery_count.get(str(token), 0) or 0) + 1
        )
    contract["duplicate_repo_read_recovery_count"] = {
        key: int(value)
        for key, value in duplicate_repo_read_recovery_count.items()
        if str(key).strip()
    }
    contract["required_next_tool_call_advisory"] = {
        "tool": "repo_read",
        "arguments": {"paths": normalized[:12]},
        "reason": "already_successful_full_path_read",
        "source": "duplicate_repo_read_recovery_contract",
    }

    contract.pop("required_next_tool_call", None)
    contract.pop("required_next_tool_call_validated", None)
    contract.pop("required_next_tool_call_validation_source", None)
    contract["required_next_progress"] = (
        "Duplicate repo_read detected. Consume verified evidence windows or rewrite final from existing reads."
    )


# ==============================================================================
# State management helpers
# ==============================================================================

def _clear_final_terminal_block_state(ctx: ValidationContext) -> None:
    """Clear final terminal block state. Modifies ctx.contract in place."""
    contract = ctx.contract
    contract["final_rewrite_latch"] = "inactive"
    contract["planner_may_choose_block"] = False
    contract["planner_may_choose_final"] = True
    for key in (
        "terminal_block_final_retry_count", "planner_forced_terminal_block",
        "planner_forced_terminal_block_reason", "planner_cuda_rewrite_required",
    ):
        contract.pop(key, None)
    final_contract = contract.get("finalization_contract") if isinstance(contract.get("finalization_contract"), dict) else {}
    if isinstance(final_contract, dict):
        final_contract["final_allowed"] = True
        final_contract["planner_may_choose_final"] = True
        final_contract["planner_may_choose_block"] = False
        for key in ("planner_forced_terminal_block", "planner_forced_terminal_block_reason"):
            final_contract.pop(key, None)
        contract["finalization_contract"] = final_contract


def _escalate_final_terminal_block_state(ctx: ValidationContext, has_gap_route: bool) -> None:
    """Escalate to final terminal block state. Modifies ctx.contract in place."""
    contract = ctx.contract
    reject_count = int(contract.get("planner_final_quality_reject_count") or 0) + 1
    contract["planner_final_quality_reject_count"] = reject_count
    contract["planner_cuda_rewrite_required"] = True
    next_latch = "terminal_block_required" if reject_count >= 2 else "rewrite_required"
    contract["final_rewrite_latch"] = next_latch
    contract["planner_may_choose_block"] = next_latch == "terminal_block_required"
    final_contract = contract.get("finalization_contract") if isinstance(contract.get("finalization_contract"), dict) else {}
    if isinstance(final_contract, dict):
        final_contract["final_allowed"] = False
        final_contract["planner_may_choose_final"] = False
        final_contract["reason"] = f"escalated_{next_latch}"
        contract["finalization_contract"] = final_contract


def _next_final_rewrite_latch(current: str, reject_count: int, has_gap_route: bool) -> str:
    """Compute next final rewrite latch state."""
    current = str(current or "").strip().lower()
    if current == "terminal_block_required":
        return current
    if reject_count >= 2:
        return "terminal_block_required"
    if current == "required_gap_only":
        return "required_gap_only" if has_gap_route else "terminal_block_required"
    return "rewrite_required"