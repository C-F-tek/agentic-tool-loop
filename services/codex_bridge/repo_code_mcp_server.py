#!/usr/bin/env python3
"""Incubating MCP adapter for repo code-product tools."""

from __future__ import annotations

from collections.abc import Callable
import json
import sys
from pathlib import Path
from typing import Any

from repo_mcp_common import (
    ToolSpec,
    health_payload,
    object_schema,
    self_test,
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
        has_change_set_input = bool(
            str(args.get("change_set_id") or "").strip()
            or any(
                isinstance(args.get(name), str) and str(args.get(name)).strip()
                for name in ("unified_diff", "diff", "patch")
            )
        )
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
        *,
        stage: str,
        handler: Callable[[dict[str, Any], Path], dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            change_set = resolve_change_set(args, root)
        except Exception as exc:
            return change_set_error_payload(handler.__name__, exc)
        resolved_args = dict(args)
        resolved_args["unified_diff"] = change_set["normalized_diff"]
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
        result = repo_apply_unified_diff(resolved_args, root)
        return with_change_set_fields(result, change_set, "applied")

    def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
        payload = health_payload(SERVER_NAME, list(tools))
        payload["incubation_status"] = "isolated_candidate"
        payload["proposal_edit_kinds"] = [
            "unified_diff",
            "structured_edit",
            "no_op",
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
        description="Build a report-only code edit proposal. Does not apply patches or write source files.",
        input_schema=object_schema(
            {
                "target_file": string_prop(),
                "path": string_prop(),
                "edit_kind": enum_string_prop(
                    ["unified_diff", "structured_edit", "no_op"]
                ),
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


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    if "--self-test" in argv:
        result = self_test(
            server_name=SERVER_NAME,
            server_version=SERVER_VERSION,
            tools=tools,
            health_tool="aicarmine_repo_code_health",
            real_tool="aicarmine_repo_code_unidiff_validate",
            real_args={
                "unified_diff": (
                    "--- a/services/codex_bridge/repo_code_mcp_server.py\n"
                    "+++ b/services/codex_bridge/repo_code_mcp_server.py\n"
                    "@@ -1,2 +1,2 @@\n"
                    " #!/usr/bin/env python3\n"
                    '-"""Incubating MCP adapter for repo code-product tools."""\n'
                    '+"""Incubating MCP adapter for repo code-product change sets."""\n'
                )
            },
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())
