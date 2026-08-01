"""Public code-product and partial-pfrom services.aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

roduct text helpers."""

from __future__ import annotations

import json
from typing import Any

from ...tool_contract import normalize_tool_name
from .state import code_product_build_state_parse
from ..shared.history_queries import history_tool_result
from ..shared.path_tokens import repo_rel_token


def latest_code_product_payload(history: list[dict[str, Any]]) -> dict[str, Any]:
    for item in reversed(history if isinstance(history, list) else []):
        if not isinstance(item, dict):
            continue
        result = history_tool_result(item)
        if (
            isinstance(result, dict)
            and result.get("tool") == "repo_propose_code_edit"
            and result.get("ok") is True
            and result.get("kind") == "code_edit_proposal"
        ):
            return result
    return {}


def code_product_answer_text(result: dict[str, Any] | None, limit: int = 180000) -> str:
    result = result if isinstance(result, dict) else {}
    history = result.get("history") if isinstance(result.get("history"), list) else []
    proposal = latest_code_product_payload(history)
    if not proposal:
        return ""
    target = str(proposal.get("target_file") or "")
    edit_kind = str(proposal.get("edit_kind") or "")
    lines = [
        "Code edit proposal generated.",
        f"- target_file: {target}",
        f"- edit_kind: {edit_kind}",
        f"- source_writes_performed: {str(proposal.get('source_writes_performed')).lower()}",
        f"- patch_application_performed: {str(proposal.get('patch_application_performed')).lower()}",
        f"- manual_review_required: {str(proposal.get('manual_review_required')).lower()}",
    ]
    rationale = str(proposal.get("rationale") or "").strip()
    if rationale:
        lines.append(f"- rationale: {rationale}")
    validation_commands = proposal.get("validation_commands")
    if isinstance(validation_commands, list) and validation_commands:
        lines.append("- validation_commands:")
        for command in validation_commands:
            lines.append(f"  - {command}")
    if edit_kind == "unified_diff":
        diff_text = str(proposal.get("unified_diff") or "")
        if not diff_text.strip():
            return ""
        lines.extend(["", "```diff", diff_text.rstrip("\n"), "```"])
    elif edit_kind == "structured_edit":
        operations = proposal.get("structured_operations")
        if not isinstance(operations, list) or not operations:
            return ""
        lines.extend(["", "```json", json.dumps(operations, ensure_ascii=False, indent=2, default=str), "```"])
    elif edit_kind == "no_op":
        if not rationale:
            return ""
        lines.append("")
        lines.append("No patch content was produced because this proposal is an explicit no_op.")
    else:
        return ""
    text = "\n".join(lines)
    return text[:limit] if int(limit or 0) > 0 else text


def partial_product_clean_text(value: Any, limit: int = 40000) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:limit] if len(text) > limit else text


def partial_products_for_30b(
    history: list[dict[str, Any]],
    *,
    code_product_build_state_kind: str,
    limit: int = 8,
) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(product: dict[str, Any]) -> None:
        if not isinstance(product, dict) or len(products) >= max(1, int(limit or 1)):
            return
        key = json.dumps(product, ensure_ascii=False, sort_keys=True, default=str)[:12000]
        if key in seen:
            return
        seen.add(key)
        products.append({k: v for k, v in product.items() if v not in (None, "", [], {})})

    for item in reversed(history if isinstance(history, list) else []):
        if len(products) >= max(1, int(limit or 1)):
            break
        if not isinstance(item, dict):
            continue
        step = item.get("step")
        result = history_tool_result(item)
        rejected = result.get("rejected_decision") if isinstance(result.get("rejected_decision"), dict) else {}
        rejected_tool = normalize_tool_name(str(rejected.get("tool") or ""))
        rejected_args = rejected.get("arguments") if isinstance(rejected.get("arguments"), dict) else {}
        violations = result.get("violations") if isinstance(result.get("violations"), list) else []
        summary = str(result.get("summary") or "").strip()

        if rejected_tool == "repo_propose_code_edit":
            add({
                "kind": "partial_code_product_candidate",
                "source": "validator_rejected_repo_propose_code_edit",
                "step": step,
                "payload_is_complete": False,
                "validator_accepted": False,
                "rejection_summary": summary,
                "violations": violations,
                "target_file": repo_rel_token(rejected_args.get("target_file") or ""),
                "edit_kind": rejected_args.get("edit_kind"),
                "rationale": partial_product_clean_text(rejected_args.get("rationale"), 8000),
                "unified_diff": partial_product_clean_text(rejected_args.get("unified_diff"), 80000),
                "old_text": partial_product_clean_text(rejected_args.get("old_text"), 30000),
                "new_text": partial_product_clean_text(rejected_args.get("new_text"), 30000),
                "structured_operations": rejected_args.get("structured_operations") if isinstance(rejected_args.get("structured_operations"), list) else None,
                "reason": partial_product_clean_text(rejected.get("reason"), 8000),
            })

        if rejected_tool == "planner_scratchpad_write" and str(rejected_args.get("kind") or "") == code_product_build_state_kind:
            state_text = partial_product_clean_text(
                rejected_args.get("text") or rejected_args.get("content"),
                80000,
            )
            parsed = code_product_build_state_parse(state_text)
            loose_payload: dict[str, Any] = {}
            if not parsed:
                try:
                    loose = json.loads(state_text)
                    if isinstance(loose, dict):
                        loose_payload = loose.get("payload") if isinstance(loose.get("payload"), dict) else loose
                except Exception:
                    loose_payload = {}
            add({
                "kind": "partial_code_product_build_state",
                "source": "validator_rejected_code_product_build_state",
                "step": step,
                "payload_is_complete": False,
                "validator_accepted": False,
                "rejection_summary": summary,
                "violations": violations,
                "target_file": repo_rel_token(
                    rejected_args.get("target_file")
                    or (parsed or loose_payload).get("target_file")
                    or ""
                ),
                "status": (parsed or loose_payload).get("status"),
                "edit_kind": (parsed or loose_payload).get("edit_kind"),
                "rationale": partial_product_clean_text((parsed or loose_payload).get("rationale"), 8000),
                "state_text": state_text,
            })

        action_plan = partial_product_clean_text(result.get("action_plan_candidate"), 40000)
        if action_plan:
            add({
                "kind": "action_plan_candidate",
                "source": "validator_rejected_final_for_code_product",
                "step": step,
                "payload_is_complete": False,
                "validator_accepted": False,
                "rejection_summary": summary,
                "violations": violations,
                "text": action_plan,
            })

        repair = result.get("vulkan_repair") if isinstance(result.get("vulkan_repair"), dict) else {}
        if repair:
            repaired = repair.get("repaired_decision") if isinstance(repair.get("repaired_decision"), dict) else {}
            text = partial_product_clean_text(
                repaired.get("final_answer")
                or repair.get("raw_text_preview")
                or repair.get("raw_planner_text_preview"),
                40000,
            )
            if text:
                add({
                    "kind": "repair_candidate_text",
                    "source": "vulkan_gpu0_repair_rejected_or_unvalidated",
                    "step": step,
                    "payload_is_complete": False,
                    "validator_accepted": False,
                    "rejection_summary": summary,
                    "violations": violations,
                    "text": text,
                    "repair_error": repair.get("error"),
                })
    return products


def best_partial_product_for_30b(
    history: list[dict[str, Any]],
    *,
    code_product_build_state_kind: str,
) -> dict[str, Any]:
    products = partial_products_for_30b(
        history,
        code_product_build_state_kind=code_product_build_state_kind,
        limit=8,
    )
    for product in products:
        if str(product.get("unified_diff") or "").strip():
            return product
    return products[0] if products else {}


def partial_product_answer_text(
    result: dict[str, Any] | None,
    *,
    code_product_build_state_kind: str,
    limit: int = 60000,
) -> str:
    result = result if isinstance(result, dict) else {}
    history = result.get("history") if isinstance(result.get("history"), list) else []
    product = result.get("best_partial_product_for_30b") if isinstance(result.get("best_partial_product_for_30b"), dict) else {}
    if not product:
        product = best_partial_product_for_30b(
            history,
            code_product_build_state_kind=code_product_build_state_kind,
        )
    if not product:
        return ""
    lines = [
        "Prodotto parziale non validato dal controller.",
        f"- kind: {product.get('kind')}",
        f"- source: {product.get('source')}",
        f"- step: {product.get('step')}",
        f"- validator_accepted: {str(product.get('validator_accepted')).lower()}",
    ]
    if product.get("target_file"):
        lines.append(f"- target_file: {product.get('target_file')}")
    if product.get("edit_kind"):
        lines.append(f"- edit_kind: {product.get('edit_kind')}")
    if product.get("rejection_summary"):
        lines.append(f"- rejection_summary: {product.get('rejection_summary')}")
    rationale = str(product.get("rationale") or "").strip()
    if rationale:
        lines.append(f"- rationale: {rationale}")
    if str(product.get("unified_diff") or "").strip():
        lines.extend(["", "```diff", str(product.get("unified_diff")).rstrip("\n"), "```"])
    elif product.get("structured_operations"):
        lines.extend(["", "```json", json.dumps(product.get("structured_operations"), ensure_ascii=False, indent=2, default=str), "```"])
    elif str(product.get("text") or "").strip():
        lines.extend(["", str(product.get("text")).strip()])
    elif str(product.get("state_text") or "").strip():
        lines.extend(["", "```json", str(product.get("state_text")).strip(), "```"])
    text = "\n".join(lines)
    return text[:limit] if int(limit or 0) > 0 else text
