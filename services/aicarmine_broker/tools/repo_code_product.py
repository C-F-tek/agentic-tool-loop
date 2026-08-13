from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import LAB_REPO, parse_bool
from ..job_store import now, write_json


def repo_propose_unified_diff(args: dict[str, Any], root: Path) -> dict[str, Any]:
    from repo_code_change_set import (
        change_set_error_payload,
        public_change_set_fields,
        resolve_change_set,
    )

    rationale = str(args.get("rationale") or args.get("reason") or "").strip()
    edit_kind = str(args.get("edit_kind") or "unified_diff").strip()
    if edit_kind != "unified_diff":
        return {
            "ok": False,
            "tool": "repo_propose_unified_diff",
            "error": "edit_kind_invalid_for_change_set",
            "allowed": ["unified_diff"],
            "actual": edit_kind,
        }
    if not rationale:
        return {
            "ok": False,
            "tool": "repo_propose_unified_diff",
            "error": "rationale_missing",
        }

    try:
        change_set = resolve_change_set(args, root)
    except Exception as exc:
        return change_set_error_payload("repo_propose_unified_diff", exc)

    validation_commands = (
        [str(command) for command in args.get("validation_commands") if str(command).strip()]
        if isinstance(args.get("validation_commands"), list)
        else ["git diff --check"]
    )
    payload = {
        "ok": True,
        "tool": "repo_propose_unified_diff",
        **public_change_set_fields(change_set, "proposed"),
        "kind": "unified_diff_proposal",
        "proposal_mode": "multi_file_unified_diff",
        "edit_kind": "unified_diff",
        "rationale": rationale,
        "source_writes_performed": False,
        "patch_application_performed": False,
        "manual_review_required": True,
        "validation_commands": validation_commands,
        "diff_inline": False,
        "change_set_resolvable": True,
        "errors": [],
        "warnings": [],
    }
    artifact = root / "tool-results" / f"{now()}-repo_propose_unified_diff.json"
    write_json(artifact, payload)
    payload["artifact"] = str(artifact)
    return payload


def repo_propose_code_edit(args: dict[str, Any], root: Path) -> dict[str, Any]:
    try:
        from aicarmine_broker.code_edit_proposal_contract import build_code_edit_proposal
    except Exception as exc:
        return {
            "ok": False,
            "tool": "repo_propose_code_edit",
            "error": "code_edit_proposal_helper_missing",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }

    target_file = str(args.get("target_file") or args.get("path") or "").strip()
    edit_kind = str(args.get("edit_kind") or "").strip()
    rationale = str(args.get("rationale") or args.get("reason") or "").strip()
    validation_commands = (
        [str(cmd) for cmd in args.get("validation_commands") if str(cmd).strip()]
        if isinstance(args.get("validation_commands"), list)
        else None
    )

    tree_sitter_language = str(args.get("tree_sitter_language") or "").strip()
    if not tree_sitter_language and target_file.replace("\\", "/").endswith(".py"):
        tree_sitter_language = "python"

    try:
        proposal = build_code_edit_proposal(
            repo_root=LAB_REPO,
            target_file=target_file,
            edit_kind=edit_kind,
            rationale=rationale,
            unified_diff=args.get("unified_diff"),
            structured_operations=args.get("structured_operations") or args.get("operations"),
            old_text=args.get("old_text") if isinstance(args.get("old_text"), str) else None,
            new_text=args.get("new_text") if isinstance(args.get("new_text"), str) else None,
            validation_commands=validation_commands,
            require_unidiff=parse_bool(args.get("require_unidiff"), default=True),
            ast_anchor=str(args.get("ast_anchor") or "").strip() or None,
            ast_grep_rule=str(args.get("ast_grep_rule") or "").strip() or None,
            tree_sitter_language=tree_sitter_language or None,
        )
    except Exception as exc:
        proposal = {
            "kind": "code_edit_proposal",
            "target_file": target_file,
            "edit_kind": edit_kind,
            "rationale": rationale,
            "source_writes_performed": False,
            "patch_application_performed": False,
            "manual_review_required": True,
            "validation_commands": validation_commands or [],
            "errors": [f"code_edit_proposal_build_failed:{type(exc).__name__}"],
            "warnings": [],
            "message": str(exc),
        }

    payload = {
        "ok": not bool(proposal.get("errors")),
        "tool": "repo_propose_code_edit",
        **proposal,
    }
    artifact = root / "tool-results" / f"{now()}-repo_propose_code_edit.json"
    write_json(artifact, payload)
    payload["artifact"] = str(artifact)
    return payload
