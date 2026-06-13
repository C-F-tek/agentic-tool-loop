"""Planner evidence contract builder owner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from aicarmine_broker.application.evidence.coverage_scorer import score_evidence_coverage
from aicarmine_broker.application.planner.required_progress import required_next_progress_from_text
from aicarmine_broker.application.tool_surface.candidate_action_gate import gate_candidate_actions
from aicarmine_broker.application.tool_surface.action_proof_ledger import attach_action_proof
from aicarmine_broker.application.tool_surface.batch_contract import canonical_batch_call_key
from aicarmine_broker.planner_core.cache import CACHEABLE_READ_TOOLS


POST_WRITE_VALIDATION_TOOLS = frozenset({
    "repo_validate",
    "repo_ruff_check",
    "repo_pyright_check",
    "repo_pytest_run",
})
POST_WRITE_TOOL_NAMES = frozenset({"repo_apply_patch", "repo_write_file"})
MICRO_BATCH_MAX_ACTIONS = 8
_PREPLANNER_GOAL_CLASSES = frozenset({
    "analysis_only",
    "code_security_analysis",
    "repo_analysis",
    "code_product_report",
    "apply_write",
    "generic",
})


def _preplanner_semantic_intent_from_orientation(
    initial_orientation_surface: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(initial_orientation_surface, Mapping):
        return {}
    preplanner_rag = initial_orientation_surface.get("preplanner_rag")
    if not isinstance(preplanner_rag, Mapping):
        return {}
    ranking = preplanner_rag.get("ranking")
    if not isinstance(ranking, Mapping):
        return {}
    query_plan = ranking.get("query_plan")
    if not isinstance(query_plan, Mapping):
        return {}
    intent = query_plan.get("semantic_intent")
    if not isinstance(intent, Mapping):
        return {}
    if str(intent.get("schema") or "") != "agentic_loop_preplanner_semantic_intent.v1":
        return {}
    goal_class = str(intent.get("goal_class") or "").strip()
    if goal_class not in _PREPLANNER_GOAL_CLASSES:
        return {}
    return {str(key): value for key, value in intent.items()}


def _semantic_classification_with_preplanner_intent(
    fallback: Mapping[str, Any],
    preplanner_intent: Mapping[str, Any],
) -> dict[str, Any]:
    classification = dict(fallback if isinstance(fallback, Mapping) else {})
    if not isinstance(preplanner_intent, Mapping):
        return classification
    if str(preplanner_intent.get("source") or "") != "planner_query_plan":
        return classification
    goal_class = str(preplanner_intent.get("goal_class") or "").strip()
    if goal_class not in _PREPLANNER_GOAL_CLASSES:
        return classification

    contract_class = goal_class
    if goal_class in {"repo_analysis", "generic"}:
        contract_class = "analysis_only"
    code_product_requested = bool(preplanner_intent.get("code_product_requested"))
    if goal_class == "code_product_report" and not code_product_requested:
        contract_class = "analysis_only"
    must_code_product = goal_class == "code_product_report" and code_product_requested
    requires_security = bool(preplanner_intent.get("requires_code_security_coverage")) or (
        goal_class == "code_security_analysis"
    )
    requested = {
        "apply_write": "apply/edit/fix/write",
        "code_product_report": "report-only code product",
        "code_security_analysis": "code/security repository analysis",
        "repo_analysis": "repository analysis",
        "analysis_only": "general answer with evidence",
        "generic": "general answer with evidence",
    }.get(goal_class, str(classification.get("requested_deliverable") or "general answer with evidence"))

    classification.update({
        "schema": "planner_goal_classification.v1",
        "class": contract_class,
        "confidence": max(float(classification.get("confidence") or 0.0), 0.9),
        "reason": "controlled preplanner semantic intent",
        "requested_deliverable": requested,
        "must_produce_code_product": must_code_product,
        "requires_code_security_coverage": requires_security,
        "regex_code_product_override": False,
        "regex_apply_override": False,
        "code_product_requested": code_product_requested,
        "preplanner_semantic_intent": dict(preplanner_intent),
        "preplanner_goal_class": goal_class,
    })
    return classification


def _goal_requests_code_product_from_semantics(
    *,
    fallback_value: bool,
    preplanner_intent: Mapping[str, Any],
) -> bool:
    if (
        isinstance(preplanner_intent, Mapping)
        and str(preplanner_intent.get("source") or "") == "planner_query_plan"
    ):
        return (
            str(preplanner_intent.get("goal_class") or "").strip() == "code_product_report"
            and preplanner_intent.get("code_product_requested") is True
        )
    return bool(fallback_value)


def _goal_requests_apply_from_semantics(
    *,
    fallback_value: bool,
    preplanner_intent: Mapping[str, Any],
) -> bool:
    if (
        isinstance(preplanner_intent, Mapping)
        and str(preplanner_intent.get("source") or "") == "planner_query_plan"
    ):
        return str(preplanner_intent.get("goal_class") or "").strip() == "apply_write"
    return bool(fallback_value)


def _micro_batch_contract_from_candidates(
    candidates: list[dict[str, Any]],
    *,
    max_actions: int = MICRO_BATCH_MAX_ACTIONS,
) -> dict[str, Any]:
    """Expose independent read-only candidate actions that may share one planner turn."""
    allowed_actions: list[dict[str, Any]] = []
    seen_call_keys: set[str] = set()
    seen_action_ids: set[str] = set()
    for action in candidates if isinstance(candidates, list) else []:
        if not isinstance(action, dict):
            continue
        tool = str(action.get("tool") or "").strip()
        if tool not in CACHEABLE_READ_TOOLS:
            continue
        args = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
        call_key = canonical_batch_call_key(tool, args)
        if call_key in seen_call_keys:
            continue
        action_id = str(action.get("action_id") or "").strip()
        if not action_id or action_id in seen_action_ids:
            continue
        seen_call_keys.add(call_key)
        seen_action_ids.add(action_id)
        allowed_actions.append({
            "action_id": action_id,
            "tool": tool,
            "arguments": args,
            "reason": action.get("reason"),
            "source": action.get("source"),
            "independent_read_only": True,
        })
    limit = max(1, int(max_actions or MICRO_BATCH_MAX_ACTIONS))
    visible_actions = allowed_actions[:limit]
    return {
        "schema": "planner_micro_batch_contract.v1",
        "allowed": len(visible_actions) >= 2,
        "mode": "native_message_tool_calls_only",
        "max_batch_size": min(limit, len(visible_actions)) if visible_actions else 0,
        "allowed_tools": sorted({str(action.get("tool") or "") for action in visible_actions}),
        "allowed_batch_actions": visible_actions,
        "candidate_action_count": len(candidates) if isinstance(candidates, list) else 0,
        "batchable_candidate_count": len(visible_actions),
        "guard": (
            "Multiple native message.tool_calls are accepted only when every call "
            "matches one allowed_batch_actions entry by tool and sanitized arguments. "
            "Write/apply/command/validation/final actions remain single-step and separately validated."
        ),
        "writes_allowed": False,
        "validation_tools_allowed": False,
        "reason": (
            "at_least_two_independent_read_only_candidates"
            if len(visible_actions) >= 2 else
            "fewer_than_two_independent_read_only_candidates"
        ),
    }


def _history_result(row: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    result = row.get("tool_result") if isinstance(row.get("tool_result"), dict) else {}
    if result:
        return result
    return row if row.get("tool") else {}


def _collect_result_paths(
    value: Any,
    *,
    repo_rel_token: Callable[[Any], str],
    output: list[str],
) -> None:
    if value in (None, "", [], {}):
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _collect_result_paths(item, repo_rel_token=repo_rel_token, output=output)
        return
    if isinstance(value, dict):
        for key in ("path", "paths", "target", "targets", "target_file", "modified_paths"):
            if key in value:
                _collect_result_paths(value.get(key), repo_rel_token=repo_rel_token, output=output)
        return
    path = repo_rel_token(value)
    if path and path != "." and path not in output:
        output.append(path)


def _tool_result_paths(result: dict[str, Any], *, repo_rel_token: Callable[[Any], str]) -> list[str]:
    paths: list[str] = []
    for key in ("modified_paths", "paths", "path", "target", "targets", "target_file"):
        _collect_result_paths(result.get(key), repo_rel_token=repo_rel_token, output=paths)
    compile_resolution = (
        result.get("compile_target_resolution")
        if isinstance(result.get("compile_target_resolution"), dict)
        else {}
    )
    _collect_result_paths(compile_resolution.get("targets"), repo_rel_token=repo_rel_token, output=paths)
    return paths


def _path_covers_target(path: str, target: str) -> bool:
    path = str(path or "").strip().strip("/")
    target = str(target or "").strip().strip("/")
    if not path or not target:
        return False
    return path == target or target.startswith(path + "/") or path.startswith(target + "/")


def _validation_covers_modified_files(validation_paths: list[str], modified_files: list[str]) -> bool:
    if not modified_files:
        return True
    if not validation_paths:
        return True
    return all(
        any(_path_covers_target(path, target) for path in validation_paths)
        for target in modified_files
    )


def _post_write_validation_candidates(
    modified_files: list[str],
    *,
    validation_failed: bool,
) -> list[dict[str, Any]]:
    paths = modified_files[:8]
    candidates: list[dict[str, Any]] = []
    if validation_failed and paths:
        candidates.append({
            "tool": "repo_read",
            "arguments": {"paths": paths, "max_chars": 50000},
            "reason": "post_write_validation_failed_read_modified_files",
            "source": "post_write_validation_contract",
        })
    validate_args: dict[str, Any] = {"timeout_seconds": 300}
    if paths:
        validate_args["paths"] = paths
    candidates.append({
        "tool": "repo_validate",
        "arguments": validate_args,
        "reason": "post_write_validation_required",
        "source": "post_write_validation_contract",
    })
    python_paths = [path for path in paths if path.endswith(".py")]
    if python_paths:
        candidates.append({
            "tool": "repo_ruff_check",
            "arguments": {"paths": python_paths, "timeout_seconds": 180},
            "reason": "post_write_python_validation_candidate",
            "source": "post_write_validation_contract",
        })
    return candidates


def _post_write_validation_contract(
    history: list[dict[str, Any]],
    *,
    repo_rel_token: Callable[[Any], str],
) -> dict[str, Any]:
    write_events: list[dict[str, Any]] = []
    for index, row in enumerate(history if isinstance(history, list) else []):
        result = _history_result(row)
        tool = str(result.get("tool") or "")
        if tool not in POST_WRITE_TOOL_NAMES or result.get("ok") is not True:
            continue
        if tool == "repo_apply_patch" and result.get("changed") is False:
            continue
        paths = _tool_result_paths(result, repo_rel_token=repo_rel_token)
        write_events.append({
            "index": index,
            "tool": tool,
            "paths": paths,
            "changed": result.get("changed"),
        })

    modified_files: list[str] = []
    for event in write_events:
        for path in event.get("paths") or []:
            if path not in modified_files:
                modified_files.append(path)

    latest_write_index = max((int(event["index"]) for event in write_events), default=-1)
    validation_events: list[dict[str, Any]] = []
    for index, row in enumerate(history if isinstance(history, list) else []):
        if index <= latest_write_index:
            continue
        result = _history_result(row)
        tool = str(result.get("tool") or "")
        if tool not in POST_WRITE_VALIDATION_TOOLS:
            continue
        paths = _tool_result_paths(result, repo_rel_token=repo_rel_token)
        covers_modified_files = _validation_covers_modified_files(paths, modified_files)
        validation_events.append({
            "index": index,
            "tool": tool,
            "ok": result.get("ok") is True,
            "paths": paths,
            "covers_modified_files": covers_modified_files,
            "returncode": result.get("returncode"),
            "error": result.get("error"),
        })

    latest_covering_validation = next(
        (event for event in reversed(validation_events) if event.get("covers_modified_files")),
        {},
    )
    validation_done = bool(latest_covering_validation and latest_covering_validation.get("ok") is True)
    validation_failed = bool(latest_covering_validation and latest_covering_validation.get("ok") is not True)
    status = (
        "not_required"
        if not write_events else
        "passed"
        if validation_done else
        "failed"
        if validation_failed else
        "pending"
    )
    return {
        "schema": "post_write_validation_contract.v1",
        "required": bool(write_events),
        "status": status,
        "validation_done": validation_done,
        "validation_failed": validation_failed,
        "required_after_tools": sorted(POST_WRITE_TOOL_NAMES),
        "accepted_validation_tools": sorted(POST_WRITE_VALIDATION_TOOLS),
        "modified_files": modified_files[:32],
        "latest_write_index": latest_write_index if latest_write_index >= 0 else None,
        "write_events": write_events[-8:],
        "validation_events_after_latest_write": validation_events[-8:],
        "latest_validation": latest_covering_validation or None,
        "candidate_next_actions": _post_write_validation_candidates(
            modified_files,
            validation_failed=validation_failed,
        ) if write_events and not validation_done else [],
    }


@dataclass(frozen=True)
class EvidenceBuilder:
    """Owner for planner evidence contract construction."""

    _deps: Mapping[str, Any]
    _config: Mapping[str, Any]

    def build(
        self,
        goal: str,
        history: list[dict[str, Any]],
        intrinsic_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        deps = self._deps
        config = self._config
        CODE_PRODUCT_BUILD_STATE_KIND = config["CODE_PRODUCT_BUILD_STATE_KIND"]
        LAB_REPO = config["LAB_REPO"]
        REPO_CONCRETE_READ_TARGET = config["REPO_CONCRETE_READ_TARGET"]
        SCOPED_CONCRETE_READ_TARGET = config["SCOPED_CONCRETE_READ_TARGET"]
        _agentic_v2_decision_paths = deps["agentic_v2_decision_paths"]
        _agentic_v2_enrich_evidence_contract = deps["agentic_v2_enrich_evidence_contract"]
        _agentic_v2_goal_scope = deps["agentic_v2_goal_scope"]
        _apply_turn_surface_policy = deps["apply_turn_surface_policy"]
        _build_operational_notebook = deps["build_operational_notebook"]
        _candidate_actions_from_evidence = deps["candidate_actions_from_evidence"]
        _canonical_invalid_code_product_decision_signature = deps["canonical_invalid_code_product_decision_signature"]
        _compact_validation_rejections_tail = deps["compact_validation_rejections_tail"]
        _core_discovery_candidates_from_intrinsic = deps["core_discovery_candidates_from_intrinsic"]
        _disallowed_invalid_code_product_signatures = deps["disallowed_invalid_code_product_signatures"]
        _file_memory_from_history = deps["file_memory_from_history"]
        _goal_exact_text_block = deps["goal_exact_text_block"]
        _goal_target_file = deps["goal_target_file"]
        _goal_target_kind = deps["goal_target_kind"]
        _initial_orientation_surface_from_history = deps["initial_orientation_surface_from_history"]
        _input_error_goal = deps["input_error_goal"]
        _low_signal_top_dir = deps["low_signal_top_dir"]
        _meaningful_read_candidates_from_evidence = deps["meaningful_read_candidates_from_evidence"]
        _path_exists_repo_relative = deps["path_exists_repo_relative"]
        _path_under_scope = deps["path_under_scope"]
        _paths_from_list_rows = deps["paths_from_list_rows"]
        _paths_from_result = deps["paths_from_result"]
        _rank_core_candidates = deps["rank_core_candidates"]
        _repo_analysis_goal = deps["repo_analysis_goal"]
        _repo_code_file = deps["repo_code_file"]
        _repo_doc_or_config = deps["repo_doc_or_config"]
        _repo_list_evidence = deps["repo_list_evidence"]
        _repo_readable_evidence_file = deps["repo_readable_evidence_file"]
        _repo_rel_token = deps["repo_rel_token"]
        _repo_required_read_count = deps["repo_required_read_count"]
        _scope_read_candidates_from_evidence = deps["scope_read_candidates_from_evidence"]
        _scoped_required_read_count = deps["scoped_required_read_count"]
        _user_scope_claims = deps["user_scope_claims"]
        _verified_repo_read_content_rows = deps["verified_repo_read_content_rows"]
        goal_requested_repo_scope = deps["goal_requested_repo_scope"]
        goal_requests_apply = deps["goal_requests_apply"]
        goal_requests_code_product = deps["goal_requests_code_product"]
        goal_requests_python_file_review = deps["goal_requests_python_file_review"]
        history_has_tool = deps["history_has_tool"]
        latest_file_list_result = deps["latest_file_list_result"]
        requested_file_limit_from_goal = deps["requested_file_limit_from_goal"]
        semantic_goal_classification = deps["semantic_goal_classification"]
        successful_repo_read_paths = deps["successful_repo_read_paths"]
        failed_repo_read_paths = deps["failed_repo_read_paths"]
        failed_repo_list_files_paths = deps["failed_repo_list_files_paths"]
        goal_requires_code_security_coverage = deps["goal_requires_code_security_coverage"]

        fallback_semantic_classification = semantic_goal_classification(goal)
        fallback_goal_requests_apply_value = goal_requests_apply(goal)
        fallback_goal_requests_code_product_value = goal_requests_code_product(goal)
        latest_list = latest_file_list_result(history)
        known_paths = _paths_from_result(latest_list) if latest_list else []
        requested_limit = requested_file_limit_from_goal(goal, 0)
        target_file = _goal_target_file(goal)
        target_scope = _agentic_v2_goal_scope(goal, {}) or goal_requested_repo_scope(goal)
        target_kind = _goal_target_kind(goal)
        read_ok = successful_repo_read_paths(history)
        verified_read_rows = _verified_repo_read_content_rows(history)
        verified_read_paths = [str(row.get("path")) for row in verified_read_rows if row.get("path")]
        verified_read_path_set = set(verified_read_paths)
        missing_full_content_reads = [
            p for p in read_ok
            if p not in verified_read_path_set and _repo_readable_evidence_file(p)
        ]
        read_failed = failed_repo_read_paths(history)
        list_failed = failed_repo_list_files_paths(history)
        list_rows = _repo_list_evidence(history)
        all_listed_paths = _paths_from_list_rows(list_rows)
        semantic_search_paths: list[str] = []
        for row in history if isinstance(history, list) else []:
            if not isinstance(row, dict):
                continue
            result = row.get("tool_result") if isinstance(row.get("tool_result"), dict) else {}
            if str(result.get("tool") or "") != "repo_semantic_search" or not result.get("ok"):
                continue
            for path in _paths_from_result(result):
                p = _repo_rel_token(path)
                if (
                    p
                    and p not in semantic_search_paths
                    and _path_exists_repo_relative(p)
                    and _repo_readable_evidence_file(p)
                ):
                    semantic_search_paths.append(p)
        file_memory = _file_memory_from_history(history)
        initial_orientation_surface = _initial_orientation_surface_from_history(history)
        preplanner_rag = (
            initial_orientation_surface.get("preplanner_rag")
            if isinstance(initial_orientation_surface.get("preplanner_rag"), dict)
            else {}
        )
        preplanner_semantic_intent = _preplanner_semantic_intent_from_orientation(
            initial_orientation_surface
        )
        semantic_classification = _semantic_classification_with_preplanner_intent(
            fallback_semantic_classification,
            preplanner_semantic_intent,
        )
        goal_requests_apply_value = _goal_requests_apply_from_semantics(
            fallback_value=fallback_goal_requests_apply_value,
            preplanner_intent=preplanner_semantic_intent,
        )
        goal_requests_code_product_value = _goal_requests_code_product_from_semantics(
            fallback_value=fallback_goal_requests_code_product_value,
            preplanner_intent=preplanner_semantic_intent,
        )
        ranked_preplanner_paths = [
            _repo_rel_token(path)
            for path in (
                initial_orientation_surface.get("ranked_preplanner_paths")
                if isinstance(initial_orientation_surface.get("ranked_preplanner_paths"), list)
                else []
            )
            if _repo_rel_token(path)
        ]
        selected_preplanner_paths = [
            _repo_rel_token(path)
            for path in (
                initial_orientation_surface.get("selected_paths")
                if isinstance(initial_orientation_surface.get("selected_paths"), list)
                else []
            )
            if _repo_rel_token(path)
        ]
        ranked_orientation_done = bool(
            str(preplanner_rag.get("schema") or "") == "agentic_loop_preplanner_rag_preseed.v1"
            and preplanner_rag.get("selected_paths") not in (None, "", [], {})
            and ranked_preplanner_paths
        )
        doc_reads = [p for p in verified_read_paths if _repo_doc_or_config(p)]
        doc_baseline_sufficient = bool(len(doc_reads) >= 3 or (ranked_orientation_done and len(doc_reads) >= 2))
        code_reads = [p for p in verified_read_paths if _repo_code_file(p)]
        root_surface_done = any(
            row.get("path") in ("", ".") for row in list_rows
        ) or any(
            isinstance(item, dict)
            and (item.get("tool_result") or {}).get("tool") == "repo_tree"
            and (item.get("tool_result") or {}).get("ok")
            for item in history if isinstance(item, dict)
        )
        orientation_surface_done = bool(root_surface_done or ranked_orientation_done)
        meaningful_lists = [
            row.get("path") for row in list_rows
            if row.get("path") not in (None, "", ".") and not _low_signal_top_dir(str(row.get("path")))
        ]
        area_scoped_meaningful_content_reads = [
            p for p in verified_read_paths
            if any(_path_under_scope(p, str(area)) for area in meaningful_lists)
            and _repo_readable_evidence_file(p)
        ]
        ranked_meaningful_content_reads = [
            p for p in verified_read_paths
            if p in ranked_preplanner_paths
            and not _repo_doc_or_config(p)
            and not _low_signal_top_dir(p)
            and _repo_readable_evidence_file(p)
        ]
        meaningful_content_reads: list[str] = []
        for p in [*area_scoped_meaningful_content_reads, *ranked_meaningful_content_reads]:
            if p not in meaningful_content_reads:
                meaningful_content_reads.append(p)
        meaningful_evidence_available = bool(meaningful_lists or ranked_meaningful_content_reads)
        repo_available_read_candidates = _meaningful_read_candidates_from_evidence(list_rows)
        code_available_read_candidates = [
            p for p in repo_available_read_candidates
            if _repo_code_file(p)
        ]
        for path in [*all_listed_paths, *known_paths]:
            p = _repo_rel_token(path)
            if p and _repo_code_file(p) and p not in code_available_read_candidates:
                code_available_read_candidates.append(p)
        repo_required_read_count = _repo_required_read_count(repo_available_read_candidates)
        repo_goal = _repo_analysis_goal(goal)
        code_security_coverage_required = bool(repo_goal and goal_requires_code_security_coverage(goal))
        code_security_read_required = (
            min(5, len(code_available_read_candidates))
            if code_available_read_candidates
            else 3
        )
        code_security_coverage_sufficient = bool(
            not code_security_coverage_required
            or len(code_reads) >= code_security_read_required
        )
        repo_goal_class = str(semantic_classification.get("class") or "")
        orientative_repo_final_goal = (
            repo_goal
            and repo_goal_class in {"analysis_only", "action_plan_only"}
            and not bool(semantic_classification.get("must_produce_code_product"))
            and not goal_requests_apply_value
        )
        repo_final_required_read_count = (
            min(repo_required_read_count, 10)
            if orientative_repo_final_goal
            else repo_required_read_count
        )
        scoped_inspection = bool(target_scope)
        file_read_done = bool(target_file and target_file in verified_read_path_set)
        scope_listed = bool(target_scope and any(_path_under_scope(str(row.get("path") or ""), target_scope) and str(row.get("path") or ".") not in ("", ".") for row in list_rows))
        scope_content_reads = [
            p for p in verified_read_paths
            if target_scope
            and _path_under_scope(p, target_scope)
            and _repo_readable_evidence_file(p)
        ]
        scope_available_read_candidates = _scope_read_candidates_from_evidence(list_rows, target_scope) if target_scope else []
        scope_required_read_count = _scoped_required_read_count(scope_available_read_candidates) if target_scope else 0
        user_scope_claims = _user_scope_claims(goal, target_scope)
        core_discovery_candidates, core_discovery_status = _core_discovery_candidates_from_intrinsic(
            intrinsic_context=intrinsic_context,
            list_rows=list_rows,
            read_ok=read_ok,
            target_scope=target_scope,
            user_scope_claims=user_scope_claims,
        )
        validator_admissible_read_paths: list[str] = []
        for path in (
            known_paths
            + all_listed_paths
            + repo_available_read_candidates
            + scope_available_read_candidates
            + semantic_search_paths
            + [
                str(item.get("path") or "")
                for item in core_discovery_candidates
                if isinstance(item, dict)
            ]
            + read_ok
        ):
            p = _repo_rel_token(path)
            if p and p not in validator_admissible_read_paths:
                validator_admissible_read_paths.append(p)
        final_allowed = False
        final_reason = "No generic final fallback. Final requires explicit evidence for the actual goal."
        if _input_error_goal(goal):
            final_allowed = False
            final_reason = "Bridge/input error: missing natural-language user request. Do not invent a repository-analysis goal."
        elif target_kind == "file":
            final_allowed = file_read_done
            final_reason = (
                f"File evidence exists for {target_file}: direct repo_read succeeded."
                if final_allowed else
                f"Need direct repo_read evidence for requested file {target_file}."
            )
        elif scoped_inspection:
            final_allowed = bool(scope_listed and len(scope_content_reads) >= scope_required_read_count)
            final_reason = (
                f"Scoped evidence exists for {target_scope}: in-scope tree/list and "
                f"{len(scope_content_reads)}/{scope_required_read_count} verified concrete readable file reads."
                if final_allowed else
                f"Need scoped evidence for {target_scope}: repo_tree/list under scope and "
                f"{len(scope_content_reads)}/{scope_required_read_count} verified concrete readable file reads "
                f"(up to {SCOPED_CONCRETE_READ_TARGET}, bounded by discovered candidates)."
            )
        elif repo_goal:
            strict_repo_evidence_sufficient = bool(
                orientation_surface_done
                and doc_baseline_sufficient
                and meaningful_evidence_available
                and len(meaningful_content_reads) >= repo_required_read_count
            )
            analysis_repo_evidence_sufficient = bool(
                orientative_repo_final_goal
                and orientation_surface_done
                and doc_baseline_sufficient
                and meaningful_evidence_available
                and len(meaningful_content_reads) >= 1
                and len(verified_read_rows) >= repo_final_required_read_count
            )
            final_allowed = bool(strict_repo_evidence_sufficient or analysis_repo_evidence_sufficient)
            final_reason = (
                (
                    "Analysis/action-plan repository evidence exists: root/ranked orientation, baseline docs/config reads, "
                    f"one meaningful non-infra/code area/read set, "
                    f"{len(meaningful_content_reads)} verified reads "
                    f"inside meaningful areas, and {len(verified_read_rows)}/{repo_final_required_read_count} "
                    "total verified content reads. The 20-read target remains orientative, not a hard final gate."
                )
                if analysis_repo_evidence_sufficient and not strict_repo_evidence_sufficient else
                (
                    "Codex-quality repository evidence exists: root/ranked orientation, baseline docs/config reads, "
                    f"one meaningful non-infra/code area/read set, and {len(meaningful_content_reads)}/"
                    f"{repo_required_read_count} verified concrete readable reads inside meaningful areas."
                )
                if final_allowed else
                (
                    "Need root/ranked orientation + baseline markdown/config reads + one meaningful non-infra/code area/read set "
                    f"+ {len(meaningful_content_reads)}/{repo_final_required_read_count} verified concrete readable reads "
                    "for analysis/action-plan finalization "
                    f"(target {REPO_CONCRETE_READ_TARGET} remains orientative and bounded by discovered candidates)."
                )
            )
        else:
            # Non-repository goals may still finish only after a planner final with
            # evidence. Do not use this branch to auto-legitimize a one-step repo_tree.
            final_allowed = bool(read_ok or meaningful_lists)
            final_reason = (
                "Non-repository goal has some executed evidence." if final_allowed
                else "Need at least one relevant tool result; no generic final fallback."
            )
        if goal_requests_apply_value and not history_has_tool(history, "repo_apply_patch"):
            final_allowed = False
            final_reason = "Apply/edit/write goal requires repo_apply_patch after verified repo_read old_text evidence."
        if code_security_coverage_required and not code_security_coverage_sufficient:
            final_allowed = False
            final_reason = (
                "Code/security/semantic critique goal requires verified source-code reads before finalization: "
                f"{len(code_reads)}/{code_security_read_required} code reads available. "
                "Do not claim absence of issues; continue with repo_list_files/repo_read over code paths."
            )

        core_candidates = _rank_core_candidates(file_memory, list_rows)
        candidates = _candidate_actions_from_evidence(
            goal,
            file_memory,
            list_rows,
            read_ok,
            final_allowed,
            list_failed,
            core_discovery_candidates,
        )
        explicit_request_context = (
            intrinsic_context.get("explicit_request_context")
            if isinstance(intrinsic_context, dict)
            and isinstance(intrinsic_context.get("explicit_request_context"), dict)
            else {}
        )
        explicit_request_tool = str(explicit_request_context.get("target_internal_tool") or "").strip()
        explicit_request_args = (
            explicit_request_context.get("target_arguments")
            if isinstance(explicit_request_context.get("target_arguments"), dict)
            else {}
        )
        explicit_request_target_covered = bool(
            explicit_request_tool
            and explicit_request_tool != "repo_read"
            and history_has_tool(history, explicit_request_tool)
        )
        explicit_request_target_pending = bool(
            explicit_request_tool
            and explicit_request_tool != "repo_read"
            and not explicit_request_target_covered
        )
        if explicit_request_target_pending:
            final_allowed = False
            final_reason = (
                "Structured explicit_request_context target "
                f"{explicit_request_tool} has not been covered by the runtime loop yet. "
                "Planner must attempt the target native tool with target_arguments, or return a typed block/unavailable result."
            )
        explicit_request_read_paths: list[str] = []
        if explicit_request_tool == "repo_read":
            raw_targets: list[Any] = []
            if explicit_request_args.get("path") not in (None, "", [], {}):
                raw_targets.append(explicit_request_args.get("path"))
            if isinstance(explicit_request_args.get("paths"), list):
                raw_targets.extend(explicit_request_args.get("paths") or [])
            for raw_target in raw_targets:
                if isinstance(raw_target, dict):
                    continue
                p = _repo_rel_token(raw_target)
                if (
                    p
                    and p != "."
                    and p not in explicit_request_read_paths
                    and p not in read_ok
                    and _path_exists_repo_relative(p)
                    and _repo_readable_evidence_file(p)
                ):
                    explicit_request_read_paths.append(p)
            for p in reversed(explicit_request_read_paths):
                try:
                    max_chars = int(explicit_request_args.get("max_chars") or 10000)
                except Exception:
                    max_chars = 10000
                action = {
                    "tool": "repo_read",
                    "arguments": {"path": p, "max_chars": max(1000, min(max_chars, 50000))},
                    "reason": "explicit_request_context_target_read",
                    "source": "explicit_request_context",
                }
                if not any(
                    isinstance(item, dict)
                    and item.get("tool") == "repo_read"
                    and _repo_rel_token((item.get("arguments") or {}).get("path") or "") == p
                    for item in candidates
                    if isinstance(item, dict)
                ):
                    candidates.insert(0, action)
        elif explicit_request_tool:
            action = {
                "tool": explicit_request_tool,
                "arguments": dict(explicit_request_args),
                "reason": "explicit_request_context_target_tool",
                "source": "explicit_request_context",
            }
            if not any(
                isinstance(item, dict)
                and str(item.get("tool") or "").strip() == explicit_request_tool
                and (item.get("arguments") if isinstance(item.get("arguments"), dict) else {}) == explicit_request_args
                for item in candidates
            ):
                candidates.insert(0, action)
        apply_preloop_candidate_paths: list[str] = []
        for raw_path in [*ranked_preplanner_paths, *selected_preplanner_paths]:
            p = _repo_rel_token(raw_path)
            if p and p != "." and p not in apply_preloop_candidate_paths:
                apply_preloop_candidate_paths.append(p)
        apply_target_files: list[str] = []
        goal_low = str(goal or "").lower().replace("\\", "/")

        def add_apply_target(path: str) -> None:
            p = _repo_rel_token(path)
            if (
                p
                and p != "."
                and p not in apply_target_files
                and _path_exists_repo_relative(p)
                and _repo_readable_evidence_file(p)
            ):
                apply_target_files.append(p)

        if goal_requests_apply_value:
            add_apply_target(target_file)
            for path in apply_preloop_candidate_paths:
                low_path = path.lower()
                basename = low_path.rsplit("/", 1)[-1]
                goal_mentions_path = low_path in goal_low or basename in goal_low
                goal_mentions_agents_alias = basename == "agents.md" and "agenti" in goal_low
                if goal_mentions_path or goal_mentions_agents_alias:
                    add_apply_target(path)
        post_write_validation_contract = _post_write_validation_contract(
            history,
            repo_rel_token=_repo_rel_token,
        )
        post_write_validation_required = bool(post_write_validation_contract.get("required"))
        post_write_validation_done = bool(post_write_validation_contract.get("validation_done"))
        post_write_validation_failed = bool(post_write_validation_contract.get("validation_failed"))
        post_write_validation_status = str(post_write_validation_contract.get("status") or "")
        post_write_validation_candidates = [
            item for item in (
                post_write_validation_contract.get("candidate_next_actions")
                if isinstance(post_write_validation_contract.get("candidate_next_actions"), list)
                else []
            )
            if isinstance(item, dict)
        ]
        apply_patch_done = any(
            isinstance(event, dict) and event.get("tool") == "repo_apply_patch"
            for event in (
                post_write_validation_contract.get("write_events")
                if isinstance(post_write_validation_contract.get("write_events"), list)
                else []
            )
        )
        apply_verified_target_reads = [
            p for p in apply_target_files
            if p in verified_read_path_set
        ]
        apply_unread_target_files = [
            p for p in apply_target_files
            if p not in verified_read_path_set
        ]
        apply_write_contract = {
            "schema": "apply_write_contract.v1",
            "required": bool(goal_requests_apply_value),
            "required_tool": "repo_apply_patch" if goal_requests_apply_value else None,
            "patch_applied": bool(apply_patch_done),
            "target_files": apply_target_files[:8],
            "verified_target_reads": apply_verified_target_reads[:8],
            "unread_target_files": apply_unread_target_files[:8],
            "preloop_target_candidate_paths": apply_preloop_candidate_paths[:16],
            "target_source": "resolved_goal_file_and_preloop_rag_target_candidates",
            "generic_discovery_allowed": False if goal_requests_apply_value and not apply_patch_done else None,
            "post_write_validation_required": bool(post_write_validation_required),
            "post_write_validation_status": post_write_validation_status or None,
        }
        if post_write_validation_required and not post_write_validation_done:
            final_allowed = False
            candidates = post_write_validation_candidates
            if post_write_validation_failed:
                final_reason = (
                    "Post-write validation failed after repo_apply_patch/repo_write_file. "
                    "Planner must inspect the validation result and fix, revalidate, or return a typed block; final is disallowed."
                )
            else:
                final_reason = (
                    "Post-write validation is required after repo_apply_patch/repo_write_file. "
                    "Planner must call repo_validate or another deterministic validation tool over modified files before final."
                )
        if goal_requests_apply_value and not apply_patch_done:
            final_allowed = False
            if not apply_target_files:
                candidates = []
                final_reason = (
                    "Apply/edit/write goal did not resolve a concrete existing target file. "
                    "Planner must return a typed block instead of generic repository discovery."
                )
            elif apply_unread_target_files:
                candidates = [{
                    "tool": "repo_read",
                    "arguments": {"paths": apply_unread_target_files[:6], "max_chars": 50000},
                    "reason": "apply_write_preloop_target_read_required",
                    "source": "apply_write_contract",
                }]
                final_reason = (
                    "Apply/edit/write goal requires repo_read of every concrete apply target before repo_apply_patch."
                )
            else:
                candidates = [
                    item for item in candidates
                    if isinstance(item, dict)
                    and str(item.get("tool") or "") in {
                        "repo_apply_patch",
                        "repo_validate",
                        "repo_git_apply_check",
                    }
                ]
                final_reason = (
                    "Apply/edit/write target files are read. Planner must call repo_apply_patch with old_text "
                    "verified from required_working_set.repo_reads, or return a typed block."
                )
        candidate_repo_read_paths: list[str] = []
        for action in candidates:
            if not isinstance(action, dict) or action.get("tool") != "repo_read":
                continue
            args = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
            raw_paths: list[Any] = []
            if args.get("path") not in (None, "", [], {}):
                raw_paths.append(args.get("path"))
            if isinstance(args.get("paths"), list):
                raw_paths.extend(args.get("paths") or [])
            for raw_path in raw_paths:
                if isinstance(raw_path, dict):
                    continue
                p = _repo_rel_token(raw_path)
                if (
                    p
                    and p != "."
                    and p not in candidate_repo_read_paths
                    and p not in read_ok
                    and _path_exists_repo_relative(p)
                    and _repo_readable_evidence_file(p)
                ):
                    candidate_repo_read_paths.append(p)
        for p in candidate_repo_read_paths:
            if p not in validator_admissible_read_paths:
                validator_admissible_read_paths.append(p)
        code_product_required = bool(semantic_classification.get("must_produce_code_product")) and not goal_requests_apply_value
        code_product_history_required = bool(code_product_required or goal_requests_code_product_value)
        if code_product_history_required:
            successful_code_edit_proposals = deps["successful_code_edit_proposals"]
            code_product_proposals = successful_code_edit_proposals(history)
        else:
            code_product_proposals = []
        latest_code_product = code_product_proposals[-1] if code_product_proposals else {}
        if latest_code_product:
            _code_product_payload_violations = deps["code_product_payload_violations"]
            latest_code_product_violations = _code_product_payload_violations(
                latest_code_product,
                verified_read_path_set,
            )
        else:
            latest_code_product_violations = (
                ["missing_code_product_candidate"] if code_product_required else []
            )
        code_product_blocks_final = code_product_required and bool(latest_code_product_violations)
        code_product_candidate_target = ""
        code_product_candidate_line_count = 0
        code_product_build_state: dict[str, Any] = {}
        if code_product_blocks_final:
            candidate_paths = [target_file]
            ranked_code_reads = sorted(
                [
                    row for row in verified_read_rows
                    if _repo_code_file(str(row.get("path") or ""))
                    and (
                        target_file
                        or (
                            not str(row.get("path") or "").endswith("__init__.py")
                            and not str(row.get("path") or "").endswith("__main__.py")
                            and int(row.get("line_count") or 0) >= 20
                        )
                    )
                ],
                key=lambda row: (
                    str(row.get("path") or "").endswith("__init__.py"),
                    str(row.get("path") or "").endswith("__main__.py"),
                    -int(row.get("line_count") or 0),
                    str(row.get("path") or ""),
                ),
            )
            candidate_paths.extend(str(row.get("path") or "") for row in ranked_code_reads)
            if target_file:
                candidate_paths.extend([*code_reads, *scope_content_reads, *verified_read_paths])
            for candidate_path in candidate_paths:
                p = _repo_rel_token(candidate_path)
                if p and p != "." and p in verified_read_path_set:
                    code_product_candidate_target = p
                    for row in verified_read_rows:
                        if _repo_rel_token(row.get("path") or "") == p:
                            try:
                                code_product_candidate_line_count = int(row.get("line_count") or 0)
                            except Exception:
                                code_product_candidate_line_count = 0
                            break
                    break
        if code_product_history_required:
            _latest_code_product_build_state = deps["latest_code_product_build_state"]
            code_product_build_state = _latest_code_product_build_state(
                history,
                code_product_candidate_target or target_file,
            )
        if (
            code_product_blocks_final
            and not code_product_candidate_target
            and _repo_rel_token(code_product_build_state.get("target_file") or "") in verified_read_path_set
        ):
            code_product_candidate_target = _repo_rel_token(code_product_build_state.get("target_file") or "")
        if code_product_blocks_final:
            final_allowed = False
            final_reason = (
                "Code-product goal requires repo_propose_code_edit ok=true before final. "
                "Latest code-product violations: "
                + ", ".join(str(v) for v in latest_code_product_violations)
            )
            if code_product_candidate_target:
                _code_product_candidate_action = deps["code_product_candidate_action"]
                code_candidate = _code_product_candidate_action(
                    target_file=code_product_candidate_target,
                    latest_violations=latest_code_product_violations,
                    goal=goal,
                )
                if code_candidate and not any(
                    item.get("tool") == "repo_propose_code_edit"
                    and (item.get("arguments") or {}).get("target_file") == code_product_candidate_target
                    for item in candidates
                    if isinstance(item, dict)
                ):
                    candidates.insert(0, code_candidate)

        validation_rejections: list[dict[str, Any]] = []
        for item in history if isinstance(history, list) else []:
            result = item.get("tool_result") if isinstance(item, dict) and isinstance(item.get("tool_result"), dict) else {}
            if result.get("tool") == "controller_guard" or result.get("violations"):
                validation_rejections.append({
                    "step": item.get("step"),
                    "guard_type": result.get("guard_type"),
                    "summary": result.get("summary"),
                    "classification": result.get("classification"),
                    "semantic_goal_classification": result.get("semantic_goal_classification"),
                    "next_instruction": result.get("next_instruction"),
                    "action_plan_candidate": result.get("action_plan_candidate"),
                    "raw_planner_text_preview": result.get("raw_planner_text_preview"),
                    "violations": result.get("violations") or [],
                    "rejected_decision": result.get("rejected_decision") or {},
                    "invalid_decision_signature": (
                        result.get("invalid_decision_signature")
                        if isinstance(result.get("invalid_decision_signature"), dict)
                        else _canonical_invalid_code_product_decision_signature(
                            result.get("rejected_decision") if isinstance(result.get("rejected_decision"), dict) else {},
                            result.get("violations") if isinstance(result.get("violations"), list) else [],
                        )
                    ),
                })
            elif code_product_history_required:
                _failed_code_edit_proposal_validation_row = deps["failed_code_edit_proposal_validation_row"]
                failed_code_edit_row = _failed_code_edit_proposal_validation_row(item)
                if failed_code_edit_row:
                    failed_code_edit_row["invalid_decision_signature"] = (
                        failed_code_edit_row.get("invalid_decision_signature")
                        if isinstance(failed_code_edit_row.get("invalid_decision_signature"), dict)
                        else _canonical_invalid_code_product_decision_signature(
                            failed_code_edit_row.get("rejected_decision")
                            if isinstance(failed_code_edit_row.get("rejected_decision"), dict) else {},
                            failed_code_edit_row.get("violations")
                            if isinstance(failed_code_edit_row.get("violations"), list) else [],
                        )
                    )
                    validation_rejections.append(failed_code_edit_row)
        action_plan_candidate = ""
        for row in reversed(validation_rejections):
            candidate = str(row.get("action_plan_candidate") or "").strip()
            if candidate:
                action_plan_candidate = candidate
                break
        disallowed_invalid_decision_signatures = _disallowed_invalid_code_product_signatures(
            validation_rejections
        )

        contract = {
            "contract_type": "planner_decides_controller_validates",
            "planner_must_decide_next_action": True,
            "controller_may_reject_but_must_not_replace_planner_reasoning": True,
            "controller_must_not_auto_read_or_auto_final": True,
            "semantic_goal_classification": semantic_classification,
            "preplanner_semantic_intent": preplanner_semantic_intent or None,
            "goal_requests_python_file_review": goal_requests_python_file_review(goal),
            "goal_requests_code_product": goal_requests_code_product_value,
            "goal_requires_code_product_report": code_product_required,
            "goal_requests_apply": goal_requests_apply_value,
            "apply_write_contract": apply_write_contract,
            "post_write_validation_contract": post_write_validation_contract,
            "action_plan_candidate": action_plan_candidate or None,
            "requested_file_limit": requested_limit or None,
            "target_kind": target_kind,
            "resolved_goal_file": target_file or None,
            "resolved_goal_scope": target_scope or None,
            "known_paths_from_latest_repo_list_files": known_paths[:120],
            "known_paths_total_in_latest_digest": len(known_paths),
            "successful_repo_read_paths": read_ok[:160],
            "successful_repo_read_count": len(read_ok),
            "verified_content_read_count": len(verified_read_rows),
            "verified_content_reads": verified_read_rows[:160],
            "missing_full_content_reads": missing_full_content_reads[:160],
            "user_scope_claims": user_scope_claims[:12],
            "core_discovery_status": core_discovery_status,
            "core_discovery_candidates": core_discovery_candidates[:16],
            "explicit_request_context": {
                "target_internal_tool": explicit_request_tool,
                "target_arguments": explicit_request_args,
                "admissible_read_paths": explicit_request_read_paths,
                "target_tool_covered": explicit_request_target_covered,
                "target_tool_pending": explicit_request_target_pending,
                "source": "original_args.context",
            } if explicit_request_context else {},
            "scoped_concrete_read_target": SCOPED_CONCRETE_READ_TARGET if target_scope else None,
            "scoped_concrete_read_required": scope_required_read_count or None,
            "scoped_available_read_candidates": scope_available_read_candidates[:120],
            "scoped_concrete_read_count": len(scope_content_reads),
            "repo_concrete_read_target": REPO_CONCRETE_READ_TARGET if repo_goal else None,
            "repo_concrete_read_target_is_orientative": bool(orientative_repo_final_goal) if repo_goal else None,
            "repo_concrete_read_required": repo_final_required_read_count if repo_goal else None,
            "repo_concrete_read_strict_required": repo_required_read_count if repo_goal else None,
            "repo_available_read_candidates": repo_available_read_candidates[:160] if repo_goal else [],
            "repo_concrete_read_count": len(meaningful_content_reads) if repo_goal else None,
            "repo_goal_final_target_is_orientative": bool(orientative_repo_final_goal) if repo_goal else None,
            "code_security_coverage": {
                "schema": "code_security_coverage_gate.v1",
                "required": code_security_coverage_required,
                "source_code_read_required": code_security_read_required if code_security_coverage_required else 0,
                "source_code_read_count": len(code_reads),
                "source_code_reads": code_reads[:80],
                "source_code_candidates": code_available_read_candidates[:120],
                "verdict_allowed": code_security_coverage_sufficient,
                "allowed_conclusion": (
                    "code_security_verdict_allowed"
                    if code_security_coverage_sufficient else
                    "partial_findings_only"
                ),
                "forbidden_claims_when_not_allowed": [
                    "no security issues",
                    "no critical issues identified",
                    "nessuna criticita",
                    "nessuna criticità",
                    "repository is secure",
                    "intrinsecamente sicura",
                ],
            },
            "failed_repo_read_paths": read_failed[:120],
            "failed_repo_list_files_paths": list_failed[:120],
            "repo_list_files_evidence": list_rows[-10:],
            "file_memory": file_memory[:32],
            "ranked_core_candidate_dirs": core_candidates,
            "candidate_next_actions": candidates,
            "disallowed_next_decision_signatures": disallowed_invalid_decision_signatures,
            "planner_may_choose_final": final_allowed,
            "read_admissible_paths": validator_admissible_read_paths[:400],
            "validator_admissible_repo_read_paths": validator_admissible_read_paths[:400],
            "code_product_contract": {
                "required": code_product_required,
                "required_tool": "repo_propose_code_edit" if code_product_required else None,
                "successful_proposal_count": len(code_product_proposals),
                "latest_target_file": latest_code_product.get("target_file") if latest_code_product else None,
                "candidate_target_file": code_product_candidate_target or None,
                "candidate_target_line_count": code_product_candidate_line_count or None,
                "candidate_payload_must_be_generated_from_required_working_set": bool(
                    code_product_candidate_target
                    and not (_goal_exact_text_block(goal, "old_text") and _goal_exact_text_block(goal, "new_text"))
                    and code_product_blocks_final
                ),
                "action_plan_candidate_available": bool(action_plan_candidate),
                "latest_edit_kind": latest_code_product.get("edit_kind") if latest_code_product else None,
                "latest_payload_complete": bool(latest_code_product and not latest_code_product_violations),
                "latest_violations": latest_code_product_violations if code_product_required else [],
                "build_state": {
                    k: v for k, v in code_product_build_state.items()
                    if k not in {"state", "ready_arguments"} and v not in (None, "", [], {})
                } if code_product_build_state else {},
                "build_state_status": code_product_build_state.get("status") if code_product_build_state else None,
                "build_state_payload_loaded": bool(code_product_build_state.get("payload_loaded")) if code_product_build_state else False,
                "build_state_complete_payload_ready": bool(code_product_build_state.get("complete_payload_ready")) if code_product_build_state else False,
                "inline_payload_required": True,
                "artifact_path_is_not_payload": True,
                "full_payload_fields": [
                    "unified_diff",
                    "structured_operations",
                    "validation_commands",
                    "target_file",
                    "edit_kind",
                ],
                "disallowed_next_decision_signatures": disallowed_invalid_decision_signatures,
            },
            "validation_rejections_tail": _compact_validation_rejections_tail(validation_rejections, limit=5),
            "project_powershell_access": {
                "tool": "terminal_run_command_wait",
                "cwd": str(LAB_REPO),
                "privilege_boundary": "current 3572 Python process user; not UAC elevation",
                "dangerous_commands_require_user_consent": True,
                "use_for": "rg/select-string, dir/tree, git status/diff, python -m compileall, targeted diagnostics under the project folder",
            },
            "finalization_contract": {
                "final_allowed": final_allowed,
                "reason": final_reason,
                "planner_may_choose_final": final_allowed,
                "controller_must_not_auto_final": True,
                "final_is_not_required": True,
                "verified_content_read_count": len(verified_read_rows),
                "verified_content_reads": verified_read_rows[:160],
                "missing_full_content_reads": missing_full_content_reads[:160],
                "code_product_required": code_product_required,
                "code_product_required_tool": "repo_propose_code_edit" if code_product_required else None,
                "code_product_latest_violations": latest_code_product_violations if code_product_required else [],
                "minimum_evidence_for_this_goal_kind": (
                    "For code diff/refactoring proposals: read the target with repo_read, then call repo_propose_code_edit with a complete unified_diff, structured_operations, or explicit no_op rationale."
                    if code_product_required else
                    "For explicit file inspection: direct repo_read of the requested file."
                    if target_kind == "file" else
                    f"For explicit directory inspection: list/tree the requested directory and read up to "
                    f"{SCOPED_CONCRETE_READ_TARGET} verified concrete readable files discovered under it; "
                    "if fewer are discovered, read all discovered candidates."
                    if target_kind == "directory" else
                    "For generic repository structure/content analysis: root surface or ranked preplanner orientation, "
                    "baseline markdown/config reads, one evidence-derived meaningful non-infra/code area/read set, "
                    "and enough verified content reads for the "
                    f"current goal. For analysis/action-plan goals the {REPO_CONCRETE_READ_TARGET}-read target is orientative; "
                    f"{repo_final_required_read_count} verified reads can satisfy finalization when concrete evidence is present."
                ),
            },
            "agentic_codex_quality": {
                "enabled": True,
                "repo_goal": repo_goal,
                "deep_repo_goal": repo_goal,
                "target_kind": target_kind,
                "target_file": target_file or None,
                "target_scope": target_scope or None,
                "root_surface_done": root_surface_done,
                "ranked_orientation_done": ranked_orientation_done,
                "orientation_surface_done": orientation_surface_done,
                "ranked_preplanner_paths": ranked_preplanner_paths[:40],
                "selected_preplanner_paths": selected_preplanner_paths[:40],
                "doc_read_count": len(doc_reads),
                "doc_reads": doc_reads[:80],
                "doc_baseline_sufficient": doc_baseline_sufficient,
                "code_read_count": len(code_reads),
                "code_reads": code_reads[:80],
                "code_security_coverage_required": code_security_coverage_required,
                "code_security_verdict_allowed": code_security_coverage_sufficient,
                "meaningful_non_root_list_count": len(meaningful_lists),
                "meaningful_non_root_lists": meaningful_lists[:20],
                "ranked_meaningful_content_reads": ranked_meaningful_content_reads[:40],
                "meaningful_content_read_count": len(meaningful_content_reads),
                "meaningful_content_reads": meaningful_content_reads[:40],
                "verified_content_read_count": len(verified_read_rows),
                "verified_content_reads": verified_read_rows[:80],
                "missing_full_content_reads": missing_full_content_reads[:80],
                "ranked_core_candidate_dirs": core_candidates,
                "core_discovery_candidates": core_discovery_candidates[:12],
                "top_core_seen": bool(core_candidates),
                "quality_gate": (
                    "direct file read"
                    if target_kind == "file" else
                    f"in-scope list/tree + {scope_required_read_count} in-scope verified concrete readable reads"
                    if target_kind == "directory" else
                    "root_or_ranked_orientation + baseline docs/config reads + one evidence-derived non-infra/code area/read set "
                    f"+ {repo_final_required_read_count} verified concrete readable reads"
                ),
                "hardcoded_core_path": False,
            },
            "initial_orientation_surface": initial_orientation_surface,
        }
        contract = _agentic_v2_enrich_evidence_contract(contract, goal, history)
        contract["operational_notes"] = _build_operational_notebook(goal, contract)
        if code_product_blocks_final:
            _code_product_action_has_complete_payload = deps["code_product_action_has_complete_payload"]
            _code_product_build_state_propose_action = deps["code_product_build_state_propose_action"]
            _code_product_build_state_read_action = deps["code_product_build_state_read_action"]
            _code_product_build_state_write_action = deps["code_product_build_state_write_action"]
            _code_product_payload_rejection_count = deps["code_product_payload_rejection_count"]
            _code_product_source_window_candidate = deps["code_product_source_window_candidate"]
            payload_rejection_count = _code_product_payload_rejection_count(
                validation_rejections,
                code_product_candidate_target,
            )
            successful_read_path_set = {
                _repo_rel_token(path)
                for path in [*read_ok, *verified_read_paths, *list(verified_read_path_set)]
                if _repo_rel_token(path)
            }
            code_contract = contract.get("code_product_contract") if isinstance(contract.get("code_product_contract"), dict) else {}
            code_contract["payload_rejection_count"] = payload_rejection_count
            code_contract["route_shift_after_payload_rejection"] = bool(payload_rejection_count and code_product_candidate_target)
            contract["code_product_contract"] = code_contract
            final_contract = contract.get("finalization_contract") if isinstance(contract.get("finalization_contract"), dict) else {}
            final_contract["final_allowed"] = False
            final_contract["planner_may_choose_final"] = False
            final_contract["reason"] = final_reason
            contract["finalization_contract"] = final_contract
            contract["planner_may_choose_final"] = False
            build_state_ready_action = _code_product_build_state_propose_action(
                code_product_build_state,
                latest_code_product_violations,
            )
            complete_existing_code_action = next(
                (
                    item for item in (contract.get("candidate_next_actions") or [])
                    if isinstance(item, dict)
                    and item.get("tool") == "repo_propose_code_edit"
                    and _code_product_action_has_complete_payload(item)
                ),
                {},
            )
            if not build_state_ready_action and complete_existing_code_action:
                build_state_ready_action = complete_existing_code_action
            build_state_status = str(code_product_build_state.get("status") or "")
            build_state_target = _repo_rel_token(code_product_build_state.get("target_file") or "")
            build_state_needs_read = bool(
                code_product_build_state
                and not build_state_ready_action
                and (
                    code_product_build_state.get("complete_payload_ready")
                    or code_product_build_state.get("has_more_after") is True
                    or code_product_build_state.get("payload_loaded") is not True
                )
            )
            build_state_progress_handled = False
            if build_state_ready_action:
                build_state_progress_handled = True
                ready_progress = (
                    "Internal code_product_build_state is ready_for_propose. "
                    "Call repo_propose_code_edit with the complete payload from candidate_next_actions."
                    if code_product_build_state else
                    "A complete repo_propose_code_edit candidate is available. "
                    "Call repo_propose_code_edit with that complete payload."
                )
                existing_candidates = [
                    item for item in (contract.get("candidate_next_actions") or [])
                    if not (
                        isinstance(item, dict)
                        and item.get("tool") == "repo_propose_code_edit"
                        and not _code_product_action_has_complete_payload(item)
                    )
                ]
                contract["candidate_next_actions"] = [build_state_ready_action] + existing_candidates[:15]
                contract["required_next_progress"] = ready_progress
            elif build_state_status == "blocked_incomplete":
                build_state_progress_handled = True
                code_contract = contract.get("code_product_contract") if isinstance(contract.get("code_product_contract"), dict) else {}
                code_contract["build_state_block_allows_typed_block"] = True
                code_contract["build_state_blocker"] = (
                    code_product_build_state.get("blocker")
                    or (code_product_build_state.get("state") or {}).get("blocker")
                )
                contract["code_product_contract"] = code_contract
                contract["candidate_next_actions"] = []
                contract["required_next_progress"] = (
                    "Internal code_product_build_state is blocked_incomplete. "
                    "Return action=block with final_answer starting with code_product_build_state_blocked_incomplete "
                    "and cite the blocker; do not loop on repo_read or incomplete repo_propose_code_edit."
                )
            elif build_state_needs_read:
                build_state_progress_handled = True
                read_state_action = _code_product_build_state_read_action(
                    code_product_build_state,
                    build_state_target or code_product_candidate_target,
                )
                existing_candidates = [
                    item for item in (contract.get("candidate_next_actions") or [])
                    if not (
                        isinstance(item, dict)
                        and item.get("tool") == "repo_propose_code_edit"
                        and not _code_product_action_has_complete_payload(item)
                    )
                ]
                contract["candidate_next_actions"] = [read_state_action] + existing_candidates[:15]
                contract["required_next_progress"] = (
                    "Read the internal code_product_build_state SQLite window before deciding whether "
                    "repo_propose_code_edit has a complete payload."
                )
            elif payload_rejection_count and code_product_candidate_target:
                build_state_progress_handled = True
                route_candidate = _code_product_source_window_candidate(
                    code_product_candidate_target,
                    line_count=code_product_candidate_line_count,
                    history=history,
                )
                existing_candidates = [
                    item for item in (contract.get("candidate_next_actions") or [])
                    if not (
                        isinstance(item, dict)
                        and item.get("tool") == "repo_propose_code_edit"
                        and not _code_product_action_has_complete_payload(item)
                    )
                    and not (
                        isinstance(item, dict)
                        and item.get("tool") == "planner_scratchpad_write"
                        and (item.get("arguments") or {}).get("kind") == CODE_PRODUCT_BUILD_STATE_KIND
                        and not str((item.get("arguments") or {}).get("text") or (item.get("arguments") or {}).get("content") or "").strip()
                    )
                ]
                if route_candidate:
                    contract["candidate_next_actions"] = [route_candidate] + existing_candidates[:15]
                    contract["required_next_progress"] = (
                        "Route shift required after invalid repo_propose_code_edit payload. Change decision now: "
                        "read a different concrete source window from the target via candidate_next_actions[0], then call "
                        "repo_propose_code_edit only with complete unified_diff or complete old_text/new_text. "
                        "Do not repeat the rejected incomplete repo_propose_code_edit and do not write an empty "
                        "code_product_build_state."
                    )
                else:
                    contract["candidate_next_actions"] = existing_candidates[:15]
                    contract["required_next_progress"] = (
                        "Route shift required after invalid repo_propose_code_edit payload, but no new source "
                        "window is available for this target. Change decision now: use verified_content_reads / "
                        "required_working_set to call repo_propose_code_edit with a complete unified_diff or "
                        "complete old_text/new_text, write code_product_build_state with real progress only, "
                        "or return a typed block if the diff cannot be built. Do not repeat repo_read."
                    )
            elif build_state_status == "collecting_source" and code_product_build_state.get("payload_loaded") is True:
                build_state_progress_handled = True
                existing_candidates = [
                    item for item in (contract.get("candidate_next_actions") or [])
                    if not (
                        isinstance(item, dict)
                        and item.get("tool") == "repo_propose_code_edit"
                        and not _code_product_action_has_complete_payload(item)
                    )
                    and not (
                        isinstance(item, dict)
                        and item.get("tool") == "repo_read"
                        and (build_state_target or code_product_candidate_target) in {
                            _repo_rel_token(path)
                            for path in _agentic_v2_decision_paths(
                                str(item.get("tool") or ""),
                                item.get("arguments") if isinstance(item.get("arguments"), dict) else {},
                            )
                        }
                    )
                ]
                progress_write_action = _code_product_build_state_write_action(
                    build_state_target or code_product_candidate_target,
                    history,
                )
                contract["candidate_next_actions"] = (
                    ([progress_write_action] if progress_write_action else []) + existing_candidates[:15]
                )
                contract["required_next_progress"] = (
                    "Internal code_product_build_state is collecting_source but not ready and has no remaining "
                    "state window to read. Advance with one real step only: call repo_propose_code_edit with a "
                    "complete unified_diff or complete old_text/new_text, write code_product_build_state with "
                    "new real progress, or return a typed block if the diff cannot be built. Empty "
                    "collecting_source writes are rejected."
                )
            elif code_product_candidate_target and code_product_candidate_target in successful_read_path_set:
                build_state_progress_handled = True
                write_state_action = _code_product_build_state_write_action(code_product_candidate_target, history)
                existing_candidates = [
                    item for item in (contract.get("candidate_next_actions") or [])
                    if not (
                        isinstance(item, dict)
                        and item.get("tool") == "repo_propose_code_edit"
                        and not _code_product_action_has_complete_payload(item)
                    )
                    and not (
                        isinstance(item, dict)
                        and item.get("tool") == "repo_read"
                        and code_product_candidate_target in {
                            _repo_rel_token(path)
                            for path in _agentic_v2_decision_paths(
                                str(item.get("tool") or ""),
                                item.get("arguments") if isinstance(item.get("arguments"), dict) else {},
                            )
                        }
                    )
                ]
                contract["candidate_next_actions"] = (
                    ([write_state_action] if write_state_action else []) + existing_candidates[:15]
                )
                contract["required_next_progress"] = (
                    "Target is already read and no ready code product exists. Persist an internal "
                    "code_product_build_state with real progress only; do not repeat repo_read "
                    "for that target and do not call repo_propose_code_edit until payload is complete. "
                    "Empty collecting_source writes are rejected."
                )
            if not build_state_progress_handled and payload_rejection_count and code_product_candidate_target:
                route_candidate = _code_product_source_window_candidate(
                    code_product_candidate_target,
                    line_count=code_product_candidate_line_count,
                    history=history,
                )
                route_target_has_truncated_read = any(
                    _repo_rel_token(row.get("path") or "") == code_product_candidate_target
                    and row.get("truncated") is True
                    for row in verified_read_rows
                    if isinstance(row, dict)
                )
                existing_candidates = [
                    item for item in (contract.get("candidate_next_actions") or [])
                    if not (
                        isinstance(item, dict)
                        and item.get("tool") == "repo_propose_code_edit"
                        and not _code_product_action_has_complete_payload(item)
                    )
                    and not (
                        isinstance(item, dict)
                        and item.get("tool") == "repo_read"
                        and code_product_candidate_target in {
                            _repo_rel_token(path)
                            for path in _agentic_v2_decision_paths(
                                str(item.get("tool") or ""),
                                item.get("arguments") if isinstance(item.get("arguments"), dict) else {},
                            )
                        }
                    )
                ]
                if code_product_candidate_target in successful_read_path_set and not route_target_has_truncated_read:
                    code_contract["route_shift_target_already_read"] = True
                    code_contract["route_shift_blocker"] = (
                        "code_product_route_shift_target_already_read_but_no_valid_candidate"
                    )
                    code_contract["forbidden_repeated_repo_read_target"] = code_product_candidate_target
                    contract["code_product_contract"] = code_contract
                    contract["candidate_next_actions"] = existing_candidates[:15]
                    contract["forbidden_next_actions"] = [
                        {
                            "action": "tool",
                            "tool": "repo_read",
                            "arguments": route_candidate.get("arguments"),
                            "reason": (
                                "The code-product route-shift target is already in "
                                "successful_repo_read_paths; repeating this read loops."
                            ),
                        }
                    ]
                    contract["required_next_progress"] = (
                        "Route shift required after invalid repo_propose_code_edit payload, but "
                        f"{code_product_candidate_target} is already read. Do not call repo_read for "
                        "that target again. Use required_working_set.repo_reads / verified_content_reads "
                        "for that target and call repo_propose_code_edit only with a complete inline "
                        "unified_diff or complete structured_operations. If a complete code product "
                        "cannot be produced from the available source evidence, return action=block with "
                        "final_answer starting with "
                        "code_product_route_shift_target_already_read_but_no_valid_candidate."
                    )
                elif route_candidate:
                    contract["candidate_next_actions"] = [route_candidate] + existing_candidates[:15]
                    contract["required_next_progress"] = (
                        "Route shift required after invalid repo_propose_code_edit payload. "
                        f"Do not repeat the same repo_propose_code_edit arguments for {code_product_candidate_target}. "
                        "Next action must inspect a concrete source window of that target with repo_read, then produce "
                        "repo_propose_code_edit only when the unified_diff or structured_operations payload is complete inline."
                    )
                else:
                    contract["candidate_next_actions"] = existing_candidates[:15]
                    contract["required_next_progress"] = (
                        "Route shift required after invalid repo_propose_code_edit payload, but no unread source "
                        "window remains for the target. Do not call repo_read for that target again. Use the "
                        "existing source evidence to produce a complete inline repo_propose_code_edit payload, "
                        "write code_product_build_state with real progress, or return a typed block."
                    )
            elif not build_state_progress_handled and code_product_candidate_target:
                contract["required_next_progress"] = (
                    "Use required_working_set.repo_reads for the previously read target "
                    f"{code_product_candidate_target}; then call repo_propose_code_edit only with a complete "
                    "unified_diff or complete structured_operations inline. "
                    "Do not final with prose-only output."
                )
            elif not build_state_progress_handled:
                contract["required_next_progress"] = (
                    "read the target with repo_read, then call repo_propose_code_edit with a complete inline code product. "
                    "Do not final with prose-only output."
                )
        elif post_write_validation_required and post_write_validation_failed:
            contract["candidate_next_actions"] = post_write_validation_candidates
            contract["required_next_progress"] = (
                "Post-write validation failed after repo_apply_patch/repo_write_file. "
                "Do not final. Inspect the failed validation evidence and modified files from "
                "post_write_validation_contract.modified_files, then call repo_apply_patch with verified current "
                "old_text to fix and re-run validation, or return action=block with a concrete blocker."
            )
        elif post_write_validation_required and not post_write_validation_done:
            contract["candidate_next_actions"] = post_write_validation_candidates
            contract["required_next_progress"] = (
                "Post-write validation is required before final. Call repo_validate with "
                "post_write_validation_contract.modified_files, or another deterministic validation tool from "
                "post_write_validation_contract.accepted_validation_tools. Do not produce final until one "
                "covering validation succeeds."
            )
        elif goal_requests_apply_value and not apply_patch_done:
            if not apply_target_files:
                contract["candidate_next_actions"] = []
                contract["required_next_progress"] = (
                    "Apply/write goal has no resolved concrete existing target file. Return action=block with "
                    "final_answer starting with apply_write_target_not_resolved; do not call repo_tree, "
                    "repo_list_files, repo_search, or repo_semantic_search."
                )
            elif apply_unread_target_files:
                contract["required_next_progress"] = (
                    "Apply/write goal is in target acquisition mode. Call repo_read only for unread apply target "
                    "paths from apply_write_contract.unread_target_files; do not call repo_tree, repo_list_files, "
                    "repo_search, repo_semantic_search, or unrelated repo_read."
                )
            else:
                contract["required_next_progress"] = (
                    "Apply/write goal target files are already read. Call repo_apply_patch with old_text that is an "
                    "exact substring of required_working_set.repo_reads for apply_write_contract.target_files. "
                    "If more exact text is needed, call repo_read only for apply_write_contract.target_files. "
                    "Do not call repo_tree, repo_list_files, repo_search, repo_semantic_search, or unrelated repo_read; "
                    "return a typed block only if a valid patch cannot be built from the verified target reads."
                )
        elif explicit_request_target_pending:
            contract["required_next_progress"] = (
                "Structured explicit_request_context target is pending. Planner must call "
                f"{explicit_request_tool} with target_arguments from explicit_request_context, or return a typed "
                "block/unavailable result if that tool cannot be run. Do not produce final before this target is covered."
            )
        elif final_allowed:
            contract["required_next_progress"] = (
                "Quality gate is satisfied. Planner must produce action=final using operational_notes.read_notes, "
                "workflow/problems/core evidence, cited concrete paths, and explicit limits. Do not call repo_tree/list/read again "
                "unless a brand-new evidence gap is named."
            )
        elif candidates:
            contract["required_next_progress"] = (
                "candidate_next_actions contains admissible examples, not a controller script. "
                "Planner must choose the next evidence-bound tool or final; do not repeat rejected decisions. "
                "Controller validates only; no hidden fallback final."
            )
        else:
            contract["required_next_progress"] = (
                "Use prior evidence. If enough, final with concrete cited paths; otherwise choose a new evidence-bound tool."
            )
        proofed_candidates: list[dict[str, Any]] = []
        for action in contract.get("candidate_next_actions") or []:
            if not isinstance(action, dict):
                continue
            args = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
            action_paths = [
                _repo_rel_token(path)
                for path in _agentic_v2_decision_paths(str(action.get("tool") or ""), args)
                if _repo_rel_token(path)
            ]
            path_exists = None
            path_readable = None
            under_scope = None
            validator_admissible = None
            if action_paths:
                path_exists = all(_path_exists_repo_relative(path) for path in action_paths)
                path_readable = all(_repo_readable_evidence_file(path) for path in action_paths)
                under_scope = (
                    all(_path_under_scope(path, target_scope) for path in action_paths)
                    if target_scope
                    else True
                )
                validator_admissible = (
                    all(path in validator_admissible_read_paths for path in action_paths)
                    if action.get("tool") == "repo_read"
                    else None
                )
            proofed_candidates.append(
                attach_action_proof(
                    action,
                    source="evidence_contract_candidate_next_actions",
                    path_exists=path_exists,
                    path_readable=path_readable,
                    under_scope=under_scope,
                    validator_admissible=validator_admissible,
                )
            )
        candidate_gate = gate_candidate_actions(proofed_candidates)
        contract["candidate_next_actions"] = candidate_gate["candidate_next_actions"]
        contract["rejected_candidate_actions"] = candidate_gate["rejected_candidate_actions"]
        contract["micro_batch_contract"] = _micro_batch_contract_from_candidates(
            contract["candidate_next_actions"]
        )
        contract["evidence_coverage"] = score_evidence_coverage(contract)
        progress_text = str(contract.get("required_next_progress") or "").strip()
        if progress_text:
            contract["required_next_progress_model"] = required_next_progress_from_text(
                progress_text,
                metadata={
                    "final_allowed": bool(contract.get("planner_may_choose_final")),
                    "candidate_next_actions_count": len(contract.get("candidate_next_actions") or []),
                    "forbidden_next_actions_count": len(contract.get("forbidden_next_actions") or []),
                    "goal_requests_code_product": bool(contract.get("goal_requests_code_product")),
                    "goal_requests_apply": bool(contract.get("goal_requests_apply")),
                },
            ).to_contract()
        contract = _apply_turn_surface_policy(contract)
        return contract


def planner_evidence_contract(
    goal: str,
    history: list[dict[str, Any]],
    intrinsic_context: dict[str, Any] | None = None,
    *,
    deps: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Compatibility entrypoint for ``EvidenceBuilder``."""
    return EvidenceBuilder(_deps=deps, _config=config).build(
        goal,
        history,
        intrinsic_context,
    )
