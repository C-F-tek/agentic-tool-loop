"""Broker-side inline evidence materializer for OpenWebUI payloads.

The materializer is the 3572 owner for public evidence fields. It does not
load local files and does not duplicate payload content inside the index; it
selects concrete inline artifacts already present in ``tool_context_for_30b``
and exposes deterministic pointers for the 3571 bridge/OpenWebUI surface.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from ..shared.payload_metadata import sha256_text
from .payload_index_resolver import resolve_payload_index


MATERIALIZATION_SCHEMA = "public_evidence_materialization.v1"
PRIMARY_SCHEMA = "openwebui.primary_payload_for_30b.v1"
PRIORITY_SCHEMA = "openwebui.priority_evidence_for_30b.v1"
INDEX_KIND = "openwebui_payload_index.v1"
_ITEM_INDEX_RE = re.compile(r"priority_evidence_for_30b\.items\[(?P<index>\d+)\]")


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            cleaned = _clean(item)
            if cleaned not in (None, "", [], {}):
                out[str(key)] = cleaned
        return out
    if isinstance(value, list):
        out = []
        for item in value:
            cleaned = _clean(item)
            if cleaned not in (None, "", [], {}):
                out.append(cleaned)
        return out
    return value


def _priority_item_from_artifact(row: dict[str, Any], *, artifact_index: int) -> dict[str, Any]:
    artifact = _as_dict(row.get("artifact"))
    kind = str(artifact.get("kind") or "")
    tool = row.get("tool")
    step = row.get("producer_step")
    substep = row.get("substep")

    if kind == "repo_read":
        content = artifact.get("content")
        if not isinstance(content, str) or not content:
            return {}
        if artifact.get("truncated") is True or artifact.get("preview_only") is True:
            return {}
        return _clean({
            "kind": "repo_file_full_content",
            "tool": tool,
            "step": step,
            "substep": substep,
            "ok": row.get("ok", True),
            "path": artifact.get("repo_path"),
            "payload_is_complete": True,
            "chars": len(content),
            "line_count": artifact.get("line_count"),
            "sha256": sha256_text(content),
            "artifact_index": artifact_index,
            "content_not_duplicated_here": True,
            "primary_payload_location": (
                f"tool_context_for_30b.artifacts[{artifact_index}].artifact.content"
            ),
        })

    if kind == "code_edit_proposal":
        edit_kind = artifact.get("edit_kind")
        item: dict[str, Any] = {
            "kind": "code_edit_proposal",
            "tool": tool,
            "step": step,
            "substep": substep,
            "ok": row.get("ok", True),
            "target_file": artifact.get("target_file"),
            "edit_kind": edit_kind,
            "payload_is_complete": False,
            "source_writes_performed": artifact.get("source_writes_performed"),
            "patch_application_performed": artifact.get("patch_application_performed"),
            "manual_review_required": artifact.get("manual_review_required"),
            "rationale": artifact.get("rationale"),
            "validation_commands": artifact.get("validation_commands"),
            "warnings": artifact.get("warnings"),
            "errors": artifact.get("errors"),
            "target_metadata": artifact.get("target_metadata"),
            "ast_evidence": artifact.get("ast_evidence"),
            "artifact_index": artifact_index,
            "content_not_duplicated_here": True,
        }
        if edit_kind == "unified_diff":
            diff = artifact.get("unified_diff")
            item["payload_is_complete"] = isinstance(diff, str) and bool(diff.strip())
            if isinstance(diff, str):
                item["chars"] = len(diff)
                item["sha256"] = sha256_text(diff)
                item["primary_payload_location"] = (
                    f"tool_context_for_30b.artifacts[{artifact_index}].artifact.unified_diff"
                )
        elif edit_kind == "structured_edit":
            operations = artifact.get("structured_operations")
            item["payload_is_complete"] = bool(operations)
            if operations not in (None, "", [], {}):
                operations_text = json.dumps(
                    operations,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
                item["chars"] = len(operations_text)
                item["sha256"] = sha256_text(operations_text)
                item["structured_operations_count"] = (
                    len(operations) if isinstance(operations, list) else None
                )
                item["primary_payload_location"] = (
                    f"tool_context_for_30b.artifacts[{artifact_index}].artifact.structured_operations"
                )
        elif edit_kind == "no_op":
            rationale = artifact.get("rationale")
            item["payload_is_complete"] = isinstance(rationale, str) and bool(rationale.strip())
        return _clean(item)

    return {}


def _generic_tool_result_priority_item(row: dict[str, Any], *, artifact_index: int) -> dict[str, Any]:
    artifact = _as_dict(row.get("artifact"))
    if not artifact:
        return {}
    kind = str(artifact.get("kind") or "")
    if kind in {"repo_read", "code_edit_proposal"}:
        return {}
    tool = str(row.get("tool") or artifact.get("tool") or "")
    if not tool:
        return {}
    accepted = not (row.get("ok") is False or artifact.get("ok") is False)
    return _clean({
        "kind": "tool_result_inline",
        "tool": tool,
        "step": row.get("producer_step"),
        "substep": row.get("substep"),
        "ok": row.get("ok", True),
        "payload_is_complete": accepted,
        "validator_accepted": accepted,
        "payload_type": kind or "tool_result",
        "artifact_index": artifact_index,
        "result_keys": sorted(str(key) for key in artifact.keys())[:40],
        "summary": artifact.get("summary") or row.get("summary"),
        "error": artifact.get("error"),
        "error_type": artifact.get("error_type"),
        "returncode": artifact.get("returncode"),
    })


def _analysis_priority_item(tool_context: dict[str, Any], planner_text: str) -> dict[str, Any]:
    evidence_files: list[dict[str, Any]] = []
    for row in _as_list(tool_context.get("artifacts")):
        row = _as_dict(row)
        artifact = _as_dict(row.get("artifact"))
        kind = str(artifact.get("kind") or "")
        path = artifact.get("repo_path")
        if not path and isinstance(row.get("arguments"), dict):
            path = row["arguments"].get("path")
        if kind not in {"repo_read", "repo_tree", "repo_list_files"} and not path:
            continue
        evidence_files.append(_clean({
            "step": row.get("producer_step"),
            "substep": row.get("substep"),
            "tool": row.get("tool"),
            "kind": kind or "tool_evidence",
            "path": path,
            "truncated": artifact.get("truncated"),
            "preview_only": artifact.get("preview_only"),
            "reason": "successful_tool_evidence_available_in_tool_context_for_30b",
        }))
    if not planner_text and not evidence_files:
        return {}
    return _clean({
        "kind": "repo_analysis_summary",
        "payload_is_complete": bool(planner_text),
        "guide_chars": len(planner_text) if planner_text else None,
        "guide_sha256": sha256_text(planner_text) if planner_text else None,
        "primary_payload_location": "evidence_guide_for_30b",
        "summary_not_duplicated_here": True,
        "content_not_duplicated_here": True,
        "evidence_files": evidence_files[:80],
    })


def _partial_priority_items(tool_context: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in _as_list(tool_context.get("partial_products_for_30b")):
        item = _as_dict(row)
        if not item:
            continue
        item = dict(item)
        item.setdefault("payload_is_complete", False)
        item.setdefault("validator_accepted", False)
        out.append(_clean(item))
    best = _as_dict(tool_context.get("best_partial_product_for_30b"))
    if best:
        best = dict(best)
        best.setdefault("payload_is_complete", False)
        best.setdefault("validator_accepted", False)
        key = json.dumps(best, ensure_ascii=False, sort_keys=True, default=str)
        existing = {
            json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
            for item in out
        }
        if key not in existing:
            out.insert(0, _clean(best))
    return out


def _coverage_priority_item(tool_context: dict[str, Any]) -> dict[str, Any]:
    coverage = _as_dict(tool_context.get("coverage_status"))
    if not coverage:
        contract = _as_dict(
            tool_context.get("evidence_contract_at_terminal")
            or tool_context.get("evidence_contract_at_finish")
        )
        coverage = _as_dict(contract.get("minimum_read_coverage"))
        if not coverage and contract:
            coverage = {
                "coverage_satisfied": contract.get("coverage_satisfied"),
                "missing_owner_paths": contract.get("missing_owner_paths"),
                "covered_owner_paths": contract.get("covered_owner_paths"),
            }
    if not coverage or coverage.get("coverage_satisfied") is not False:
        return {}
    return _clean({
        "kind": "coverage_gap",
        "payload_type": "coverage_status",
        "payload_is_complete": False,
        "validator_accepted": False,
        "coverage_satisfied": False,
        "required": coverage.get("required"),
        "target_kind": coverage.get("target_kind"),
        "required_count": coverage.get("required_count"),
        "covered_count": coverage.get("covered_count"),
        "missing_owner_paths": coverage.get("missing_owner_paths"),
        "covered_owner_paths": coverage.get("covered_owner_paths"),
        "candidate_owner_paths": coverage.get("candidate_owner_paths"),
        "minimum_read_coverage": coverage.get("minimum_read_coverage") or coverage,
        "role": (
            "gap di copertura: non trattare questo payload come completato; "
            "serve una lettura/search selettiva o un block tipizzato"
        ),
    })


def _context_location_resolution(tool_context: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    kind = str(item.get("kind") or "")
    target_file = str(item.get("target_file") or "")
    path = str(item.get("path") or "")
    artifacts = _as_list(tool_context.get("artifacts"))
    if not artifacts:
        return {
            "location": "tool_context_for_30b.artifacts[*].artifact",
            "location_resolved": False,
            "location_resolution_reason": "tool_context_artifacts_empty",
            "artifact_index": item.get("artifact_index"),
        }
    for index, row in enumerate(artifacts):
        artifact = _as_dict(_as_dict(row).get("artifact"))
        artifact_kind = str(artifact.get("kind") or "")
        if kind == "code_edit_proposal" and artifact_kind == "code_edit_proposal":
            if target_file and str(artifact.get("target_file") or "") != target_file:
                continue
            edit_kind = str(artifact.get("edit_kind") or "")
            if edit_kind == "unified_diff":
                location = f"tool_context_for_30b.artifacts[{index}].artifact.unified_diff"
            elif edit_kind == "structured_edit":
                location = f"tool_context_for_30b.artifacts[{index}].artifact.structured_operations"
            else:
                location = f"tool_context_for_30b.artifacts[{index}].artifact"
            return {
                "location": location,
                "location_resolved": True,
                "location_resolution_reason": "matched_code_edit_proposal_artifact",
                "artifact_index": index,
            }
        if kind == "repo_file_full_content" and artifact_kind == "repo_read":
            if path and str(artifact.get("repo_path") or "") != path:
                continue
            return {
                "location": f"tool_context_for_30b.artifacts[{index}].artifact.content",
                "location_resolved": True,
                "location_resolution_reason": "matched_repo_read_artifact",
                "artifact_index": index,
            }
    return {
        "location": "tool_context_for_30b.artifacts[*].artifact",
        "location_resolved": False,
        "location_resolution_reason": "matching_artifact_not_found",
        "artifact_index": item.get("artifact_index"),
        "artifact_count": len(artifacts),
    }


def _context_location(tool_context: dict[str, Any], item: dict[str, Any]) -> str:
    location = _context_location_resolution(tool_context, item).get("location")
    return str(location or "tool_context_for_30b.artifacts[*].artifact")


def _payload_index_row(item: dict[str, Any], index: int, tool_context: dict[str, Any]) -> dict[str, Any]:
    kind = str(item.get("kind") or "")
    base = f"priority_evidence_for_30b.items[{index}]"
    if kind == "repo_file_full_content":
        context_resolution = _context_location_resolution(tool_context, item)
        context_location = str(context_resolution.get("location") or "tool_context_for_30b.artifacts[*].artifact")
        return _clean({
            "kind": "repo_file_full_content",
            "payload_type": "file_content",
            "path": item.get("path"),
            "step": item.get("step"),
            "substep": item.get("substep"),
            "payload_is_complete": item.get("payload_is_complete"),
            "primary_location": context_location,
            "full_context_location": context_location,
            "metadata_location": base,
            "artifact_index": context_resolution.get("artifact_index"),
            "location_resolved": context_resolution.get("location_resolved"),
            "location_resolution_reason": context_resolution.get("location_resolution_reason"),
            "sha256": item.get("sha256"),
            "chars": item.get("chars"),
            "line_count": item.get("line_count"),
            "content_not_duplicated_here": True,
        })
    if kind == "code_edit_proposal":
        edit_kind = str(item.get("edit_kind") or "")
        if edit_kind == "unified_diff":
            payload_type = "unified_diff"
        elif edit_kind == "structured_edit":
            payload_type = "structured_operations"
        else:
            payload_type = "code_edit_proposal"
        context_resolution = _context_location_resolution(tool_context, item)
        context_location = str(context_resolution.get("location") or "tool_context_for_30b.artifacts[*].artifact")
        return _clean({
            "kind": "code_edit_proposal",
            "payload_type": payload_type,
            "target_file": item.get("target_file"),
            "step": item.get("step"),
            "substep": item.get("substep"),
            "edit_kind": edit_kind,
            "payload_is_complete": item.get("payload_is_complete"),
            "primary_location": context_location,
            "full_context_location": context_location,
            "metadata_location": base,
            "artifact_index": context_resolution.get("artifact_index"),
            "location_resolved": context_resolution.get("location_resolved"),
            "location_resolution_reason": context_resolution.get("location_resolution_reason"),
            "sha256": item.get("sha256"),
            "chars": item.get("chars"),
            "content_not_duplicated_here": True,
        })
    if kind in {
        "partial_code_product_candidate",
        "partial_code_product_build_state",
        "action_plan_candidate",
        "repair_candidate_text",
    }:
        if item.get("unified_diff"):
            field = "unified_diff"
            payload_type = "partial_unified_diff"
        elif item.get("structured_operations"):
            field = "structured_operations"
            payload_type = "partial_structured_operations"
        elif item.get("old_text") is not None or item.get("new_text") is not None:
            field = "old_text_new_text"
            payload_type = "partial_old_text_new_text"
        elif item.get("state_text"):
            field = "state_text"
            payload_type = "partial_code_product_state"
        elif item.get("rationale"):
            field = "rationale"
            payload_type = "partial_rationale"
        elif item.get("violations"):
            field = "violations"
            payload_type = "partial_validation_violations"
        else:
            field = ""
            payload_type = "partial_metadata"
        primary_location: str | dict[str, str] = f"{base}.{field}"
        if field == "old_text_new_text":
            primary_location = {
                "old_text": f"{base}.old_text",
                "new_text": f"{base}.new_text",
            }
        elif not field:
            primary_location = base
        return _clean({
            "kind": kind,
            "payload_type": payload_type,
            "target_file": item.get("target_file"),
            "edit_kind": item.get("edit_kind"),
            "payload_is_complete": item.get("payload_is_complete", False),
            "validator_accepted": item.get("validator_accepted", False),
            "primary_location": primary_location,
            "full_context_location": "priority_evidence_for_30b.items[*]",
            "role": (
                "prodotto parziale/non validato: mostrare all'utente se il job "
                "interno non ha completato; non trattarlo come diff completato"
            ),
        })
    if kind == "tool_result_inline":
        artifact_index = item.get("artifact_index")
        try:
            artifact_index = int(artifact_index)
        except Exception:
            artifact_index = None
        if artifact_index is None or artifact_index < 0:
            primary_location = "tool_context_for_30b.artifacts[*].artifact"
        else:
            primary_location = f"tool_context_for_30b.artifacts[{artifact_index}].artifact"
        return _clean({
            "kind": "tool_result_inline",
            "payload_type": item.get("payload_type") or "tool_result",
            "tool": item.get("tool"),
            "step": item.get("step"),
            "substep": item.get("substep"),
            "payload_is_complete": item.get("payload_is_complete", True),
            "validator_accepted": item.get("validator_accepted", True),
            "primary_location": primary_location,
            "full_context_location": primary_location,
            "role": (
                "risultato concreto: payload inline prodotto dal tool; leggere "
                "l'artifact indicato senza richiamare il tool"
            ),
        })
    if kind == "coverage_gap":
        return _clean({
            "kind": "partial_coverage_gap",
            "payload_type": "coverage_status",
            "payload_is_complete": False,
            "validator_accepted": False,
            "coverage_satisfied": False,
            "primary_location": f"{base}.missing_owner_paths",
            "full_context_location": base,
            "missing_owner_paths": item.get("missing_owner_paths"),
            "covered_owner_paths": item.get("covered_owner_paths"),
            "role": "coverage_satisfied=false: non trasformare in completed",
        })
    return {}


def _code_product_payload_is_complete(artifact: dict[str, Any]) -> bool:
    edit_kind = str(artifact.get("edit_kind") or "")
    if edit_kind == "unified_diff":
        diff = artifact.get("unified_diff")
        return isinstance(diff, str) and bool(diff.strip())
    if edit_kind == "structured_edit":
        operations = artifact.get("structured_operations")
        return operations not in (None, "", [], {})
    if edit_kind == "no_op":
        rationale = artifact.get("rationale")
        return isinstance(rationale, str) and bool(rationale.strip())
    return False


def _code_product_final_allowed(tool_context: dict[str, Any]) -> bool:
    contract = _as_dict(
        tool_context.get("evidence_contract_at_terminal")
        or tool_context.get("evidence_contract_at_finish")
    )
    finalization = _as_dict(contract.get("finalization_contract"))
    if "final_allowed" in finalization:
        return finalization.get("final_allowed") is True
    if "planner_may_choose_final" in contract:
        return contract.get("planner_may_choose_final") is True
    if "final_allowed" in contract:
        return contract.get("final_allowed") is True
    return False


def _artifact_repo_path(artifact: dict[str, Any]) -> str:
    return str(
        artifact.get("repo_path")
        or artifact.get("path")
        or artifact.get("source_path")
        or ""
    ).strip()


def _code_product_gate(priority_evidence: dict[str, Any], tool_context: dict[str, Any]) -> dict[str, Any]:
    priority_items = [_as_dict(item) for item in _as_list(priority_evidence.get("items"))]
    artifacts = [_as_dict(row) for row in _as_list(tool_context.get("artifacts"))]
    code_items = [
        item for item in priority_items
        if str(item.get("kind") or "") in {"code_edit_proposal"}
        or str(item.get("kind") or "").startswith("partial_code_product")
    ]
    proposal_rows = [
        row for row in artifacts
        if str(row.get("tool") or "") == "repo_propose_code_edit"
        or str(_as_dict(row.get("artifact")).get("kind") or "") == "code_edit_proposal"
    ]
    if not code_items and not proposal_rows:
        return {}

    target_file = ""
    edit_kind = "unknown"
    repo_propose_ok = False
    complete_inline = False
    for row in proposal_rows:
        artifact = _as_dict(row.get("artifact"))
        if not target_file:
            target_file = str(artifact.get("target_file") or row.get("target_file") or "")
        if edit_kind == "unknown" and str(artifact.get("edit_kind") or "") in {"unified_diff", "structured_edit", "no_op"}:
            edit_kind = str(artifact.get("edit_kind") or "")
        if row.get("ok") is not False and artifact.get("ok") is not False:
            repo_propose_ok = True
        if _code_product_payload_is_complete(artifact):
            complete_inline = True
    for item in code_items:
        if not target_file:
            target_file = str(item.get("target_file") or "")
        if edit_kind == "unknown" and str(item.get("edit_kind") or "") in {"unified_diff", "structured_edit", "no_op"}:
            edit_kind = str(item.get("edit_kind") or "")
        if item.get("payload_is_complete") is True:
            complete_inline = True

    target_read = False
    if target_file:
        for row in artifacts:
            artifact = _as_dict(row.get("artifact"))
            kind = str(artifact.get("kind") or "")
            if kind not in {"repo_read", "repo_file_full_content"}:
                continue
            if row.get("ok") is False or artifact.get("ok") is False:
                continue
            if _artifact_repo_path(artifact) != target_file:
                continue
            content = artifact.get("content")
            target_read = isinstance(content, str) and bool(content)
            if target_read:
                break

    return _clean({
        "schema": "openwebui_payload_index.code_product_gate.v1",
        "diagnostic_only": True,
        "target_file": target_file,
        "target_read": target_read,
        "repo_propose_code_edit_ok": repo_propose_ok,
        "complete_payload_inline": complete_inline,
        "edit_kind": edit_kind,
        "final_allowed": _code_product_final_allowed(tool_context),
        "source": (
            "Derived from tool_context_for_30b artifacts and priority evidence; "
            "diagnostic only, not a validator or apply/write decision."
        ),
    })


def _iter_location_strings(value: Any):
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_location_strings(item)


def _item_index_from_location(value: Any) -> int | None:
    for location in _iter_location_strings(value):
        match = _ITEM_INDEX_RE.search(location)
        if not match:
            continue
        try:
            return int(match.group("index"))
        except Exception:
            return None
    return None


def _first_location_value(row: dict[str, Any]) -> str:
    for key in ("primary_location", "field", "full_context_location"):
        for location in _iter_location_strings(row.get(key)):
            if location:
                return location
    return ""


def _append_unique(values: list[str], value: str) -> None:
    value = str(value or "").strip()
    if value and value not in values:
        values.append(value)


def _payload_search_order(
    *,
    concrete_results: list[dict[str, Any]],
    partial_results: list[dict[str, Any]],
    descriptive_only: list[dict[str, Any]],
) -> list[str]:
    order: list[str] = []
    _append_unique(order, "evidence_guide_for_30b")
    _append_unique(order, "primary_payload_for_30b.primary_location")
    if concrete_results:
        _append_unique(order, "payload_index_for_30b.concrete_results")
        for row in concrete_results:
            _append_unique(order, _first_location_value(row))
    if partial_results:
        _append_unique(order, "payload_index_for_30b.partial_results")
        for row in partial_results:
            _append_unique(order, _first_location_value(row))
    for row in descriptive_only:
        _append_unique(order, _first_location_value(row))
    if not concrete_results and not partial_results:
        _append_unique(order, "tool_context_for_30b.artifacts[*].artifact")
    return order


def _owner_for_priority_item(item: dict[str, Any], row: dict[str, Any] | None = None) -> tuple[str, str]:
    row = row or {}
    kind = str(item.get("kind") or row.get("kind") or "")
    tool = str(item.get("tool") or row.get("tool") or "")
    if tool == "repo_apply_patch":
        return "application.patch_apply", "apply_patch"
    if kind in {"repo_file_full_content", "repo_analysis_summary"}:
        return "application.evidence", "repo_analysis"
    if kind == "code_edit_proposal" or kind.startswith("partial_code_product"):
        return "application.code_product", "code_product"
    if kind.startswith("partial_"):
        return "application.public_payload", "partial_terminal_payload"
    if kind == "coverage_gap":
        return "application.evidence", "minimum_read_coverage"
    if kind == "tool_result_inline":
        return "application.tool_surface", "tool_result"
    return "application.public_payload", "generic_payload"


def _primary_descriptor_from_row(
    *,
    row: dict[str, Any],
    item: dict[str, Any],
    item_index: int | None,
    section: str,
) -> dict[str, Any]:
    owner, request_type = _owner_for_priority_item(item, row)
    primary_location = row.get("primary_location") or row.get("field")
    payload_kind = row.get("payload_type") or item.get("kind") or row.get("kind")
    return _clean({
        "schema": PRIMARY_SCHEMA,
        "owner": owner,
        "request_type": request_type,
        "payload_kind": payload_kind,
        "kind": item.get("kind") or row.get("kind"),
        "tool": item.get("tool") or row.get("tool"),
        "step": item.get("step") or row.get("step"),
        "substep": item.get("substep") or row.get("substep"),
        "path": item.get("path") or row.get("path"),
        "target_file": item.get("target_file") or row.get("target_file"),
        "item_index": item_index,
        "source_index_section": section,
        "primary_location": primary_location,
        "full_context_location": row.get("full_context_location"),
        "payload_is_complete": row.get("payload_is_complete", item.get("payload_is_complete")),
        "validator_accepted": row.get("validator_accepted", item.get("validator_accepted", True)),
        "read_before_payload_index": True,
        "content_not_duplicated_here": True,
        "reason": (
            "This is the owner-selected first useful inline payload location. "
            "Read the referenced field in this same JSON payload; this descriptor "
            "does not copy the content."
        ),
    })


def _primary_payload_descriptor(
    priority_evidence: dict[str, Any],
    payload_index: dict[str, Any],
) -> dict[str, Any]:
    priority_items = [_as_dict(item) for item in _as_list(priority_evidence.get("items"))]
    for section in ("concrete_results", "partial_results"):
        for row in _as_list(payload_index.get(section)):
            row = _as_dict(row)
            if not row:
                continue
            location = row.get("primary_location") or row.get("field")
            item_index = _item_index_from_location(location)
            if item_index is None:
                item_index = _item_index_from_location(row.get("metadata_location"))
            item = priority_items[item_index] if item_index is not None and 0 <= item_index < len(priority_items) else {}
            if not item:
                item = {
                    "kind": row.get("kind"),
                    "tool": row.get("tool"),
                    "path": row.get("path"),
                    "target_file": row.get("target_file"),
                    "payload_is_complete": row.get("payload_is_complete"),
                    "validator_accepted": row.get("validator_accepted"),
                }
            return _primary_descriptor_from_row(
                row=row,
                item=item,
                item_index=item_index,
                section=section,
            )
    for index, item in enumerate(priority_items):
        if item.get("kind") != "repo_analysis_summary":
            continue
        return _primary_descriptor_from_row(
            row={
                "kind": "repo_analysis_summary",
                "payload_type": "repo_analysis_summary",
                "primary_location": "evidence_guide_for_30b",
                "full_context_location": "evidence_guide_for_30b",
                "payload_is_complete": item.get("payload_is_complete"),
                "validator_accepted": True,
            },
            item=item,
            item_index=index,
            section="descriptive_only",
        )
    return {}


@dataclass(frozen=True)
class PublicEvidenceMaterializer:
    """Build the complete 30B evidence surface from broker-side inline context."""

    owner: str = "3572_broker"

    def materialize(
        self,
        *,
        tool_context: dict[str, Any] | str | None,
        evidence_guide: str = "",
        completed: bool = False,
        internal_job_status: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = _as_dict(tool_context)
        coverage_missing = bool(_coverage_priority_item(context))
        effective_completed = bool(completed and not coverage_missing)
        priority = self._priority_evidence(context, evidence_guide, completed=effective_completed)
        payload_index = self._payload_index(priority, context, completed=effective_completed)
        if isinstance(internal_job_status, dict) and internal_job_status:
            payload_index["internal_job_status"] = _clean(internal_job_status)
        primary_payload = _primary_payload_descriptor(priority, payload_index)
        report = self._materialization_report(
            tool_context=context,
            priority_evidence=priority,
            payload_index=payload_index,
            evidence_guide=evidence_guide,
        )
        return {
            "primary_payload_for_30b": primary_payload,
            "payload_index_for_30b": payload_index,
            "priority_evidence_for_30b": priority,
            "materialization_report": report,
        }

    def _priority_evidence(
        self,
        tool_context: dict[str, Any],
        evidence_guide: str,
        *,
        completed: bool,
    ) -> dict[str, Any]:
        artifact_rows = [_as_dict(row) for row in _as_list(tool_context.get("artifacts"))]
        artifact_items = [
            item
            for item in (
                _priority_item_from_artifact(row, artifact_index=index)
                for index, row in enumerate(artifact_rows)
            )
            if item
        ]
        generic_artifact_items = [
            item
            for item in (
                _generic_tool_result_priority_item(row, artifact_index=index)
                for index, row in enumerate(artifact_rows)
            )
            if item
        ]
        partial_items = _partial_priority_items(tool_context)
        coverage_item = _coverage_priority_item(tool_context)
        analysis_item = _analysis_priority_item(tool_context, evidence_guide)
        items: list[dict[str, Any]] = []
        if coverage_item:
            items.append(coverage_item)
        if completed:
            items.extend(artifact_items)
            items.extend(generic_artifact_items)
            items.extend(partial_items)
        else:
            items.extend(partial_items)
            items.extend(artifact_items)
            items.extend(generic_artifact_items)
        if analysis_item:
            items.append(analysis_item)
        return _clean({
            "schema": PRIORITY_SCHEMA,
            "purpose": (
                "High-priority evidence materialized by the 3572 broker. "
                "Concrete payloads are pointer-first: this section carries "
                "metadata/hash/location for successful tool artifacts; partial "
                "products are marked validator_accepted=false."
            ),
            "navigation_hint": (
                "Read primary_payload_for_30b.primary_location and "
                "payload_index_for_30b.concrete_results for concrete payload "
                "locations; priority_evidence_for_30b.items is metadata."
            ),
            "items": items,
            "limits": tool_context.get("limits"),
        })

    def _payload_index(
        self,
        priority_evidence: dict[str, Any],
        tool_context: dict[str, Any],
        *,
        completed: bool,
    ) -> dict[str, Any]:
        concrete_results: list[dict[str, Any]] = []
        partial_results: list[dict[str, Any]] = []
        descriptive_only: list[dict[str, Any]] = []
        suggestions_only: list[dict[str, Any]] = []
        for index, item in enumerate(_as_list(priority_evidence.get("items"))):
            item = _as_dict(item)
            location = _payload_index_row(item, index, tool_context)
            if location:
                if str(location.get("kind") or "").startswith("partial_") or location.get("validator_accepted") is False:
                    partial_results.append(location)
                else:
                    concrete_results.append(location)
                if item.get("kind") == "code_edit_proposal":
                    base = f"priority_evidence_for_30b.items[{index}]"
                    suggestions_only.extend([
                        {
                            "field": f"{base}.manual_review_required",
                        },
                        {
                            "field": f"{base}.validation_commands",
                        },
                    ])
                continue
            if item.get("kind") == "repo_analysis_summary":
                descriptive_only.append({
                    "field": "evidence_guide_for_30b",
                    "full_context_location": "evidence_guide_for_30b",
                })
        descriptive_rows = descriptive_only
        has_indexed_payload = bool(concrete_results or partial_results or descriptive_only)
        code_product_gate = _code_product_gate(priority_evidence, tool_context)
        return _clean({
            "index_kind": INDEX_KIND,
            "job_completed": bool(completed),
            "same_request_rule": (
                "Rispondi usando i campi indicizzati qui quando esistono "
                "concrete_results, partial_results o descriptive_only. Non "
                "richiamare vulkan_helper per la stessa richiesta solo perche' "
                "job_completed=false; quello e' uno stato del job interno, non "
                "assenza di payload."
                if has_indexed_payload else
                "Nessun payload indicizzato disponibile; solo in questo caso "
                "una nuova chiamata puo' essere necessaria per la stessa richiesta."
            ),
            "concrete_results": concrete_results,
            "partial_results": partial_results,
            "descriptive_only": descriptive_rows,
            "code_product_gate": code_product_gate,
            "suggestions_or_review_metadata_only": suggestions_only + [
                {
                    "field": "priority_evidence_for_30b.limits",
                },
                {
                    "field": "openwebui_usage",
                },
            ],
            "search_order": _payload_search_order(
                concrete_results=concrete_results,
                partial_results=partial_results,
                descriptive_only=descriptive_rows,
            ),
        })

    def _materialization_report(
        self,
        *,
        tool_context: dict[str, Any],
        priority_evidence: dict[str, Any],
        payload_index: dict[str, Any],
        evidence_guide: str,
    ) -> dict[str, Any]:
        payload = {
            "evidence_guide_for_30b": evidence_guide,
            "payload_index_for_30b": payload_index,
            "priority_evidence_for_30b": priority_evidence,
            "tool_context_for_30b": tool_context,
        }
        resolution = resolve_payload_index(payload)
        artifacts = _as_list(tool_context.get("artifacts"))
        priority_items = _as_list(priority_evidence.get("items"))
        concrete_items = [
            item for item in priority_items
            if _as_dict(item).get("kind") in {"repo_file_full_content", "code_edit_proposal", "tool_result_inline"}
            and _as_dict(item).get("payload_is_complete") is not False
        ]
        ok = bool(resolution.get("ok")) and bool(tool_context)
        if artifacts:
            ok = ok and bool(concrete_items or payload_index.get("partial_results"))
        return {
            "schema": MATERIALIZATION_SCHEMA,
            "owner": self.owner,
            "target_owner": "3572_broker",
            "ok": ok,
            "diagnostic_only": True,
            "inline_json_required": True,
            "objects_are_not_transport": True,
            "bridge_role": "transport_wrapper_and_final_lint_only",
            "tool_context": {
                "json_object": bool(tool_context),
                "artifact_rows": len(artifacts),
                "public_scope": "tool_context_for_30b.artifacts[*].artifact",
                "not_full_job_dump": bool(tool_context.get("not_a_summary")),
            },
            "priority_evidence": {
                "items": len(priority_items),
                "concrete_items": len(concrete_items),
                "has_evidence_guide": bool(str(evidence_guide or "").strip()),
            },
            "artifacts": {
                "refs_seen": len(artifacts),
                "refs_resolved": len(artifacts),
                "materialized": len(concrete_items),
                "unresolved_refs": [],
            },
            "payload_index": {
                "ok": bool(resolution.get("ok")),
                "resolved_count": len(resolution.get("resolved") or []),
                "unresolved": resolution.get("unresolved") or [],
                "empty_targets": resolution.get("empty_targets") or [],
            },
            "local_paths": {
                "omitted_from_public_payload": True,
                "operator_diagnostics_only": True,
            },
        }


def materialize_public_evidence(
    *,
    tool_context: dict[str, Any] | str | None,
    evidence_guide: str = "",
    completed: bool = False,
    internal_job_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compatibility function for the broker-owned evidence materializer."""

    return PublicEvidenceMaterializer().materialize(
        tool_context=tool_context,
        evidence_guide=evidence_guide,
        completed=completed,
        internal_job_status=internal_job_status,
    )
