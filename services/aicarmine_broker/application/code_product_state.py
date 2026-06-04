"""Deterministic code-product state and payload contract helpers."""
from __future__ import annotations

import json
from typing import Any

from .path_tokens import repo_rel_token


CODE_PRODUCT_BUILD_STATE_KIND = "code_product_build_state"
CODE_PRODUCT_BUILD_STATE_SCHEMA = "code_product_build_state.v1"


def code_product_build_state_section(target_file: str) -> str:
    target = repo_rel_token(target_file)
    return f"{CODE_PRODUCT_BUILD_STATE_KIND}:{target}" if target and target != "." else CODE_PRODUCT_BUILD_STATE_KIND


def code_product_build_state_parse(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(str(text or ""))
    except Exception:
        return {}
    if not isinstance(parsed, dict) or parsed.get("schema") != CODE_PRODUCT_BUILD_STATE_SCHEMA:
        return {}
    return parsed


def code_product_build_state_ready_payload(state: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(state, dict) or str(state.get("status") or "") != "ready_for_propose":
        return {}
    target = repo_rel_token(state.get("target_file") or "")
    if not target or target == ".":
        return {}
    edit_kind = str(state.get("edit_kind") or "").strip()
    args: dict[str, Any] = {
        "target_file": target,
        "edit_kind": edit_kind,
        "rationale": str(state.get("rationale") or "").strip(),
    }
    if isinstance(state.get("validation_commands"), list):
        args["validation_commands"] = [
            str(cmd) for cmd in state.get("validation_commands") or [] if str(cmd).strip()
        ]
    if edit_kind == "unified_diff":
        if isinstance(state.get("unified_diff"), str) and state["unified_diff"].strip():
            args["unified_diff"] = state["unified_diff"]
        elif isinstance(state.get("old_text"), str) and isinstance(state.get("new_text"), str):
            args["old_text"] = state["old_text"]
            args["new_text"] = state["new_text"]
        else:
            return {}
    elif edit_kind == "structured_edit":
        operations = state.get("structured_operations")
        if not isinstance(operations, list) or not operations:
            return {}
        args["structured_operations"] = operations
    elif edit_kind == "no_op":
        if not args["rationale"]:
            return {}
    else:
        return {}
    if not args.get("rationale"):
        return {}
    return args


def code_product_build_state_has_collecting_progress(state: dict[str, Any]) -> bool:
    if not isinstance(state, dict):
        return False
    source_windows = state.get("source_windows")
    if isinstance(source_windows, list):
        for window in source_windows:
            if not isinstance(window, dict):
                continue
            has_identity = any(
                str(window.get(key) or "").strip()
                for key in ("document_id", "section", "sha256", "window_sha256")
            )
            has_window_marker = any(
                key in window
                for key in ("offset", "window_start", "window_end", "complete", "full_chars")
            )
            if has_identity and has_window_marker:
                return True
    for key in ("old_text", "new_text", "unified_diff"):
        if isinstance(state.get(key), str) and state[key].strip():
            return True
    operations = state.get("structured_operations")
    return isinstance(operations, list) and bool(operations)


def code_product_has_preview_substitute(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) in {
                "content_preview",
                "unified_diff_preview",
                "structured_operations_preview",
                "preview_only",
            }:
                return True
            if code_product_has_preview_substitute(item):
                return True
    if isinstance(value, list):
        return any(code_product_has_preview_substitute(item) for item in value)
    if isinstance(value, str):
        low = value.lower()
        return "<truncated" in low or "[truncated" in low
    return False


def code_product_payload_violations(proposal: dict[str, Any], read_paths: set[str]) -> list[str]:
    violations: list[str] = []
    if not isinstance(proposal, dict) or proposal.get("tool") != "repo_propose_code_edit" or proposal.get("ok") is not True:
        return ["missing_code_product_candidate"]
    if code_product_has_preview_substitute(proposal):
        violations.append("code_product_payload_not_complete")
    if proposal.get("kind") != "code_edit_proposal":
        violations.append("invalid_code_product_candidate")
    target = repo_rel_token(proposal.get("target_file") or proposal.get("path") or "")
    if not target or target == ".":
        violations.append("invalid_code_product_candidate")
    elif target not in read_paths:
        violations.append("code_product_target_not_read")
    if proposal.get("source_writes_performed") is not False:
        violations.append("invalid_code_product_candidate")
    if proposal.get("patch_application_performed") is not False:
        violations.append("invalid_code_product_candidate")
    if proposal.get("manual_review_required") is not True:
        violations.append("invalid_code_product_candidate")
    errors = proposal.get("errors")
    if isinstance(errors, list) and errors:
        violations.append("invalid_code_product_candidate")

    edit_kind = str(proposal.get("edit_kind") or "")
    if edit_kind == "unified_diff":
        diff_text = proposal.get("unified_diff")
        if not isinstance(diff_text, str) or not diff_text.strip():
            violations.append("code_product_payload_not_complete")
        else:
            if not all(marker in diff_text for marker in ("---", "+++", "@@")):
                violations.append("invalid_code_product_candidate")
            normalized = diff_text.replace("\\", "/")
            if (
                target
                and target != "."
                and target not in normalized
                and f"a/{target}" not in normalized
                and f"b/{target}" not in normalized
            ):
                violations.append("invalid_code_product_candidate")
    elif edit_kind == "structured_edit":
        operations = proposal.get("structured_operations")
        if not isinstance(operations, list) or not operations:
            violations.append("code_product_payload_not_complete")
    elif edit_kind == "no_op":
        if not str(proposal.get("rationale") or "").strip():
            violations.append("invalid_code_product_candidate")
        if proposal.get("unified_diff") or proposal.get("structured_operations"):
            violations.append("invalid_code_product_candidate")
    else:
        violations.append("invalid_code_product_candidate")
    return list(dict.fromkeys(violations))


def goal_exact_text_block(goal: str, name: str) -> str:
    label = f"exact {name}:"
    lines = str(goal or "").splitlines()
    start = -1
    inline = ""
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.lower().startswith(label):
            start = idx
            inline = stripped[len(label):]
            break
    if start < 0:
        return ""

    boundary_prefixes = (
        "exact old_text:",
        "exact new_text:",
        "required behavior:",
        "required behaviour:",
        "target file:",
    )
    block: list[str] = []
    if inline.strip():
        block.append(inline.lstrip())
    for line in lines[start + 1:]:
        low = line.strip().lower()
        if any(low.startswith(prefix) for prefix in boundary_prefixes):
            break
        block.append(line.rstrip("\r"))
    while block and not block[0].strip():
        block.pop(0)
    while block and not block[-1].strip():
        block.pop()
    return "\n".join(block)
