#!/usr/bin/env python3
"""Incubating MCP adapter for repo code-product tools."""

from __future__ import annotations

from collections.abc import Callable
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

from repo_mcp_common import (
    ToolSpec,
    handle_request,
    health_payload,
    mcp_text_result,
    object_schema,
    serve,
)

SERVER_NAME = "aicarmine-repo-code-mcp"
SERVER_VERSION = "0.1.0-incubator"


def string_prop(default: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if default is not None:
        schema["default"] = default
    return schema


def enum_string_prop(values: list[str]) -> dict[str, Any]:
    return {"type": "string", "enum": values}


def integer_prop(default: int, minimum: int, maximum: int) -> dict[str, Any]:
    return {"type": "integer", "default": default, "minimum": minimum, "maximum": maximum}


def _report_only(
    tool_name: str,
    handler: Callable[[dict[str, Any], Path], dict[str, Any]],
) -> Callable[[dict[str, Any], Path], dict[str, Any]]:
    def wrapped(args: dict[str, Any], root: Path) -> dict[str, Any]:
        result = handler(args, root)
        if not isinstance(result, dict):
            return {
                "ok": False,
                "tool": tool_name,
                "error": "invalid_tool_result",
                "result_type": type(result).__name__,
            }
        result.setdefault("source_writes_performed", False)
        result.setdefault("patch_application_performed", False)
        result["mcp_server"] = SERVER_NAME
        result["incubation_status"] = "isolated_candidate"
        if result.get("source_writes_performed") or result.get("patch_application_performed"):
            return {
                "ok": False,
                "tool": tool_name,
                "error": "report_only_contract_violation",
                "mcp_server": SERVER_NAME,
                "upstream": result,
            }
        return result

    return wrapped


def _guarded_source_write(
    tool_name: str,
    handler: Callable[[dict[str, Any], Path], dict[str, Any]],
) -> Callable[[dict[str, Any], Path], dict[str, Any]]:
    def wrapped(args: dict[str, Any], root: Path) -> dict[str, Any]:
        if args.get("allow_source_write") is not True:
            return {
                "ok": False,
                "tool": tool_name,
                "error": "source_write_not_enabled",
                "required_arg": "allow_source_write=true",
                "mcp_server": SERVER_NAME,
                "source_writes_performed": False,
                "patch_application_performed": False,
            }
        result = handler(args, root)
        if not isinstance(result, dict):
            return {
                "ok": False,
                "tool": tool_name,
                "error": "invalid_tool_result",
                "result_type": type(result).__name__,
                "mcp_server": SERVER_NAME,
                "source_writes_performed": False,
                "patch_application_performed": False,
            }
        changed = bool(result.get("ok") and result.get("changed"))
        result["mcp_server"] = SERVER_NAME
        result["incubation_status"] = "isolated_candidate"
        result["write_scope"] = str(
            result.get("write_scope") or "exact_old_text_new_text_only"
        )
        result["source_writes_performed"] = changed
        result["patch_application_performed"] = changed
        return result

    return wrapped


def _tools() -> dict[str, ToolSpec]:
    from aicarmine_broker.tools.repo_code_product import (
        repo_propose_code_edit,
        repo_propose_unified_diff,
    )
    from aicarmine_broker.tools.repo_deterministic import (
        repo_git_apply_check,
        repo_unidiff_validate,
    )
    from aicarmine_broker.tools.repo_patch import (
        repo_apply_patch,
        repo_apply_unified_diff,
    )
    from repo_code_change_set import (
        build_structured_edit_diff,
        change_set_error_payload,
        materialize_change_set,
        public_change_set_fields,
        resolve_change_set,
    )

    tools: dict[str, ToolSpec] = {}

    def with_change_set_fields(
        result: dict[str, Any],
        change_set: dict[str, Any],
        stage: str,
    ) -> dict[str, Any]:
        fields = public_change_set_fields(change_set, stage)
        return {
            "ok": result.get("ok", False),
            "tool": result.get("tool"),
            **fields,
            **{
                key: value
                for key, value in result.items()
                if key not in {"ok", "tool", *fields}
            },
        }

    def propose_edit(args: dict[str, Any], root: Path) -> dict[str, Any]:
        has_edits = args.get("edits") is not None
        has_inline_diff = any(
            isinstance(args.get(name), str) and str(args.get(name)).strip()
            for name in ("unified_diff", "diff", "patch")
        )
        has_change_set_id = bool(str(args.get("change_set_id") or "").strip())
        has_legacy_text = any(
            args.get(name) is not None for name in ("old_text", "new_text")
        )
        has_legacy_structured = any(
            args.get(name) is not None
            for name in ("structured_operations", "operations")
        )
        edit_modes = (
            int(has_edits)
            + int(has_inline_diff or has_change_set_id)
            + int(has_legacy_text)
        )
        if (
            edit_modes > 1
            or (has_edits and has_legacy_structured)
            or ((has_inline_diff or has_change_set_id) and has_legacy_structured)
        ):
            return {
                "ok": False,
                "tool": "repo_propose_code_edit",
                "error": "ambiguous_edit_mode",
                "source_writes_performed": False,
                "patch_application_performed": False,
            }

        if has_edits:
            edit_kind = str(args.get("edit_kind") or "").strip()
            if edit_kind not in {"", "structured_edit"}:
                return {
                    "ok": False,
                    "tool": "repo_propose_code_edit",
                    "error": "ambiguous_edit_mode",
                    "source_writes_performed": False,
                    "patch_application_performed": False,
                }
            rationale = str(
                args.get("rationale") or args.get("reason") or ""
            ).strip()
            if not rationale:
                return {
                    "ok": False,
                    "tool": "repo_propose_code_edit",
                    "error": "structured_edit_rationale_missing",
                    "source_writes_performed": False,
                    "patch_application_performed": False,
                }
            try:
                generated = build_structured_edit_diff(root, args.get("edits"))
                change_set = materialize_change_set(
                    root,
                    generated["unified_diff"],
                )
            except Exception as exc:
                return change_set_error_payload("repo_propose_code_edit", exc)
            validation_commands = args.get("validation_commands")
            if not isinstance(validation_commands, list):
                validation_commands = ["git diff --check"]
            result = {
                "ok": True,
                "tool": "repo_propose_code_edit",
                "kind": "code_edit_proposal",
                "edit_kind": "structured_edit",
                "rationale": rationale,
                "unified_diff": generated["unified_diff"],
                "structured_edit_summary": {
                    "edit_count": generated["edit_count"],
                    "file_count": generated["file_count"],
                    "files": generated["files"],
                },
                "validation_commands": validation_commands,
                "manual_review_required": True,
                "source_writes_performed": False,
                "patch_application_performed": False,
            }
            return with_change_set_fields(result, change_set, "proposed")

        has_change_set_input = has_change_set_id or has_inline_diff
        if has_change_set_input:
            return repo_propose_unified_diff(args, root)

        normalized_args = dict(args)
        if not str(normalized_args.get("edit_kind") or "").strip():
            if isinstance(normalized_args.get("old_text"), str) and isinstance(
                normalized_args.get("new_text"), str
            ):
                normalized_args["edit_kind"] = "unified_diff"
            elif isinstance(
                normalized_args.get("structured_operations")
                or normalized_args.get("operations"),
                list,
            ):
                normalized_args["edit_kind"] = "structured_edit"

        result = repo_propose_code_edit(normalized_args, root)
        generated_diff = result.get("unified_diff") if isinstance(result, dict) else None
        if not result.get("ok") or not isinstance(generated_diff, str) or not generated_diff.strip():
            return result
        try:
            change_set = materialize_change_set(root, generated_diff)
        except Exception as exc:
            return change_set_error_payload("repo_propose_code_edit", exc)
        return with_change_set_fields(result, change_set, "proposed")

    def resolve_and_call(
        args: dict[str, Any],
        root: Path,
        
        stage: str,
        handler: Callable[[dict[str, Any], Path], dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            change_set = resolve_change_set(args, root)
        except Exception as exc:
            return change_set_error_payload(handler.__name__, exc)
        resolved_args = dict(args)
        resolved_args["unified_diff"] = change_set["normalized_diff"]
        resolved_args["_verified_change_set"] = True
        result = handler(resolved_args, root)
        return with_change_set_fields(result, change_set, stage)

    def validate_unified_diff(args: dict[str, Any], root: Path) -> dict[str, Any]:
        return resolve_and_call(
            args,
            root,
            stage="validated",
            handler=repo_unidiff_validate,
        )

    def check_unified_diff(args: dict[str, Any], root: Path) -> dict[str, Any]:
        return resolve_and_call(
            args,
            root,
            stage="apply_checked",
            handler=repo_git_apply_check,
        )

    def apply_patch(args: dict[str, Any], root: Path) -> dict[str, Any]:
        has_diff_mode = bool(
            str(args.get("change_set_id") or "").strip()
            or any(
                isinstance(args.get(name), str) and str(args.get(name)).strip()
                for name in ("unified_diff", "diff", "patch")
            )
        )
        has_exact_mode = any(
            args.get(name) is not None
            for name in ("path", "old_text", "new_text")
        )
        if has_diff_mode and has_exact_mode:
            return {
                "ok": False,
                "tool": "repo_apply_patch",
                "error": "ambiguous_patch_mode",
                "source_writes_performed": False,
                "patch_application_performed": False,
            }
        if not has_diff_mode:
            return repo_apply_patch(args, root)

        try:
            change_set = resolve_change_set(args, root)
        except Exception as exc:
            return change_set_error_payload("repo_apply_unified_diff", exc)
        resolved_args = dict(args)
        resolved_args["unified_diff"] = change_set["normalized_diff"]
        resolved_args["change_set_id"] = change_set["change_set_id"]
        resolved_args["_change_set_metadata"] = change_set["metadata"]
        resolved_args["_verified_change_set"] = True
        result = repo_apply_unified_diff(resolved_args, root)
        return with_change_set_fields(result, change_set, "applied")

    def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
        payload = health_payload(SERVER_NAME, list(tools))
        payload["incubation_status"] = "isolated_candidate"
        payload["proposal_edit_kinds"] = [
            "structured_edit",
            "unified_diff",
            "no_op",
        ]
        payload["preferred_authoring_mode"] = "structured_edit"
        payload["structured_edit_multi_file"] = True
        payload["structured_edit_operations"] = [
            "replace_exact",
            "insert_before_exact",
            "insert_after_exact",
            "create_file",
        ]
        payload["structured_edit_limits"] = {
            "maximum_diff_bytes": 2 * 1024 * 1024,
            "maximum_files": 100,
        }
        payload["client_guidance"] = [
            "Prefer structured_edit with edits for repository authoring.",
            "Use unified_diff only when the client already owns a valid diff.",
            "Do not construct hunk headers or transport .diff files client-side.",
            "After propose_edit, propagate only change_set_id.",
        ]
        payload["apply_modes"] = [
            "exact_old_text_new_text",
            "unified_diff",
            "change_set_id",
        ]
        payload["multi_file_unified_diff"] = True
        payload["change_set_propagation"] = True
        payload["promotion_rule"] = (
            "Promote tools into semantic MCP servers only after repeated clean "
            "self-tests and no source-write contract violations."
        )
        return payload

    tools["aicarmine_repo_code_health"] = ToolSpec(
        name="aicarmine_repo_code_health",
        description="Report repo-code incubator MCP health and no-loop guarantees.",
        input_schema=object_schema(),
        handler=health,
    )
    tools["aicarmine_repo_code_propose_edit"] = ToolSpec(
        name="aicarmine_repo_code_propose_edit",
        description=(
            "Build a report-only code edit proposal. Prefer multi-file "
            "structured_edit edits; use unified_diff only when already valid. "
            "Does not write source files."
        ),
        input_schema=object_schema(
            {
                "target_file": string_prop(),
                "path": string_prop(),
                "edit_kind": enum_string_prop(
                    ["structured_edit", "unified_diff", "no_op"]
                ),
                "edits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": string_prop(),
                            "operation": enum_string_prop(
                                [
                                    "replace_exact",
                                    "insert_before_exact",
                                    "insert_after_exact",
                                    "create_file",
                                ]
                            ),
                            "old_text": string_prop(),
                            "new_text": string_prop(),
                            "anchor": string_prop(),
                            "content": string_prop(),
                            "expected_occurrences": integer_prop(1, 1, 1000000),
                        },
                        "required": ["path", "operation"],
                    },
                },
                "rationale": string_prop(),
                "reason": string_prop(),
                "unified_diff": string_prop(),
                "diff": string_prop(),
                "patch": string_prop(),
                "change_set_id": string_prop(),
                "old_text": string_prop(),
                "new_text": string_prop(),
                "structured_operations": {"type": "array", "items": {"type": "object"}},
                "operations": {"type": "array", "items": {"type": "object"}},
                "validation_commands": {"type": "array", "items": {"type": "string"}},
                "require_unidiff": {"type": "boolean", "default": True},
                "ast_anchor": string_prop(),
                "ast_grep_rule": string_prop(),
                "tree_sitter_language": string_prop(),
            }
        ),
        handler=_report_only("repo_propose_code_edit", propose_edit),
        required_one_of=[
            ["edits"],
            ["target_file"],
            ["path"],
            ["unified_diff"],
            ["diff"],
            ["patch"],
            ["change_set_id"],
        ],
    )
    tools["aicarmine_repo_code_unidiff_validate"] = ToolSpec(
        name="aicarmine_repo_code_unidiff_validate",
        description="Validate unified diff structure without applying it.",
        input_schema=object_schema(
            {
                "unified_diff": string_prop(),
                "diff": string_prop(),
                "patch": string_prop(),
                "change_set_id": string_prop(),
            }
        ),
        handler=_report_only("repo_unidiff_validate", validate_unified_diff),
        required_one_of=[
            ["unified_diff"],
            ["diff"],
            ["patch"],
            ["change_set_id"],
        ],
    )
    tools["aicarmine_repo_code_git_apply_check"] = ToolSpec(
        name="aicarmine_repo_code_git_apply_check",
        description="Run git apply --check on a unified diff without applying it.",
        input_schema=object_schema(
            {
                "unified_diff": string_prop(),
                "diff": string_prop(),
                "patch": string_prop(),
                "change_set_id": string_prop(),
                "timeout_seconds": integer_prop(120, 1, 600),
            }
        ),
        handler=_report_only("repo_git_apply_check", check_unified_diff),
        required_one_of=[
            ["unified_diff"],
            ["diff"],
            ["patch"],
            ["change_set_id"],
        ],
    )
    tools["aicarmine_repo_code_apply_patch"] = ToolSpec(
        name="aicarmine_repo_code_apply_patch",
        description=(
            "Apply either an exact old_text/new_text patch or a validated unified "
            "diff/change-set in the incubator MCP. Requires allow_source_write=true."
        ),
        input_schema=object_schema(
            {
                "path": string_prop(),
                "old_text": string_prop(),
                "new_text": string_prop(),
                "unified_diff": string_prop(),
                "diff": string_prop(),
                "patch": string_prop(),
                "change_set_id": string_prop(),
                "max_replacements": integer_prop(1, 1, 100),
                "allow_source_write": {"type": "boolean", "default": False},
            },
            required=["allow_source_write"],
        ),
        handler=_guarded_source_write("repo_apply_patch", apply_patch),
        required_one_of=[
            ["path", "old_text", "new_text"],
            ["unified_diff"],
            ["diff"],
            ["patch"],
            ["change_set_id"],
        ],
    )
    return tools


def _self_test_git(root: Path, *args: str) -> None:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {completed.stderr[-1000:]}"
        )


def _self_test_write(root: Path, relative_path: str, content: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))


def _self_test_repo(root: Path, files: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _self_test_git(root, "init", "-q")
    _self_test_git(root, "config", "user.email", "repo-code-self-test@example.invalid")
    _self_test_git(root, "config", "user.name", "Repo Code Self Test")
    _self_test_git(root, "config", "core.autocrlf", "false")
    for relative_path, content in files.items():
        _self_test_write(root, relative_path, content)
    _self_test_git(root, "add", "--all")
    _self_test_git(root, "commit", "-q", "-m", "fixture")


def _repo_code_self_test(tools: dict[str, ToolSpec]) -> dict[str, Any]:
    call_names: list[str] = []
    call_id = 10
    root_env_names = (
        "AICARMINE_CODEX_MCP_REPO_ROOT",
        "AICARMINE_LAB_REPO",
    )
    original_env = {name: os.environ.get(name) for name in root_env_names}
    results: dict[str, Any] = {}

    def select_root(root: Path) -> None:
        for name in root_env_names:
            os.environ[name] = str(root)

    def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        nonlocal call_id
        call_id += 1
        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": call_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
            server_name=SERVER_NAME,
            server_version=SERVER_VERSION,
            tools=tools,
        )
        call_names.append(name)
        return mcp_text_result(response if isinstance(response, dict) else {})

    def artifact_count(root: Path) -> int:
        directory = root / "state" / "repo_code" / "change_sets"
        return len(list(directory.glob("*"))) if directory.is_dir() else 0

    try:
        initialized = handle_request(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            server_name=SERVER_NAME,
            server_version=SERVER_VERSION,
            tools=tools,
        )
        listed = handle_request(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            server_name=SERVER_NAME,
            server_version=SERVER_VERSION,
            tools=tools,
        )
        list_result = listed.get("result") if isinstance(listed, dict) else {}
        listed_tools = (
            list_result.get("tools", [])
            if isinstance(list_result, dict)
            else []
        )
        listed_names = [
            item.get("name") for item in listed_tools if isinstance(item, dict)
        ]
        propose_schema = next(
            (
                item.get("inputSchema")
                for item in listed_tools
                if isinstance(item, dict)
                and item.get("name") == "aicarmine_repo_code_propose_edit"
            ),
            {},
        )
        edit_schema_present = bool(
            isinstance(propose_schema, dict)
            and isinstance(propose_schema.get("properties"), dict)
            and "edits" in propose_schema["properties"]
        )

        with tempfile.TemporaryDirectory(prefix="aicarmine-repo-code-ps-") as temp:
            root = Path(temp)
            powershell_before = (
                "$rawInput = [Console]::In.ReadToEnd()\r\n"
                "$helper = Join-Path $PSScriptRoot 'lib\\helper.ps1'\r\n"
                "Write-Output \u0060\"$rawInput\u0060\"\r\n"
                "[ordered]@{ value = $rawInput }\r\n"
            )
            powershell_after = powershell_before.replace(
                "Write-Output \u0060\"$rawInput\u0060\"",
                "Write-Output \u0060\"$rawInput processed\u0060\"",
            )
            _self_test_repo(root, {"hook.ps1": powershell_before})
            select_root(root)
            health = call("aicarmine_repo_code_health", {})
            proposal = call(
                "aicarmine_repo_code_propose_edit",
                {
                    "edit_kind": "structured_edit",
                    "edits": [
                        {
                            "path": "hook.ps1",
                            "operation": "replace_exact",
                            "old_text": (
                                "Write-Output \u0060\"$rawInput\u0060\"\r\n"
                                "[ordered]@{"
                            ),
                            "new_text": (
                                "Write-Output \u0060\"$rawInput processed\u0060\"\r\n"
                                "[ordered]@{"
                            ),
                            "expected_occurrences": 1,
                        }
                    ],
                    "rationale": "PowerShell structured-edit self-test",
                    "validation_commands": ["git diff --check"],
                },
            )
            change_set_id = str(proposal.get("change_set_id") or "")
            unchanged_before_apply = (
                (root / "hook.ps1").read_bytes()
                == powershell_before.encode("utf-8")
            )
            validated = call(
                "aicarmine_repo_code_unidiff_validate",
                {"change_set_id": change_set_id},
            )
            checked = call(
                "aicarmine_repo_code_git_apply_check",
                {"change_set_id": change_set_id},
            )
            applied = call(
                "aicarmine_repo_code_apply_patch",
                {
                    "change_set_id": change_set_id,
                    "allow_source_write": True,
                },
            )
            actual_powershell_bytes = (root / "hook.ps1").read_bytes()
            expected_powershell_bytes = powershell_after.encode("utf-8")
            results["powershell_content"] = {
                "ok": bool(
                    proposal.get("ok")
                    and validated.get("ok")
                    and checked.get("ok")
                    and applied.get("ok")
                    and unchanged_before_apply
                    and actual_powershell_bytes == expected_powershell_bytes
                ),
                "change_set_id": change_set_id,
                "server_generated_unified_diff": bool(
                    proposal.get("unified_diff")
                ),
                "source_unchanged_during_propose": unchanged_before_apply,
                "proposal_error": proposal.get("error"),
                "validate_error": validated.get("error"),
                "apply_check_error": checked.get("error"),
                "apply_error": applied.get("error"),
                "content_exact": (
                    actual_powershell_bytes == expected_powershell_bytes
                ),
                "actual_bytes": repr(actual_powershell_bytes)[:1000],
                "expected_bytes": repr(expected_powershell_bytes)[:1000],
            }

        with tempfile.TemporaryDirectory(prefix="aicarmine-repo-code-multi-") as temp:
            root = Path(temp)
            _self_test_repo(
                root,
                {
                    "first.txt": "alpha\n",
                    "second.txt": "top\nbottom\n",
                },
            )
            select_root(root)
            proposal = call(
                "aicarmine_repo_code_propose_edit",
                {
                    "edit_kind": "structured_edit",
                    "edits": [
                        {
                            "path": "first.txt",
                            "operation": "replace_exact",
                            "old_text": "alpha",
                            "new_text": "beta",
                            "expected_occurrences": 1,
                        },
                        {
                            "path": "second.txt",
                            "operation": "insert_before_exact",
                            "anchor": "bottom\n",
                            "content": "middle\n",
                            "expected_occurrences": 1,
                        },
                        {
                            "path": "second.txt",
                            "operation": "insert_after_exact",
                            "anchor": "bottom\n",
                            "content": "tail\n",
                            "expected_occurrences": 1,
                        },
                        {
                            "path": "created.txt",
                            "operation": "create_file",
                            "content": "created\n",
                        },
                    ],
                    "rationale": "Multi-file structured-edit self-test",
                },
            )
            change_set_id = str(proposal.get("change_set_id") or "")
            validated = call(
                "aicarmine_repo_code_unidiff_validate",
                {"change_set_id": change_set_id},
            )
            checked = call(
                "aicarmine_repo_code_git_apply_check",
                {"change_set_id": change_set_id},
            )
            applied = call(
                "aicarmine_repo_code_apply_patch",
                {
                    "change_set_id": change_set_id,
                    "allow_source_write": True,
                },
            )
            results["multi_file"] = {
                "ok": bool(
                    proposal.get("ok")
                    and proposal.get("file_count") == 3
                    and validated.get("ok")
                    and checked.get("ok")
                    and applied.get("ok")
                    and (root / "first.txt").read_text(encoding="utf-8")
                    == "beta\n"
                    and (root / "second.txt").read_text(encoding="utf-8")
                    == "top\nmiddle\nbottom\ntail\n"
                    and (root / "created.txt").read_text(encoding="utf-8")
                    == "created\n"
                ),
                "change_set_id": change_set_id,
                "file_count": proposal.get("file_count"),
                "added_paths": applied.get("added_paths"),
                "modified_paths": applied.get("modified_paths"),
            }

        with tempfile.TemporaryDirectory(prefix="aicarmine-repo-code-anchor-") as temp:
            root = Path(temp)
            _self_test_repo(root, {"anchor.txt": "same\nsame\n"})
            select_root(root)
            before_count = artifact_count(root)
            missing = call(
                "aicarmine_repo_code_propose_edit",
                {
                    "edit_kind": "structured_edit",
                    "edits": [
                        {
                            "path": "anchor.txt",
                            "operation": "replace_exact",
                            "old_text": "missing",
                            "new_text": "new",
                            "expected_occurrences": 1,
                        }
                    ],
                    "rationale": "Missing anchor self-test",
                },
            )
            after_missing_count = artifact_count(root)
            ambiguous = call(
                "aicarmine_repo_code_propose_edit",
                {
                    "edit_kind": "structured_edit",
                    "edits": [
                        {
                            "path": "anchor.txt",
                            "operation": "replace_exact",
                            "old_text": "same",
                            "new_text": "new",
                            "expected_occurrences": 1,
                        }
                    ],
                    "rationale": "Ambiguous anchor self-test",
                },
            )
            after_ambiguous_count = artifact_count(root)
            results["anchor_not_found"] = {
                "ok": bool(
                    missing.get("error") == "structured_edit_anchor_not_found"
                    and before_count == after_missing_count
                ),
                "error": missing.get("error"),
                "change_set_persisted": after_missing_count != before_count,
            }
            results["ambiguous_anchor"] = {
                "ok": bool(
                    ambiguous.get("error") == "structured_edit_ambiguous"
                    and after_missing_count == after_ambiguous_count
                ),
                "error": ambiguous.get("error"),
                "change_set_persisted": (
                    after_ambiguous_count != after_missing_count
                ),
            }

        with tempfile.TemporaryDirectory(prefix="aicarmine-repo-code-stale-") as temp:
            root = Path(temp)
            _self_test_repo(root, {"stale.txt": "original\n"})
            select_root(root)
            proposal = call(
                "aicarmine_repo_code_propose_edit",
                {
                    "edit_kind": "structured_edit",
                    "edits": [
                        {
                            "path": "stale.txt",
                            "operation": "replace_exact",
                            "old_text": "original",
                            "new_text": "planned",
                            "expected_occurrences": 1,
                        }
                    ],
                    "rationale": "Stale preimage self-test",
                },
            )
            _self_test_write(root, "stale.txt", "external\n")
            stale_apply = call(
                "aicarmine_repo_code_apply_patch",
                {
                    "change_set_id": proposal.get("change_set_id"),
                    "allow_source_write": True,
                },
            )
            results["stale_preimage"] = {
                "ok": bool(
                    stale_apply.get("error") == "change_set_preimage_mismatch"
                    and stale_apply.get("source_writes_performed") is False
                    and (root / "stale.txt").read_text(encoding="utf-8")
                    == "external\n"
                ),
                "error": stale_apply.get("error"),
                "source_writes_performed": stale_apply.get(
                    "source_writes_performed"
                ),
                "content_preserved": (
                    (root / "stale.txt").read_text(encoding="utf-8")
                    == "external\n"
                ),
            }

        with tempfile.TemporaryDirectory(prefix="aicarmine-repo-code-legacy-") as temp:
            root = Path(temp)
            _self_test_repo(
                root,
                {
                    "unified.txt": "one\n",
                    "legacy.txt": "left\n",
                    "exact.txt": "before\n",
                },
            )
            select_root(root)
            inline_diff = (
                "--- a/unified.txt\n"
                "+++ b/unified.txt\n"
                "@@ -1 +1 @@\n"
                "-one\n"
                "+two\n"
            )
            inline_proposal = call(
                "aicarmine_repo_code_propose_edit",
                {
                    "edit_kind": "unified_diff",
                    "unified_diff": inline_diff,
                    "rationale": "Inline unified diff compatibility",
                },
            )
            inline_validation = call(
                "aicarmine_repo_code_unidiff_validate",
                {"unified_diff": inline_diff},
            )
            from aicarmine_broker.tools import repo_code_product as legacy_product
            from aicarmine_broker.tools import repo_patch as legacy_patch

            previous_product_root = legacy_product.LAB_REPO
            previous_patch_root = legacy_patch.LAB_REPO
            legacy_product.LAB_REPO = root
            legacy_patch.LAB_REPO = root
            try:
                legacy_proposal = call(
                    "aicarmine_repo_code_propose_edit",
                    {
                        "path": "legacy.txt",
                        "old_text": "left",
                        "new_text": "right",
                        "rationale": "Legacy old/new compatibility",
                    },
                )
                exact_apply = call(
                    "aicarmine_repo_code_apply_patch",
                    {
                        "path": "exact.txt",
                        "old_text": "before",
                        "new_text": "after",
                        "allow_source_write": True,
                    },
                )
            finally:
                legacy_product.LAB_REPO = previous_product_root
                legacy_patch.LAB_REPO = previous_patch_root
            ambiguous_mode = call(
                "aicarmine_repo_code_propose_edit",
                {
                    "edit_kind": "structured_edit",
                    "edits": [
                        {
                            "path": "legacy.txt",
                            "operation": "replace_exact",
                            "old_text": "left",
                            "new_text": "right",
                            "expected_occurrences": 1,
                        }
                    ],
                    "unified_diff": inline_diff,
                    "rationale": "Ambiguous mode self-test",
                },
            )
            results["unified_diff_compatibility"] = {
                "ok": bool(
                    inline_proposal.get("ok")
                    and inline_proposal.get("change_set_id")
                    and inline_validation.get("ok")
                ),
                "change_set_id": inline_proposal.get("change_set_id"),
                "inline_validate_ok": inline_validation.get("ok"),
            }
            results["legacy_compatibility"] = {
                "ok": bool(
                    legacy_proposal.get("ok")
                    and legacy_proposal.get("change_set_id")
                    and exact_apply.get("ok")
                    and (root / "exact.txt").read_text(encoding="utf-8")
                    == "after\n"
                ),
                "old_text_new_text_change_set_id": legacy_proposal.get(
                    "change_set_id"
                ),
                "exact_apply_ok": exact_apply.get("ok"),
            }
            results["ambiguous_edit_mode"] = {
                "ok": ambiguous_mode.get("error") == "ambiguous_edit_mode",
                "error": ambiguous_mode.get("error"),
            }

        required_tools = {
            "aicarmine_repo_code_health",
            "aicarmine_repo_code_propose_edit",
            "aicarmine_repo_code_unidiff_validate",
            "aicarmine_repo_code_git_apply_check",
            "aicarmine_repo_code_apply_patch",
        }
        initialize_ok = bool(initialized and "error" not in initialized)
        tools_list_ok = required_tools.issubset(set(listed_names))
        all_sections_ok = all(
            isinstance(value, dict) and value.get("ok") is True
            for value in results.values()
        )
        return {
            "ok": bool(
                initialize_ok
                and tools_list_ok
                and edit_schema_present
                and required_tools.issubset(set(call_names))
                and health.get("preferred_authoring_mode")
                == "structured_edit"
                and all_sections_ok
            ),
            "server": SERVER_NAME,
            "initialize_ok": initialize_ok,
            "tools_list_ok": tools_list_ok,
            "tool_count": len(listed_names),
            "tool_names": listed_names,
            "structured_edit_schema_present": edit_schema_present,
            "preferred_authoring_mode": health.get(
                "preferred_authoring_mode"
            ),
            "real_tools_called": sorted(set(call_names)),
            **results,
        }
    except Exception as exc:
        return {
            "ok": False,
            "server": SERVER_NAME,
            "error": "repo_code_self_test_failed",
            "error_type": type(exc).__name__,
            "message": str(exc),
            "partial_results": results,
            "real_tools_called": sorted(set(call_names)),
        }
    finally:
        for name, value in original_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    if "--self-test" in argv:
        result = _repo_code_self_test(tools)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())
