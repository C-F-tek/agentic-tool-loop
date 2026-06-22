"""
final_quality_route.py
======================
Logic for applying a final-quality rejection into the evidence contract.

The central function ``apply_final_quality_route`` is called when either
the deterministic or the model-quality judge rejects a ``action=final``
decision.  It updates the contract in-place and decides:

  - which evidence gaps remain (``required_next_missing_evidences``)
  - which tool call should be required next (``required_next_tool_call``)
  - what the new latch state should be
  - whether a terminal block is now forced

All I/O with the caller is through the *contract* dict that is passed in
(and returned for convenience).
"""

from __future__ import annotations

from typing import Any

from aicarmine_broker.application.shared.path_tokens import repo_path_token
from aicarmine_broker.application.tool_surface.required_tool_call import (
    append_stale_required_call_marker,
)

from .path_utils import coalesce_repo_read_paths, is_concrete_repo_path
from .contract_utils import (
    final_quality_repo_read_allowlist,
    required_next_route_has_deterministic_proof,
)
from .rewrite_latch import coerce_latch_state, next_latch_state


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def apply_final_quality_route(
    quality: dict[str, Any],
    contract: dict[str, Any],
    *,
    # Injected dependencies (bound by the caller from deps)
    repo_rel_token,
    path_exists_repo_relative,
    repo_readable_evidence_file,
    successful_read_paths_for_final_route,
    stale_required_next_repo_read_paths,
    history: list[dict[str, Any]],
) -> None:
    """
    Apply a final-quality rejection decision into *contract* (mutated in place).

    Parameters
    ----------
    quality:
        The quality-check result dict (from deterministic or model judge).
    contract:
        The live evidence contract; mutated in place.
    repo_rel_token:
        Injected ``_repo_rel_token`` function from deps.
    path_exists_repo_relative / repo_readable_evidence_file:
        Injected path-existence helpers from deps.
    successful_read_paths_for_final_route / stale_required_next_repo_read_paths:
        Closures over history already computed by the caller.
    history:
        Full planner history list (used only for step index tracking).
    """
    step_index = len(history)

    # Increment reject count once per decision step
    if int(contract.get("planner_final_quality_last_rewrite_decision") or -1) != step_index:
        reject_count = int(contract.get("planner_final_quality_reject_count") or 0) + 1
        contract["planner_final_quality_reject_count"] = reject_count
        contract["planner_final_quality_last_rewrite_decision"] = step_index

    reject_count = int(contract.get("planner_final_quality_reject_count") or 0)
    contract["planner_cuda_rewrite_required"] = True

    # --- Output sections & progress ---
    _apply_required_output_sections(quality, contract)
    required_next_progress = str(quality.get("required_next_progress") or "").strip()
    if required_next_progress:
        contract["required_next_progress"] = required_next_progress

    # --- Evidence gaps ---
    existing_missing = _existing_missing_evidences(contract, repo_rel_token)
    new_missing = _gap_paths_from_quality(
        quality,
        existing_missing=existing_missing,
        repo_rel_token=repo_rel_token,
        successful=successful_read_paths_for_final_route(),
        stale=stale_required_next_repo_read_paths(),
    )
    raw_missing = new_missing if new_missing else existing_missing

    verified_missing, invalid_missing = _verify_missing_paths(
        raw_missing,
        repo_rel_token=repo_rel_token,
        path_exists=path_exists_repo_relative,
        is_readable=repo_readable_evidence_file,
        successful=successful_read_paths_for_final_route(),
        stale=stale_required_next_repo_read_paths(),
    )

    _record_invalid_missing(contract, invalid_missing, verified_missing)

    # --- Required next tool call ---
    invalid_tool_paths: list[str] = []
    required_next_tool_call = _build_required_next_tool_call(
        quality=quality,
        contract=contract,
        verified_missing=verified_missing,
        repo_rel_token=repo_rel_token,
        invalid_tool_paths_out=invalid_tool_paths,
    )

    if invalid_tool_paths:
        contract["invalid_required_next_tool_call_paths"] = invalid_tool_paths[:12]

    required_next_tool_call = _validate_and_filter_tool_call(
        required_next_tool_call,
        contract=contract,
        verified_missing=verified_missing,
        repo_rel_token=repo_rel_token,
        path_exists=path_exists_repo_relative,
        is_readable=repo_readable_evidence_file,
        successful=successful_read_paths_for_final_route(),
        stale=stale_required_next_repo_read_paths(),
    )

    # --- Compute new latch and update finalization contract ---
    has_gap_route = bool(required_next_tool_call) or bool(verified_missing)

    if required_next_tool_call:
        new_latch = next_latch_state(
            str(contract.get("final_rewrite_latch") or ""),
            reject_count=reject_count,
            has_gap_route=has_gap_route,
        )
    else:
        # No runnable tool call: choose between terminal block and rewrite
        new_latch = _handle_no_tool_call(
            contract=contract,
            reject_count=reject_count,
            verified_missing=verified_missing,
        )

    contract["final_rewrite_latch"] = new_latch
    contract["planner_may_choose_block"] = new_latch == "terminal_block_required"
    contract["planner_may_choose_final"] = False

    final_contract = _get_or_create_final_contract(contract)
    final_contract["final_allowed"] = False
    final_contract["planner_may_choose_final"] = False

    if new_latch == "terminal_block_required":
        final_contract.update(
            {
                "planner_may_choose_block": True,
                "planner_forced_terminal_block": True,
                "planner_forced_terminal_block_reason": (
                    "repo_analysis_final_quality_no_runnable_gap_terminal_block"
                ),
                "reason": "repo_analysis_final_quality_no_runnable_gap_terminal_block",
            }
        )
    else:
        final_contract.update(
            {
                "planner_may_choose_block": False,
                "reason": "repo_analysis_final_model_quality_rejected_no_runnable_gap",
            }
        )

    contract["finalization_contract"] = final_contract

    if required_next_tool_call:
        contract["required_next_tool_call"] = required_next_tool_call


# ---------------------------------------------------------------------------
# Duplicate repo_read recovery
# ---------------------------------------------------------------------------

def apply_duplicate_repo_read_path_recovery_contract(
    contract: dict[str, Any],
    repeated_reads: list[str],
    history: list[dict[str, Any]],
    *,
    repo_rel_token,
    decision_paths,
    minimum_read_coverage_satisfied,
) -> dict[str, Any]:
    """
    Update *contract* after detecting a duplicate ``repo_read`` for already-
    successful paths.  Returns the updated contract.
    """
    contract = contract if isinstance(contract, dict) else {}

    normalized = _normalize_repeated_reads(repeated_reads, repo_rel_token)
    if not normalized:
        return contract

    # Accumulate forbidden list
    forbidden = _build_forbidden_list(contract, normalized, repo_rel_token)
    contract["forbidden_repeated_repo_read_paths"] = forbidden[:40]

    # Update per-path recovery counts
    counts = _update_recovery_counts(contract, normalized)
    contract["duplicate_repo_read_recovery_count"] = counts

    contract["required_next_tool_call_advisory"] = {
        "tool": "repo_read",
        "arguments": {"paths": normalized[:12]},
        "reason": "already_successful_full_path_read",
        "source": "duplicate_repo_read_recovery_contract",
    }

    # If there is a pending required_next_tool_call that overlaps, mark it stale
    _maybe_mark_required_call_stale(contract, normalized, history, repo_rel_token, decision_paths)

    contract.pop("required_next_tool_call", None)
    contract.pop("required_next_tool_call_validated", None)
    contract.pop("required_next_tool_call_validation_source", None)
    contract["required_next_progress"] = (
        "Duplicate repo_read detected. "
        "Consume verified evidence windows or rewrite final from existing reads."
    )

    final_contract = _get_or_create_final_contract(contract)

    if minimum_read_coverage_satisfied():
        _handle_coverage_satisfied_after_duplicate(contract, final_contract)

    if _threshold_reached(counts, normalized):
        _handle_threshold_reached(contract, final_contract)

    contract["finalization_contract"] = final_contract
    return contract


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _apply_required_output_sections(quality: dict[str, Any], contract: dict[str, Any]) -> None:
    sections = quality.get("required_next_output_sections")
    if isinstance(sections, list):
        clean = [str(s).strip() for s in sections if str(s).strip()]
        if clean:
            contract["required_next_output_sections"] = clean


def _existing_missing_evidences(
    contract: dict[str, Any], repo_rel_token
) -> list[str]:
    raw = contract.get("required_next_missing_evidences")
    if not isinstance(raw, (list, tuple, set)):
        return []
    return [t for t in (_coalesce_missing_paths(raw, repo_rel_token)) if t]


def _coalesce_missing_paths(values: Any, repo_rel_token) -> list[str]:
    out: list[str] = []
    if not isinstance(values, (list, tuple, set)):
        return out
    for value in values:
        token = repo_rel_token(value)
        if token and token not in out:
            out.append(token)
    return out[:12]


def _gap_paths_from_quality(
    quality: dict[str, Any],
    *,
    existing_missing: list[str],
    repo_rel_token,
    successful: set[str],
    stale: set[str],
) -> list[str]:
    raw = quality.get("required_next_missing_evidences")
    if not isinstance(raw, list):
        return []
    tokens = [repo_rel_token(item) for item in raw if repo_rel_token(item)]
    return [
        p for p in tokens
        if p not in successful and p not in stale and p not in existing_missing
    ]


def _verify_missing_paths(
    values: Any,
    *,
    repo_rel_token,
    path_exists,
    is_readable,
    successful: set[str],
    stale: set[str],
) -> tuple[list[str], list[str]]:
    valid: list[str] = []
    invalid: list[str] = []
    conceptual = {
        "coverage required",
        "read or search pending",
        "missing core candidate paths",
        "missing unverified file mentions",
    }
    for path in _coalesce_missing_paths(values, repo_rel_token):
        if path in conceptual or path.startswith("need_") or any(ch.isspace() for ch in path):
            if path not in invalid:
                invalid.append(path)
            continue
        if path in successful or path in stale:
            if path not in invalid:
                invalid.append(path)
            continue
        if path_exists(path) and is_readable(path):
            if path not in valid:
                valid.append(path)
        elif path not in invalid:
            invalid.append(path)
    return valid[:12], invalid[:12]


def _record_invalid_missing(
    contract: dict[str, Any],
    invalid_missing: list[str],
    verified_missing: list[str],
) -> None:
    if invalid_missing:
        contract["invalid_required_next_missing_evidences"] = invalid_missing
        contract["invalid_required_next_missing_evidence_reason"] = (
            "final-quality proposed strings that are not existing readable repo paths; "
            "validator will not turn them into repo_read calls"
        )
    if verified_missing:
        contract["required_next_missing_evidences"] = verified_missing
    else:
        contract.pop("required_next_missing_evidences", None)
        if invalid_missing and not contract.get("required_next_progress"):
            contract["required_next_progress"] = (
                "Final-quality proposed no valid unread repo path. "
                "Do not call repo_read for non-existing/prose paths; "
                "rewrite final from verified evidence or return a typed block."
            )


def _build_required_next_tool_call(
    *,
    quality: dict[str, Any],
    contract: dict[str, Any],
    verified_missing: list[str],
    repo_rel_token,
    invalid_tool_paths_out: list[str],
) -> dict[str, Any]:
    """Build, filter and return a candidate required_next_tool_call, or {}."""
    required_next_tool_call = (
        quality.get("required_next_tool_call")
        if isinstance(quality.get("required_next_tool_call"), dict)
        else {}
    )

    # Derive from missing evidences if not already supplied
    if not required_next_tool_call and verified_missing:
        required_next_tool_call = _tool_call_from_missing_evidences(
            verified_missing, allow_if_missing=True, repo_rel_token=repo_rel_token
        )

    if required_next_tool_call.get("tool") != "repo_read":
        return required_next_tool_call

    # Filter repo_read paths against the allowlist
    args = required_next_tool_call.get("arguments") if isinstance(required_next_tool_call.get("arguments"), dict) else {}
    raw_paths: list[Any] = []
    if args.get("path"):
        raw_paths.append(args["path"])
    raw_paths.extend(args.get("paths") if isinstance(args.get("paths"), list) else [])
    parsed_paths = coalesce_repo_read_paths(raw_paths)

    allowlist = final_quality_repo_read_allowlist(contract)
    valid_paths: list[str] = []
    for path in parsed_paths:
        if path in allowlist or not allowlist:
            valid_paths.append(path)
        elif path not in invalid_tool_paths_out:
            invalid_tool_paths_out.append(path)

    if not valid_paths:
        return {}

    new_args = dict(args)
    if len(valid_paths) == 1:
        new_args["path"] = valid_paths[0]
        new_args.pop("paths", None)
    else:
        new_args["paths"] = valid_paths[:12]
        new_args.pop("path", None)
    required_next_tool_call = dict(required_next_tool_call)
    required_next_tool_call["arguments"] = new_args
    return required_next_tool_call


def _tool_call_from_missing_evidences(
    values: Any,
    *,
    allow_if_missing: bool,
    repo_rel_token,
) -> dict[str, Any]:
    iterable = values if isinstance(values, (list, tuple, set)) else []
    paths = _coalesce_missing_paths(
        [v for v in iterable if isinstance(v, str)], repo_rel_token
    )
    if not paths:
        return {}
    return {
        "tool": "repo_read",
        "arguments": {"paths": paths},
        "reason": (
            "Rewrite final from verified evidence requires at least one remaining "
            "evidence gap.  Read one of the requested missing paths before final."
        ),
        "allow_only_if_missing_evidence": bool(allow_if_missing),
        "source": "repo_analysis_final_model_quality",
    }


def _coalesce_required_next_tool(value: dict[str, Any], repo_rel_token) -> dict[str, Any]:
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
    if tool == "repo_read":
        out["arguments"] = _normalize_repo_read_args(args, repo_rel_token)
        if out["arguments"]:
            out["allow_only_if_missing_evidence"] = True
    elif not args:
        out["arguments"] = {}
    return out


def _normalize_repo_read_args(args: dict[str, Any], repo_rel_token) -> dict[str, Any]:
    if "paths" in args:
        normalized = [
            repo_rel_token(item)
            for item in (args.get("paths") if isinstance(args.get("paths"), list) else [])
            if repo_rel_token(item)
        ]
        return {"paths": normalized} if normalized else {}
    path = repo_rel_token(args.get("path"))
    return {"path": path} if path else {}


def _validate_and_filter_tool_call(
    call: dict[str, Any],
    *,
    contract: dict[str, Any],
    verified_missing: list[str],
    repo_rel_token,
    path_exists,
    is_readable,
    successful: set[str],
    stale: set[str],
) -> dict[str, Any]:
    if not call:
        return {}
    call = _coalesce_required_next_tool(call, repo_rel_token)
    if not required_next_route_has_deterministic_proof(call, contract):
        _record_undeterministic_call(call, contract)
        return {}
    if call.get("tool") != "repo_read":
        return call if call.get("arguments") else {}

    # Verify repo_read paths
    required_args = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
    raw_required = (
        required_args.get("paths")
        if isinstance(required_args.get("paths"), list)
        else [required_args.get("path")]
    )
    verified_tool, invalid_tool = _verify_missing_paths(
        raw_required,
        repo_rel_token=repo_rel_token,
        path_exists=path_exists,
        is_readable=is_readable,
        successful=successful,
        stale=stale,
    )
    if invalid_tool:
        contract["invalid_required_next_tool_call_paths"] = invalid_tool
        contract["invalid_required_next_tool_call_reason"] = (
            "repo_read required_next_tool_call contained non-existing or non-readable paths"
        )
    if verified_missing:
        verified_tool = [
            p for p in verified_tool
            if _path_allowed_by_missing_evidence(p, verified_missing, repo_rel_token)
        ]
    if not verified_tool:
        return {}
    call["arguments"] = {"paths": verified_tool}
    return call


def _record_undeterministic_call(call: dict[str, Any], contract: dict[str, Any]) -> None:
    tool_name = str(call.get("tool") or "").strip()
    args = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
    path_token = repo_path_token(args.get("path") if args.get("path") else "")
    query_text = str(
        args.get("query") or args.get("pattern") or args.get("symbol")
        or args.get("needle") or args.get("text") or ""
    ).strip()
    if path_token:
        contract["invalid_required_next_tool_call_paths"] = [path_token]
    if query_text:
        contract["invalid_required_next_tool_call_query"] = query_text[:260]
    contract["invalid_required_next_tool_call_reason"] = (
        f"{tool_name or 'required_next_tool_call'} lacked deterministic concrete route proof"
    )


def _path_allowed_by_missing_evidence(
    path: str, required_missing: list[str], repo_rel_token
) -> bool:
    token = repo_rel_token(path)
    if not token:
        return False
    for item in required_missing:
        required = repo_rel_token(item)
        if not required:
            continue
        if (
            token == required
            or token.startswith(f"{required}/")
            or required.startswith(f"{token}/")
        ):
            return True
    return False


def _handle_no_tool_call(
    *,
    contract: dict[str, Any],
    reject_count: int,
    verified_missing: list[str],
) -> str:
    """Handle the case where no runnable tool call is available and return new latch."""
    contract.pop("required_next_tool_call", None)
    contract.pop("required_next_tool_call_validated", None)
    contract.pop("required_next_tool_call_validation_source", None)

    new_latch = "terminal_block_required" if reject_count >= 2 else "rewrite_required"

    if new_latch == "rewrite_required":
        if verified_missing:
            contract["required_next_progress"] = (
                "Final-quality rejected with concrete, verified evidence gaps but no runnable "
                "required_next_tool_call.  You must rewrite the final answer by explicitly "
                f"addressing the remaining required gaps: {verified_missing[:8]}"
            )
        else:
            contract["required_next_progress"] = (
                "Final-quality rejected without a concrete runnable gap route.  "
                "Continue rewrite from verified evidence only; "
                "do not emit block unless a controller-forced terminal decision is present."
            )
    elif not contract.get("required_next_progress"):
        contract["required_next_progress"] = (
            "Final-quality rejected with no concrete evidence gap and no runnable "
            "required_next_tool_call.  Rewrite action=final from verified evidence only; "
            "do not call non-evidence tools."
        )

    if new_latch == "terminal_block_required":
        contract["planner_may_choose_block"] = True
        contract["planner_forced_terminal_block"] = True
        contract["planner_forced_terminal_block_reason"] = (
            "repo_analysis_final_quality_no_runnable_gap_terminal_block"
        )
    else:
        contract["planner_may_choose_block"] = False

    return new_latch


def _get_or_create_final_contract(contract: dict[str, Any]) -> dict[str, Any]:
    fc = contract.get("finalization_contract")
    return fc if isinstance(fc, dict) else {}


# ---------------------------------------------------------------------------
# Duplicate repo_read recovery helpers
# ---------------------------------------------------------------------------

def _normalize_repeated_reads(repeated_reads: list[str], repo_rel_token) -> list[str]:
    out: list[str] = []
    for path in (repeated_reads if isinstance(repeated_reads, list) else []):
        token = repo_rel_token(path)
        if token and token not in out:
            out.append(token)
    return out


def _build_forbidden_list(
    contract: dict[str, Any], normalized: list[str], repo_rel_token
) -> list[str]:
    forbidden: list[str] = []
    for item in contract.get("forbidden_repeated_repo_read_paths", []):
        if isinstance(item, str):
            token = repo_rel_token(item)
            if token and token not in forbidden:
                forbidden.append(token)
    for token in normalized:
        if token not in forbidden:
            forbidden.append(token)
    return forbidden


def _update_recovery_counts(
    contract: dict[str, Any], normalized: list[str]
) -> dict[str, int]:
    counts = (
        contract.get("duplicate_repo_read_recovery_count")
        if isinstance(contract.get("duplicate_repo_read_recovery_count"), dict)
        else {}
    )
    for token in normalized:
        counts[str(token)] = int(counts.get(str(token), 0) or 0) + 1
    return {k: int(v) for k, v in counts.items() if str(k).strip()}


def _maybe_mark_required_call_stale(
    contract: dict[str, Any],
    normalized: list[str],
    history: list[dict[str, Any]],
    repo_rel_token,
    decision_paths,
) -> None:
    required_next_tool_call = (
        contract.get("required_next_tool_call")
        if isinstance(contract.get("required_next_tool_call"), dict)
        else {}
    )
    if not required_next_tool_call:
        return
    required_tool = str(required_next_tool_call.get("tool") or "").strip()
    required_args = (
        required_next_tool_call.get("arguments")
        if isinstance(required_next_tool_call.get("arguments"), dict)
        else {}
    )
    if required_tool != "repo_read":
        return
    required_paths = decision_paths(required_args)
    if not any(p in normalized for p in required_paths):
        return
    last_step = history[-1].get("step") if history and isinstance(history[-1], dict) else None
    append_stale_required_call_marker(
        contract,
        {
            "tool": required_tool,
            "arguments": required_args,
            "satisfied": True,
            "reason": "repo_read_already_successful",
            "path_overlap": normalized,
            "step": last_step,
        },
    )


def _handle_coverage_satisfied_after_duplicate(
    contract: dict[str, Any], final_contract: dict[str, Any]
) -> None:
    latch = coerce_latch_state(contract.get("final_rewrite_latch"))
    if latch == "inactive":
        contract["planner_may_choose_final"] = True
        final_contract["final_allowed"] = True
        final_contract["planner_may_choose_final"] = True
    else:
        final_contract["final_allowed"] = False
        final_contract["planner_may_choose_final"] = False
        final_contract["reason"] = "duplicate_repo_read_recovery_active_rewrite_latch"
    coverage = contract.get("minimum_read_coverage")
    if isinstance(coverage, dict):
        contract["coverage_satisfied"] = coverage.get("coverage_satisfied", True)


def _threshold_reached(counts: dict[str, int], normalized: list[str]) -> bool:
    return any(int(counts.get(p, 0) or 0) >= 2 for p in normalized)


def _handle_threshold_reached(
    contract: dict[str, Any], final_contract: dict[str, Any]
) -> None:
    contract["required_next_progress"] = (
        "Duplicate repo_read recovery crossed retry threshold.  "
        "Return a rewrite constrained to verified evidence or explicit terminal "
        "blocker if controller-forced."
    )
    contract["planner_may_choose_block"] = True
    contract["planner_may_choose_final"] = False
    final_contract.update(
        {
            "planner_forced_terminal_block": True,
            "planner_forced_terminal_block_reason": (
                "duplicate_repo_read_recovery_count_threshold_reached"
            ),
            "planner_may_choose_block": True,
            "final_allowed": False,
            "planner_may_choose_final": False,
            "reason": "duplicate_repo_read_recovery_count_threshold_reached",
        }
    )