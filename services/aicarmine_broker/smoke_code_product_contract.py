# type: ignore
# Runtime contract smoke: dynamic harness intentionally excluded from Pyright gate.
from __future__ import annotations

import importlib
import json
import importlib.util
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any


SERVICES_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICES_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICES_ROOT))

from aicarmine_broker import job_html, memory_tools, planner, repo_tools, tool_registry  # noqa: E402
from aicarmine_broker.code_edit_proposal_contract import (  # noqa: E402
    generate_unified_diff_from_texts,
    validate_unified_diff_text,
)
from aicarmine_broker.application.code_product.history import latest_code_product_build_state  # noqa: E402
from aicarmine_broker.application.controller import rag_preseed  # noqa: E402
from aicarmine_broker.tool_contract import TOOLS_SCHEMA  # noqa: E402
from vulkan_bridge import app as bridge_app  # noqa: E402

repo_code_product_tool = importlib.import_module("aicarmine_broker.tools.repo_code_product")
evidence_builder = importlib.import_module("aicarmine_broker.application.evidence.builder")
planner_turn = importlib.import_module("aicarmine_broker.application.planner.turn")
repo_list_files_tool = importlib.import_module("aicarmine_broker.tools.repo_list_files")
repo_read_tool = importlib.import_module("aicarmine_broker.tools.repo_read")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


OPTIONAL_PROPOSAL_DEPENDENCY_ERRORS = {
    "unidiff_dependency_missing",
    "tree_sitter_dependency_missing",
}


def proposal_ok_or_dependency_only(result: dict[str, Any]) -> bool:
    if result.get("ok") is True:
        return True
    errors = {
        str(error)
        for error in result.get("errors") or []
        if str(error)
    }
    return bool(errors) and errors <= OPTIONAL_PROPOSAL_DEPENDENCY_ERRORS


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def compact_history_row(
    *,
    root: Path,
    step: int,
    tool: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    raw_path = root / "tool-results" / f"step-{step:03d}-{tool}.json"
    write_json(raw_path, result)
    compact = planner.compact_tool_result_for_planner(tool, result)
    compact["artifact"] = str(raw_path)
    return {
        "step": step,
        "decision": {"action": "tool", "tool": tool, "arguments": arguments, "reason": "smoke"},
        "tool_result": compact,
    }


def collect_key_values(value: Any, key: str) -> list[Any]:
    values: list[Any] = []
    if isinstance(value, dict):
        for item_key, item_value in value.items():
            if item_key == key:
                values.append(item_value)
            values.extend(collect_key_values(item_value, key))
    elif isinstance(value, list):
        for item in value:
            values.extend(collect_key_values(item, key))
    return values


def action_argument_paths(actions: list[dict[str, Any]], tool: str) -> list[str]:
    paths: list[str] = []
    for action in actions:
        if not isinstance(action, dict) or action.get("tool") != tool:
            continue
        args = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
        if isinstance(args.get("path"), str) and args["path"] not in paths:
            paths.append(args["path"])
        for path in args.get("paths") or []:
            if isinstance(path, str) and path not in paths:
                paths.append(path)
    return paths


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="aic-code-product-") as tmp:
        repo_root = Path(tmp).resolve()
        job_root = repo_root / ".job"
        target = "pkg/example.py"
        source = repo_root / target
        source.parent.mkdir(parents=True, exist_ok=True)
        old_text = "def answer():\n    return 1\n"
        new_text = "def answer():\n    return 2\n"
        source.write_text(old_text, encoding="utf-8")
        (repo_root / "pkg/bad.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
        (repo_root / ".gitignore").write_text(".venv/\n", encoding="utf-8")
        (repo_root / "AGENTS.md").write_text("Original agent contract line\n", encoding="utf-8")
        (repo_root / "README.md").write_text("Original readme line\n", encoding="utf-8")
        shared_target = "ia_carmine/_shared/core_runtime.py"
        shared_old = "\n".join(
            [
                '"""Core runtime fixture for planner validator smoke tests."""',
                'CORE_ROLE = "planner validator broker loop"',
                "",
                "class SharedCoreRuntime:",
                "    def __init__(self):",
                "        self.role = CORE_ROLE",
                "",
                "    def planner_entrypoint(self):",
                "        return self.role",
                "",
                "    def validator_gate(self):",
                '        return "scope evidence gate"',
                "",
                "    def broker_loop(self):",
                '        return "agentic broker loop"',
                "",
                "def build_runtime():",
                "    return SharedCoreRuntime()",
                "",
                "def core_signal():",
                '    return "core runtime validator planner"',
                "",
            ]
        )
        shared_new = shared_old.replace(
            '        return "scope evidence gate"',
            '        return "scope evidence gate with read proof"',
        )
        shared_path = repo_root / shared_target
        shared_path.parent.mkdir(parents=True, exist_ok=True)
        shared_path.write_text(shared_old, encoding="utf-8")

        repo_lab_repo_modules = (
            repo_tools,
            repo_code_product_tool,
            repo_list_files_tool,
            repo_read_tool,
        )
        original_repo_tools_roots = {
            module: module.LAB_REPO for module in repo_lab_repo_modules
        }
        original_planner_root = planner.LAB_REPO
        original_native_tools = planner.AGENTIC_PLANNER_NATIVE_TOOLS
        planner_require_native_tools_attr = "AGENTIC_PLANNER_REQUIRE_NATIVE_TOOLS"
        has_require_native_tools = hasattr(planner, planner_require_native_tools_attr)
        original_require_native_tools = getattr(planner, planner_require_native_tools_attr, None)
        for module in repo_lab_repo_modules:
            module.LAB_REPO = repo_root
        planner.LAB_REPO = repo_root
        try:
            planner.AGENTIC_PLANNER_NATIVE_TOOLS = True
            if has_require_native_tools:
                setattr(planner, planner_require_native_tools_attr, True)
            gitignore_goal = "Applica questa patch al file .gitignore"
            require(
                planner._goal_existing_file_candidates(gitignore_goal) == [".gitignore"],
                f"dotfile target resolver missed .gitignore: {planner._goal_existing_file_candidates(gitignore_goal)}",
            )
            require(
                planner._goal_target_file(gitignore_goal) == ".gitignore",
                f"dotfile target resolver did not select .gitignore: {planner._goal_target_file(gitignore_goal)}",
            )
            diff_text = generate_unified_diff_from_texts(
                target_file=target,
                old_text=old_text,
                new_text=new_text,
            )
            require("--- a/pkg/example.py" in diff_text, "difflib unified diff missing fromfile marker")
            require("+++ b/pkg/example.py" in diff_text, "difflib unified diff missing tofile marker")
            require("@@" in diff_text, "difflib unified diff missing hunk marker")
            valid_generated_diff_errors = validate_unified_diff_text(
                unified_diff=diff_text,
                target_file=target,
                require_unidiff=True,
            )
            if importlib.util.find_spec("unidiff") is None:
                require(
                    valid_generated_diff_errors == ["unidiff_dependency_missing"],
                    f"missing unidiff produced unexpected validation errors: {valid_generated_diff_errors}",
                )
            else:
                require(
                    not valid_generated_diff_errors,
                    f"unidiff rejected a valid generated diff: {valid_generated_diff_errors}",
                )
            require(
                "invalid_unified_diff_markers"
                in validate_unified_diff_text(
                    unified_diff="--- a/pkg/example.py\n+++ b/pkg/example.py\n-old\n+new\n",
                    target_file=target,
                    require_unidiff=True,
                ),
                "broken diff was not rejected",
            )

            read_args = {"path": target, "max_chars": 20000}
            read_result = repo_tools.repo_read(read_args, job_root)
            require(read_result.get("ok") is True, "repo_read failed in smoke fixture")
            history_read = [
                compact_history_row(
                    root=job_root,
                    step=1,
                    tool="repo_read",
                    arguments=read_args,
                    result=read_result,
                )
            ]
            docs_read_args = {"paths": ["AGENTS.md", "README.md"], "max_chars": 20000}
            docs_read_result = repo_tools.repo_read(docs_read_args, job_root)
            require(docs_read_result.get("ok") is True, "repo_read docs preseed failed in smoke fixture")
            preseed_docs_row = compact_history_row(
                root=job_root,
                step=0,
                tool="repo_read",
                arguments=docs_read_args,
                result=docs_read_result,
            )
            preseed_docs_row["decision"] = {
                "action": "controller_preseed",
                "tool": "repo_read",
                "arguments": docs_read_args,
                "reason": "loop_start_delta_rag_reindex_ranked_preplanner_context",
            }
            preseed_docs_row["tool_result"]["controller_preseed"] = True
            preseed_docs_row["tool_result"]["preseed_reason"] = "loop_start_delta_rag_reindex_ranked_preplanner_context"
            preseed_docs_row["tool_result"]["preplanner_rag"] = {
                "schema": "agentic_loop_preplanner_rag_preseed.v1",
                "selected_paths": ["AGENTS.md", "README.md"],
                "anchor_paths": [],
                "ranked_preplanner_paths": ["AGENTS.md", "README.md"],
            }
            preseed_docs_row["tool_result"]["selected_paths"] = ["AGENTS.md", "README.md"]
            preseed_docs_row["tool_result"]["ranked_preplanner_paths"] = ["AGENTS.md", "README.md"]
            apply_docs_contract = planner.planner_evidence_contract(
                "Applica patch a AGENTI.md e README.md",
                [preseed_docs_row],
            )
            apply_docs_write_contract = apply_docs_contract.get("apply_write_contract") or {}
            require(
                set(apply_docs_write_contract.get("target_files") or []) == {"AGENTS.md", "README.md"},
                f"apply preloop targets did not resolve AGENTS/README: {apply_docs_write_contract}",
            )
            require(
                set(apply_docs_write_contract.get("verified_target_reads") or []) == {"AGENTS.md", "README.md"},
                f"apply preloop targets were not treated as verified reads: {apply_docs_write_contract}",
            )
            apply_docs_progress = str(apply_docs_contract.get("required_next_progress") or "")
            require(
                "repo_apply_patch" in apply_docs_progress
                and "repo_tree" in apply_docs_progress
                and "do not call" in apply_docs_progress.lower(),
                f"apply preloop progress did not require patch while forbidding discovery: {apply_docs_progress}",
            )
            apply_docs_policy = apply_docs_contract.get("turn_tool_surface_policy") or {}
            require(
                set(apply_docs_policy.get("allowed_tool_names") or []) == {"repo_apply_patch", "repo_read"},
                f"apply preloop surface did not expose patch plus bounded reads: {apply_docs_policy}",
            )
            apply_docs_surface = set(planner._tool_surface_names_for_turn(
                goal="Applica patch a AGENTI.md e README.md",
                evidence_contract=apply_docs_contract,
                intrinsic_context={},
            ))
            require(
                {
                    "repo_apply_patch",
                    "repo_read",
                    "planner_scratchpad_read",
                    "planner_scratchpad_write",
                    "runtime_sqlite_memory_search",
                    "runtime_sqlite_memory_write",
                }.issubset(apply_docs_surface),
                f"apply turn surface is missing essential support tools: {sorted(apply_docs_surface)}",
            )
            unrelated_apply_read_gate = planner.validate_planner_decision_against_evidence(
                "Applica patch a AGENTI.md e README.md",
                {
                    "action": "tool",
                    "tool": "repo_read",
                    "arguments": {"path": target, "max_chars": 20000},
                    "native_tool_call": True,
                    "raw_native_tool_call": {"function": {"name": "repo_read", "arguments": {"path": target, "max_chars": 20000}}},
                    "allowed_tool_names": sorted(apply_docs_surface),
                },
                [preseed_docs_row],
            )
            require(
                "repo_read_outside_apply_write_targets:pkg/example.py" in unrelated_apply_read_gate.get("violations", []),
                f"apply branch accepted unrelated repo_read: {unrelated_apply_read_gate}",
            )
            forbidden_apply_tools = {"repo_tree", "repo_list_files", "repo_search", "repo_semantic_search"}
            require(
                not any(
                    isinstance(item, dict) and item.get("tool") in forbidden_apply_tools
                    for item in apply_docs_contract.get("candidate_next_actions") or []
                ),
                f"apply preloop candidates still exposed discovery: {apply_docs_contract.get('candidate_next_actions')}",
            )
            patch_security_goal = (
                "GENERAZIONE CODICE PATCH EFFETTIVO PER GLI UPGRADE VULKAN_HELPER "
                "applicare patch security hardening a vulkan_helper/core/cache_manager.py"
            )
            require(
                rag_preseed._preplanner_goal_class(patch_security_goal) == "apply_write",
                "preplanner classified explicit patch/apply goal as analysis",
            )
            _, missing_db_ranking, _ = rag_preseed._ranked_paths_from_codex_rag(
                db=repo_root / "missing-rag.sqlite3",
                repo_root=repo_root,
                goal=patch_security_goal,
                query_plan={
                    "queries": [
                        {
                            "query": "vulkan_helper/core/cache_manager.py LRUCache TTL",
                            "purpose": "target patch file",
                        }
                    ]
                },
                safe_rel_path=lambda value: value,
                named_read_priority={},
                generic_readable_suffixes=(".py", ".md", ".json", ".toml"),
                candidate_limit=4,
            )
            query_specs = missing_db_ranking.get("query_specs") or []
            planner_query_specs = [
                item for item in query_specs
                if isinstance(item, dict) and item.get("source") == "planner_query_plan"
            ]
            require(planner_query_specs, f"preplanner RAG query specs missing: {missing_db_ranking}")
            planner_query_terms = planner_query_specs[0].get("query_terms") or []
            require(
                "vulkan_helper" in planner_query_terms and "generazione" not in planner_query_terms,
                f"planner query terms were contaminated by full goal terms: {planner_query_terms}",
            )
            require(
                not any(
                    isinstance(item, dict) and item.get("source") == "deterministic_goal_terms"
                    for item in query_specs
                ),
                f"apply_write preseed still added broad deterministic goal query: {query_specs}",
            )

            tool_manifest = [
                {
                    "name": item["function"]["name"],
                    "description": item["function"]["description"],
                    "parameters": item["function"]["parameters"],
                    "argument_contract": item["function"].get("argument_contract") or {},
                }
                for item in TOOLS_SCHEMA
                if isinstance(item.get("function"), dict)
            ]
            compact_manifest = planner._compact_tool_manifest_for_prompt(tool_manifest)
            native_system_prompt = planner._planner_system_for_current_mode()
            require(
                "non JSON testuale con action=tool" in native_system_prompt,
                "native planner system prompt does not forbid JSON-text tool calls",
            )
            require(
                "L'azione tool nel content non e' consentita in native tool mode" in native_system_prompt,
                "native planner system prompt does not reserve content JSON for final/block only",
            )
            text_tool_gate = planner.validate_planner_decision_against_evidence(
                "Native tool gate smoke",
                {"action": "tool", "tool": "repo_status", "arguments": {}},
                [],
            )
            require(
                "planner_text_tool_call_disallowed_in_native_mode" in text_tool_gate.get("violations", []),
                f"native mode accepted JSON-text tool call: {text_tool_gate}",
            )
            native_empty_tool_call_gate = planner.validate_planner_decision_against_evidence(
                "Native no tool call smoke",
                {
                    "action": "block",
                    "reason": "planner_native_tool_call_required",
                    "controller_synthesized_protocol_block": True,
                    "native_tool_calls_seen": 0,
                },
                [],
            )
            require(
                "planner_native_tool_call_required" in native_empty_tool_call_gate.get("violations", []),
                f"native no-tool-call block was accepted as terminal: {native_empty_tool_call_gate}",
            )
            plain_text_final = planner_turn._native_plain_text_final_decision(
                "Analisi conclusiva con evidenza citata.",
                native_tool_names=["repo_read"],
                prompt_context_continuation_required={},
                stream_meta={},
            )
            require(
                plain_text_final.get("action") == "final"
                and plain_text_final.get("final_answer") == "Analisi conclusiva con evidenza citata."
                and plain_text_final.get("controller_wrapped_plain_text_final") is True,
                f"native plain terminal text was not wrapped as final: {plain_text_final}",
            )
            require(
                planner_turn._looks_like_malformed_native_protocol('{"action":"tool","tool":"repo_status"}'),
                "malformed JSON-text tool protocol was not recognized as protocol-shaped",
            )
            require(
                not planner_turn._looks_like_malformed_native_protocol(
                    "Analisi conclusiva con evidenza citata."
                ),
                "ordinary terminal prose was incorrectly classified as protocol-shaped",
            )
            native_protocol_text_gate = planner.validate_planner_decision_against_evidence(
                "Native malformed protocol smoke",
                {
                    "action": "block",
                    "reason": "planner_native_mode_non_json_output",
                    "controller_synthesized_protocol_block": True,
                    "native_tool_calls_seen": 0,
                    "raw_planner_text": '{"action":"tool","tool":"repo_status"',
                },
                [],
            )
            require(
                "planner_native_mode_non_json_output" in native_protocol_text_gate.get("violations", []),
                f"native malformed protocol output was accepted as terminal: {native_protocol_text_gate}",
            )
            native_tool_gate = planner.validate_planner_decision_against_evidence(
                "Native tool gate smoke",
                {
                    "action": "tool",
                    "tool": "repo_status",
                    "arguments": {},
                    "native_tool_call": True,
                    "raw_native_tool_call": {
                        "function": {
                            "name": "repo_status",
                            "arguments": {},
                        },
                    },
                },
                [],
            )
            require(native_tool_gate.get("ok") is True, f"native tool decision was rejected: {native_tool_gate}")
            spoofed_native_tool_gate = planner.validate_planner_decision_against_evidence(
                "Native tool gate smoke",
                {
                    "action": "tool",
                    "tool": "repo_status",
                    "arguments": {},
                    "native_tool_call": True,
                },
                [],
            )
            require(
                "planner_text_tool_call_disallowed_in_native_mode" in spoofed_native_tool_gate.get("violations", []),
                f"native mode accepted spoofed native_tool_call flag: {spoofed_native_tool_gate}",
            )
            native_history_read = compact_history_row(
                root=job_root,
                step=2,
                tool="repo_read",
                arguments=read_args,
                result=read_result,
            )
            native_history_read["decision"]["native_tool_call"] = True
            native_history_read["decision"]["raw_native_tool_call"] = {
                "id": "call_smoke_repo_read",
                "function": {
                    "name": "repo_read",
                    "arguments": read_args,
                },
            }
            native_history_messages, native_history_report = planner._planner_history_messages_for_ollama(
                [native_history_read],
                root=job_root,
                goal="Native messages smoke",
                window_chars=2500,
                max_chars=20000,
            )
            require(native_history_report.get("included_history_items") == 1, f"native history not included: {native_history_report}")
            require(
                [msg.get("role") for msg in native_history_messages] == ["assistant", "tool"],
                f"native history did not become assistant/tool messages: {native_history_messages}",
            )
            tool_message = json.loads(str(native_history_messages[1].get("content") or "{}"))
            tool_message_schema = tool_message.get("schema")
            if tool_message_schema in {"planner_tool_history_window.v1", "planner_tool_result_message_window.v1"}:
                result_window = tool_message.get("result_window") if isinstance(tool_message.get("result_window"), dict) else {}
                require(result_window.get("document_id"), f"tool history message missing document_id: {tool_message}")
                require("text" in result_window, f"tool history message missing real first window text: {tool_message}")
            else:
                require(
                    tool_message_schema == "planner_tool_history_evidence.v1",
                    f"tool history message used unexpected schema: {tool_message}",
                )
                require(
                    isinstance(tool_message.get("result"), dict) and tool_message["result"].get("tool") == "repo_read",
                    f"bounded tool history evidence missing real result payload: {tool_message}",
                )
                result_window = {}
            planner.AGENTIC_PLANNER_NATIVE_TOOLS = False
            try:
                legacy_optional_windows = planner._optional_context_for_prompt(
                    root=job_root,
                    goal="Native messages smoke",
                    history=[native_history_read],
                    planner_memory={"available": True, "records": [], "record_count": 0},
                    intrinsic_context={"schema": "planner_intrinsic_context.v1"},
                    last_tool_result=native_history_read["tool_result"],
                    compact_mode=True,
                    window_chars=2500,
                )
            finally:
                planner.AGENTIC_PLANNER_NATIVE_TOOLS = True
            legacy_payload_windows = legacy_optional_windows.get("successful_tool_payload_windows") or []
            require(legacy_payload_windows, f"legacy optional context did not create tool payload window: {legacy_optional_windows}")
            legacy_window = legacy_payload_windows[0].get("window") if isinstance(legacy_payload_windows[0], dict) else {}
            if result_window:
                for window_key in ("text", "window_start", "window_end", "has_more_after", "sha256"):
                    require(
                        legacy_window.get(window_key) == result_window.get(window_key),
                        (
                            "native tool message window diverges from legacy SQLite optional "
                            f"window for {window_key}: legacy={legacy_window} native={result_window}"
                        ),
                    )
            optional_native = planner._optional_context_for_prompt(
                root=job_root,
                goal="Native messages smoke",
                history=[native_history_read],
                planner_memory={"available": True, "records": [], "record_count": 0},
                intrinsic_context={"schema": "planner_intrinsic_context.v1"},
                last_tool_result=native_history_read["tool_result"],
                compact_mode=False,
                window_chars=2500,
            )
            require("history_transport" in optional_native, f"native optional context missing transport note: {optional_native}")
            require("history_tail" not in optional_native, f"native optional context still embeds history_tail: {optional_native}")
            require("last_tool_result_digest" not in optional_native, f"native optional context still embeds last tool digest: {optional_native}")
            native_user_payload, native_payload_report = planner._build_planner_user_payload(
                job_id="smoke-native-history-messages",
                state={"goal": "Native messages smoke", "max_steps": 5, "approval_mode": "safe_write_lab"},
                step=3,
                history=[native_history_read],
                tool_manifest=tool_manifest,
                evidence_contract=planner.planner_evidence_contract("Native messages smoke", [native_history_read]),
                planner_memory={"available": True, "records": [], "record_count": 0},
                intrinsic_context={"schema": "planner_intrinsic_context.v1"},
                last_tool_result=native_history_read["tool_result"],
                native_tools_schema=planner._native_tools_schema_for_planner(TOOLS_SCHEMA),
            )
            require(native_payload_report.get("over_budget") is False, f"native user payload over budget: {native_payload_report}")
            require(
                int(native_payload_report.get("extra_prompt_chars") or 0) > 0
                and int((native_payload_report.get("sections") or {}).get("native_tools_schema") or 0) > 0,
                f"native prompt budget does not account for Ollama tools schema: {native_payload_report}",
            )
            require(
                int(native_payload_report.get("native_history_reserve_chars") or 0) >= 6000,
                f"native prompt budget did not reserve space for message history: {native_payload_report}",
            )
            reserved_history_chars = int(native_payload_report.get("native_history_reserve_chars") or 0)
            base_prompt_without_reserved_history = max(
                0,
                int(native_payload_report.get("total_prompt_chars") or 0) - reserved_history_chars,
            )
            actual_history_budget = max(
                0,
                int(planner.AGENTIC_PLANNER_PROMPT_CHAR_BUDGET or 0) - base_prompt_without_reserved_history,
            )
            reserved_history_messages, reserved_history_report = planner._planner_history_messages_for_ollama(
                [native_history_read],
                root=job_root,
                goal="Native messages smoke",
                window_chars=planner._prompt_window_chars(True, 0),
                max_chars=actual_history_budget,
            )
            require(reserved_history_messages, f"native reserved history budget produced no messages: {reserved_history_report}")
            require(
                reserved_history_report.get("included_history_items") == 1,
                f"native reserved history budget skipped the only tool result: {reserved_history_report}",
            )
            bloated_evidence = planner.planner_evidence_contract("Native messages smoke", [native_history_read])
            bloat_budget = max(1, int(planner.AGENTIC_PLANNER_PROMPT_CHAR_BUDGET or 1))
            bloat_reason_chars = max(260, bloat_budget // 40)
            bloat_action_reason_chars = max(220, bloat_budget // 40)
            bloated_evidence["core_discovery_candidates"] = [
                {
                    "path": f"pkg/discovery_{index}.py",
                    "next_tool": "repo_read",
                    "source": "smoke",
                    "rank": index,
                    "reason": "x" * bloat_reason_chars,
                }
                for index in range(80)
            ]
            bloated_evidence["candidate_next_actions"] = [
                {
                    "action": "tool",
                    "tool": "repo_read",
                    "arguments": {"path": f"pkg/discovery_{index}.py"},
                    "reason": "x" * bloat_action_reason_chars,
                }
                for index in range(40)
            ]
            original_compact_ratio = planner.AGENTIC_PLANNER_PROMPT_COMPACT_RATIO
            try:
                planner.AGENTIC_PLANNER_PROMPT_COMPACT_RATIO = 0.20
                bloated_payload, bloated_report = planner._build_planner_user_payload(
                    job_id="smoke-native-bloated-evidence",
                    state={"goal": "Native messages smoke", "max_steps": 5, "approval_mode": "safe_write_lab"},
                    step=4,
                    history=[native_history_read],
                    tool_manifest=tool_manifest,
                    evidence_contract=bloated_evidence,
                    planner_memory={"available": True, "records": [], "record_count": 0},
                    intrinsic_context={"schema": "planner_intrinsic_context.v1"},
                    last_tool_result=native_history_read["tool_result"],
                    native_tools_schema=planner._native_tools_schema_for_planner(TOOLS_SCHEMA),
                )
            finally:
                planner.AGENTIC_PLANNER_PROMPT_COMPACT_RATIO = original_compact_ratio
            bloated_reserve = int(bloated_report.get("native_history_reserve_chars") or 0)
            bloated_without_reserve = int(bloated_report.get("total_prompt_chars_without_native_history_reserve") or 0)
            require(bloated_reserve >= 6000, f"bloated native report lacks history reserve: {bloated_report}")
            require(
                bloated_report.get("compact_mode") is True,
                f"bloated evidence did not enter compact mode: {bloated_report}",
            )
            require(
                bloated_without_reserve <= int(planner.AGENTIC_PLANNER_PROMPT_CHAR_BUDGET or 0),
                f"bloated evidence was not compacted into SQLite before hard budget gate: {bloated_report}",
            )
            bloated_evidence_prompt = bloated_payload.get("evidence_contract") or {}
            full_evidence_window = bloated_evidence_prompt.get("full_evidence_contract_window")
            require(
                isinstance(full_evidence_window, dict)
                and full_evidence_window.get("document_id"),
                f"bloated evidence did not expose SQLite window pointer: {bloated_evidence_prompt}",
            )
            require(
                bloated_evidence_prompt.get("full_contract_sqlite_window_is_hard_gate") is False,
                f"bloated evidence SQLite window became a hard gate again: {bloated_evidence_prompt}",
            )
            if full_evidence_window.get("has_more_after") is True:
                require(
                    isinstance(bloated_evidence_prompt.get("planner_can_request_more_evidence_contract"), dict),
                    f"bloated evidence did not expose optional SQLite continuation: {bloated_evidence_prompt}",
                )
            bloated_history_budget = max(
                0,
                int(planner.AGENTIC_PLANNER_PROMPT_CHAR_BUDGET or 0) - bloated_without_reserve,
            )
            bloated_history_messages, bloated_history_report = planner._planner_history_messages_for_ollama(
                [native_history_read],
                root=job_root,
                goal="Native messages smoke",
                window_chars=planner._prompt_window_chars(True, 0),
                max_chars=bloated_history_budget,
            )
            require(
                bloated_history_messages
                and bloated_history_report.get("included_history_items") == 1,
                f"bloated prompt left no room for real native history message: {bloated_history_report}",
            )
            require(
                bloated_without_reserve + int(bloated_history_report.get("message_chars") or 0)
                <= int(planner.AGENTIC_PLANNER_PROMPT_CHAR_BUDGET or 0),
                f"bloated prompt actual messages exceed budget: report={bloated_report} history={bloated_history_report}",
            )
            native_available_tools = native_user_payload.get("available_tools")
            native_available_tool_rows = (
                native_available_tools
                if isinstance(native_available_tools, list)
                else (native_available_tools.get("summary") if isinstance(native_available_tools, dict) else [])
            )
            require(
                isinstance(native_available_tool_rows, list)
                and native_available_tool_rows
                and all(
                    "argument_contract" not in row and "description" not in row
                    for row in native_available_tool_rows
                    if isinstance(row, dict)
                ),
                (
                    "native user payload still duplicates full tool manifest instead "
                    f"of using tools schema: {native_available_tools}"
                ),
            )
            if isinstance(native_available_tools, dict):
                tools_window = native_available_tools.get("window") if isinstance(native_available_tools.get("window"), dict) else {}
                require(
                    native_available_tools.get("schema") == "planner_available_tools_window.v1"
                    and tools_window.get("document_id")
                    and isinstance(tools_window.get("text"), str)
                    and tools_window.get("full_chars", 0) >= tools_window.get("window_chars", 0),
                    f"windowed native available_tools lacks real consumable window: {native_available_tools}",
                )
            orientation_goal = (
                "Genera un patch diff concreto per il file pkg/example.py "
                "che include refactoring per modularizzazione delle cartellette."
            )
            orientation_plan = planner._controller_file_code_product_orientation_preseed_plan(
                orientation_goal
            )
            require(
                orientation_plan
                and orientation_plan.get("tool") == "repo_tree"
                and orientation_plan.get("dynamic_initial_orientation") is True,
                f"file code-product goal lacks dynamic repo orientation preseed: {orientation_plan}",
            )
            compact_orientation_contract = planner._compact_evidence_contract_for_prompt({
                "initial_orientation_surface": {
                    "schema": "agentic_loop_initial_orientation_surface.v1",
                    "root_tree": {"ok": True, "path": "."},
                    "preseed_steps": [{"tool": "repo_tree", "reason": "smoke"}],
                },
                "candidate_next_actions": [],
            })
            require(
                compact_orientation_contract.get("initial_orientation_surface"),
                f"compact evidence dropped initial_orientation_surface: {compact_orientation_contract}",
            )
            native_response_format = native_user_payload.get("required_response_format") if isinstance(native_user_payload.get("required_response_format"), dict) else {}
            require(
                native_response_format.get("tool_execution") == "message.tool_calls",
                f"native required_response_format does not require message.tool_calls: {native_response_format}",
            )
            require(
                native_response_format.get("textual_tool_action_allowed") is False,
                f"native required_response_format still allows textual tool action: {native_response_format}",
            )
            require(
                native_response_format.get("allowed_content_actions") == ["final", "block"],
                f"native content actions are not final/block only: {native_response_format}",
            )
            batch_candidates = [
                {
                    "action": "tool",
                    "tool": "repo_read",
                    "arguments": {"path": target, "max_chars": 20000},
                    "reason": "read primary target",
                    "source": "smoke",
                    "action_id": "smoke-read-primary",
                },
                {
                    "action": "tool",
                    "tool": "repo_read",
                    "arguments": {"path": shared_target, "max_chars": 20000},
                    "reason": "read shared target",
                    "source": "smoke",
                    "action_id": "smoke-read-shared",
                },
                {
                    "action": "tool",
                    "tool": "repo_apply_patch",
                    "arguments": {"path": target, "old_text": old_text, "new_text": new_text},
                    "reason": "write must not be batched",
                    "source": "smoke",
                    "action_id": "smoke-write",
                },
            ]
            micro_batch_contract = evidence_builder._micro_batch_contract_from_candidates(batch_candidates)
            require(
                micro_batch_contract.get("allowed") is True
                and micro_batch_contract.get("batchable_candidate_count") == 2,
                f"micro batch contract did not allow two read-only candidates: {micro_batch_contract}",
            )
            require(
                all(item.get("tool") == "repo_read" for item in micro_batch_contract.get("allowed_batch_actions") or []),
                f"micro batch contract allowed non-read/write candidate: {micro_batch_contract}",
            )
            compact_micro_contract = planner._compact_evidence_contract_for_prompt({
                "candidate_next_actions": batch_candidates,
                "micro_batch_contract": micro_batch_contract,
            })
            require(
                (compact_micro_contract.get("micro_batch_contract") or {}).get("allowed") is True,
                f"compact evidence dropped micro_batch_contract: {compact_micro_contract}",
            )
            batch_prompt_contract = planner.planner_evidence_contract("Native batch smoke", [native_history_read])
            batch_prompt_contract["candidate_next_actions"] = batch_candidates
            batch_prompt_contract["micro_batch_contract"] = micro_batch_contract
            native_batch_payload, _native_batch_report = planner._build_planner_user_payload(
                job_id="smoke-native-batch-contract",
                state={"goal": "Native batch smoke", "max_steps": 5, "approval_mode": "safe_write_lab"},
                step=3,
                history=[native_history_read],
                tool_manifest=tool_manifest,
                evidence_contract=batch_prompt_contract,
                planner_memory={"available": True, "records": [], "record_count": 0},
                intrinsic_context={"schema": "planner_intrinsic_context.v1"},
                last_tool_result=native_history_read["tool_result"],
                native_tools_schema=planner._native_tools_schema_for_planner(TOOLS_SCHEMA),
            )
            native_batch_response_format = native_batch_payload.get("required_response_format") or {}
            require(
                native_batch_response_format.get("native_tool_batch_allowed") is True
                and native_batch_response_format.get("native_tool_batch_max_size") == 2,
                f"native prompt did not expose batch contract: {native_batch_response_format}",
            )
            require(
                (native_batch_payload.get("evidence_contract") or {}).get("micro_batch_contract"),
                f"native prompt evidence contract dropped micro batch contract: {native_batch_payload.get('evidence_contract')}",
            )
            batch_history_rows = [
                {
                    "step": 9,
                    "substep": 1,
                    "decision": {
                        "action": "tool",
                        "tool": "repo_status",
                        "arguments": {},
                        "reason": "native_tool_call_batch",
                        "native_tool_call": True,
                    },
                    "tool_result": {"tool": "repo_status", "ok": True},
                },
                {
                    "step": 9,
                    "substep": 2,
                    "decision": {
                        "action": "tool",
                        "tool": "repo_tree",
                        "arguments": {"path": ".", "max_depth": 1},
                        "reason": "native_tool_call_batch",
                        "native_tool_call": True,
                    },
                    "tool_result": {"tool": "repo_tree", "ok": True, "path": ".", "entries": []},
                },
            ]
            batch_diagnostics = planner._agent_flow_diagnostics("Native batch smoke", batch_history_rows)
            require(
                batch_diagnostics.get("native_tool_batch_executed") == 1
                and batch_diagnostics.get("native_tool_batch_substeps") == 2,
                f"native batch diagnostics did not count substep rows: {batch_diagnostics}",
            )
            public_limits = planner._public_tool_context_limits([
                {
                    "producer_step": 9,
                    "substep": 2,
                    "tool": "repo_list_files",
                    "ok": True,
                    "artifact": {
                        "kind": "repo_list_files",
                        "repo_path": "pkg",
                        "count": 1,
                        "total_matches": 3,
                    },
                }
            ])
            require(
                public_limits
                and public_limits[0].get("substep") == 2
                and public_limits[0].get("kind") == "partial_list",
                f"public tool context limits lost substep: {public_limits}",
            )
            require(
                "allowed_actions" not in native_response_format or "tool" not in native_response_format.get("allowed_actions", []),
                f"native required_response_format still advertises JSON tool action: {native_response_format}",
            )
            native_shape_examples = native_user_payload.get("tool_shape_examples") if isinstance(native_user_payload.get("tool_shape_examples"), dict) else {}
            native_shape_window = (
                native_shape_examples.get("serialized_json_window")
                if isinstance(native_shape_examples.get("serialized_json_window"), dict)
                else {}
            )
            native_shape_text = (
                str(native_shape_window.get("text") or "")
                if native_shape_window
                else json.dumps(native_shape_examples, ensure_ascii=False, separators=(",", ":"), default=str)
            )
            require(
                native_shape_examples.get("transport") == "native_tool_calls"
                or '"transport": "native_tool_calls"' in native_shape_text
                or '"transport":"native_tool_calls"' in native_shape_text,
                f"native tool shape examples are not native-specific: {native_shape_examples}",
            )
            require(
                '"action":"tool"' not in native_shape_text and '"action": "tool"' not in native_shape_text,
                f"native tool shape examples still expose JSON action=tool: {native_shape_examples}",
            )
            require(
                (
                    "sqlite_prompt_context_window_read_native_tool_call" in native_shape_text
                    and '"transport":"message.tool_calls"' in native_shape_text
                )
                or isinstance(native_shape_examples.get("planner_can_request_more"), dict),
                f"native tool shape examples lack SQL/window native call guidance: {native_shape_examples}",
            )
            native_system_text = planner._planner_system_for_current_mode()
            require(
                '{"action":"tool"' not in native_system_text and '{"action": "tool"' not in native_system_text,
                "native planner system prompt still contains JSON action=tool examples",
            )
            if has_require_native_tools:
                setattr(planner, planner_require_native_tools_attr, False)
            native_text_tool_gate_without_require = planner.validate_planner_decision_against_evidence(
                "Native tool gate smoke",
                {"action": "tool", "tool": "repo_status", "arguments": {}},
                [],
            )
            native_tool_gate_suffix = (
                f" when {planner_require_native_tools_attr}=false"
                if has_require_native_tools
                else ""
            )
            require(
                "planner_text_tool_call_disallowed_in_native_mode"
                in native_text_tool_gate_without_require.get("violations", []),
                (
                    "native mode accepted JSON-text tool call"
                    f"{native_tool_gate_suffix}: {native_text_tool_gate_without_require}"
                ),
            )
            planner.AGENTIC_PLANNER_NATIVE_TOOLS = False
            manifest_by_name = {
                str(item.get("name")): item
                for item in compact_manifest
                if isinstance(item, dict) and item.get("name")
            }
            required_contract_expectations = {
                "repo_search": "repo_search_missing_query_pattern_or_symbol",
                "repo_read": "repo_read_missing_path_or_paths_items",
                "repo_propose_code_edit": "repo_propose_code_edit_missing_unified_diff",
                "planner_scratchpad_write": "planner_scratchpad_write_missing_text",
                "planner_scratchpad_read": "planner_scratchpad_read_missing_selector",
                "runtime_sqlite_memory_search": "runtime_sqlite_memory_search_missing_query_tag_or_kind",
                "runtime_sqlite_memory_write": "runtime_sqlite_memory_write_missing_text",
                "terminal_search_files": "terminal_search_files_missing_query",
                "terminal_run_command_wait": "terminal_run_command_wait_missing_command",
                "repo_command": "repo_command_missing_command",
            }
            for tool_name, violation in required_contract_expectations.items():
                row = manifest_by_name.get(tool_name) or {}
                contract_row = row.get("argument_contract") if isinstance(row.get("argument_contract"), dict) else {}
                require(contract_row, f"{tool_name} missing argument_contract in compact manifest")
                require(
                    violation in json.dumps(contract_row, ensure_ascii=False, sort_keys=True),
                    f"{tool_name} argument_contract missing validator violation {violation}: {contract_row}",
                )
            described_requires_without_contract = [
                row.get("name")
                for row in compact_manifest
                if isinstance(row, dict)
                and "Requires " in str(row.get("description") or "")
                and not row.get("argument_contract")
            ]
            require(
                not described_requires_without_contract,
                f"tools with Requires description lack argument_contract: {described_requires_without_contract}",
            )
            native_tools_schema = planner._native_tools_schema_for_planner(TOOLS_SCHEMA)
            require(
                not any(
                    isinstance(item.get("function"), dict)
                    and "argument_contract" in item["function"]
                    for item in native_tools_schema
                    if isinstance(item, dict)
                ),
                "native tools schema leaked non-standard argument_contract field",
            )
            repo_search_native = next(
                item["function"]
                for item in native_tools_schema
                if isinstance(item.get("function"), dict)
                and item["function"].get("name") == "repo_search"
            )
            require(
                bool((repo_search_native.get("parameters") or {}).get("anyOf")),
                "native repo_search schema lost one-of required contract",
            )
            repo_propose_native = next(
                item["function"]
                for item in native_tools_schema
                if isinstance(item.get("function"), dict)
                and item["function"].get("name") == "repo_propose_code_edit"
            )
            require(
                "Internal argument contract:" not in str(repo_propose_native.get("description") or ""),
                "native repo_propose_code_edit schema leaked long operational argument contract description",
            )
            require(
                "conditional_required" not in str(repo_propose_native.get("description") or ""),
                "native repo_propose_code_edit schema leaked conditional_required guidance into provider description",
            )
            require(
                "source_requirements" not in str(repo_propose_native.get("description") or ""),
                "native repo_propose_code_edit schema leaked source_requirements guidance into provider description",
            )
            propose_contract = (manifest_by_name.get("repo_propose_code_edit") or {}).get("argument_contract") or {}
            scratch_read_contract = (manifest_by_name.get("planner_scratchpad_read") or {}).get("argument_contract") or {}
            scratch_write_contract = (manifest_by_name.get("planner_scratchpad_write") or {}).get("argument_contract") or {}
            require(
                "shape_examples" in propose_contract and "source_requirements" in propose_contract,
                f"repo_propose_code_edit manifest lacks non-runnable source guidance: {propose_contract}",
            )
            require(
                "sqlite_window_contract" in scratch_read_contract and "shape_examples" in scratch_read_contract,
                f"planner_scratchpad_read manifest lacks SQL/window guidance: {scratch_read_contract}",
            )
            require(
                "shape_examples" in scratch_write_contract,
                f"planner_scratchpad_write manifest lacks code_product_build_state shape guidance: {scratch_write_contract}",
            )

            validator_goal = "Validator contract smoke"
            validator_cases = [
                ("repo_search", {}, "repo_search_missing_query_pattern_or_symbol"),
                ("repo_read", {}, "repo_read_missing_path_or_paths_items"),
                ("planner_scratchpad_write", {"kind": "note"}, "planner_scratchpad_write_missing_text"),
                ("planner_scratchpad_read", {}, "planner_scratchpad_read_missing_selector"),
                ("runtime_sqlite_memory_write", {}, "runtime_sqlite_memory_write_missing_text"),
                ("runtime_sqlite_memory_search", {}, "runtime_sqlite_memory_search_missing_query_tag_or_kind"),
                ("terminal_search_files", {}, "terminal_search_files_missing_query"),
                ("terminal_run_command_wait", {}, "terminal_run_command_wait_missing_command"),
                ("repo_command", {}, "repo_command_missing_command"),
            ]
            for tool_name, arguments, expected_violation in validator_cases:
                gate = planner.validate_planner_decision_against_evidence(
                    validator_goal,
                    {"action": "tool", "tool": tool_name, "arguments": arguments},
                    [],
                )
                require(
                    expected_violation in gate.get("violations", []),
                    f"{tool_name} did not reject missing required arguments with {expected_violation}: {gate}",
                )
            for tool_name in ("repo_capabilities", "repo_status"):
                gate = planner.validate_planner_decision_against_evidence(
                    validator_goal,
                    {"action": "tool", "tool": tool_name, "arguments": {}},
                    [],
                )
                require(gate.get("ok") is True, f"{tool_name} unexpectedly rejected empty arguments: {gate}")
            code_product_validator_goal = f"Generate a detailed code diff for {target}"
            apply_validator_goal = f"Apply a patch to {target}"
            no_op_payload_gate = planner.validate_planner_decision_against_evidence(
                code_product_validator_goal,
                {
                    "action": "tool",
                    "tool": "repo_propose_code_edit",
                    "arguments": {
                        "target_file": target,
                        "edit_kind": "no_op",
                        "rationale": "No code change is needed.",
                        "old_text": old_text,
                    },
                },
                [],
            )
            require(
                "repo_propose_code_edit_no_op_has_patch_payload" in no_op_payload_gate.get("violations", []),
                f"no_op with patch payload was not rejected: {no_op_payload_gate}",
            )
            placeholder_decision = {
                "action": "tool",
                "tool": "repo_propose_code_edit",
                "arguments": {
                    "target_file": target,
                    "edit_kind": "unified_diff",
                    "rationale": "Placeholder smoke",
                    "old_text": "<insert old text here>",
                    "new_text": "replacement",
                },
            }
            placeholder_gate = planner.validate_planner_decision_against_evidence(
                code_product_validator_goal,
                placeholder_decision,
                history_read,
            )
            require(
                "repo_propose_code_edit_placeholder_text" in placeholder_gate.get("violations", []),
                f"repo_propose_code_edit placeholder was not rejected: {placeholder_gate}",
            )
            paste_placeholder_decision = {
                "action": "tool",
                "tool": "repo_propose_code_edit",
                "arguments": {
                    "target_file": target,
                    "edit_kind": "unified_diff",
                    "rationale": "Placeholder smoke",
                    "old_text": "<paste the old text here>",
                    "new_text": "<paste the new text here>",
                },
            }
            paste_placeholder_gate = planner.validate_planner_decision_against_evidence(
                code_product_validator_goal,
                paste_placeholder_decision,
                history_read,
            )
            require(
                "repo_propose_code_edit_placeholder_text" in paste_placeholder_gate.get("violations", []),
                f"repo_propose_code_edit paste placeholder was not rejected: {paste_placeholder_gate}",
            )
            example_gate = planner.validate_planner_decision_against_evidence(
                code_product_validator_goal,
                {
                    "action": "tool",
                    "tool": "repo_propose_code_edit",
                    "arguments": {
                        "target_file": target,
                        "edit_kind": "unified_diff",
                        "rationale": "Example smoke",
                        "old_text": "EXAMPLE_ONLY_DO_NOT_COPY",
                        "new_text": "replacement",
                    },
                },
                history_read,
            )
            require(
                "repo_propose_code_edit_placeholder_text" in example_gate.get("violations", []),
                f"repo_propose_code_edit EXAMPLE_ONLY old_text was not rejected: {example_gate}",
            )
            old_phrase_gate = planner.validate_planner_decision_against_evidence(
                code_product_validator_goal,
                {
                    "action": "tool",
                    "tool": "repo_propose_code_edit",
                    "arguments": {
                        "target_file": target,
                        "edit_kind": "unified_diff",
                        "rationale": "Example smoke",
                        "old_text": "old phrase",
                        "new_text": "replacement",
                    },
                },
                history_read,
            )
            require(
                "repo_propose_code_edit_placeholder_text" in old_phrase_gate.get("violations", []),
                f"repo_propose_code_edit old phrase was not rejected: {old_phrase_gate}",
            )
            missing_old_gate = planner.validate_planner_decision_against_evidence(
                code_product_validator_goal,
                {
                    "action": "tool",
                    "tool": "repo_propose_code_edit",
                    "arguments": {
                        "target_file": target,
                        "edit_kind": "unified_diff",
                        "rationale": "Missing old text smoke",
                        "old_text": "def missing_anchor():\n    return 999\n",
                        "new_text": "def missing_anchor():\n    return 1000\n",
                    },
                },
                history_read,
            )
            require(
                "repo_propose_code_edit_old_text_not_from_verified_read" in missing_old_gate.get("violations", []),
                f"repo_propose_code_edit old_text outside repo_read was not rejected: {missing_old_gate}",
            )
            valid_old_gate = planner.validate_planner_decision_against_evidence(
                code_product_validator_goal,
                {
                    "action": "tool",
                    "tool": "repo_propose_code_edit",
                    "arguments": {
                        "target_file": target,
                        "edit_kind": "unified_diff",
                        "rationale": "Verified old_text smoke",
                        "old_text": old_text,
                        "new_text": new_text,
                    },
                },
                history_read,
            )
            require(valid_old_gate.get("ok") is True, f"verified old_text was rejected: {valid_old_gate}")
            apply_placeholder_gate = planner.validate_planner_decision_against_evidence(
                apply_validator_goal,
                {
                    "action": "tool",
                    "tool": "repo_apply_patch",
                    "arguments": {"path": target, "old_text": "old phrase", "new_text": new_text},
                },
                history_read,
            )
            require(
                "repo_apply_patch_placeholder_text" in apply_placeholder_gate.get("violations", []),
                f"repo_apply_patch placeholder old_text was not rejected: {apply_placeholder_gate}",
            )
            apply_missing_old_decision = {
                "action": "tool",
                "tool": "repo_apply_patch",
                "arguments": {"path": target, "old_text": "not present in verified read", "new_text": new_text},
            }
            apply_missing_old_gate = planner.validate_planner_decision_against_evidence(
                apply_validator_goal,
                apply_missing_old_decision,
                history_read,
            )
            require(
                "repo_apply_patch_old_text_not_from_verified_read" in apply_missing_old_gate.get("violations", []),
                f"repo_apply_patch old_text outside repo_read was not rejected: {apply_missing_old_gate}",
            )
            require(
                planner.planner_cuda_rewrite_target(
                    apply_missing_old_gate,
                    apply_missing_old_decision,
                ) == "repo_apply_patch",
                f"repo_apply_patch old_text rejection did not request planner CUDA rewrite: {apply_missing_old_gate}",
            )
            apply_rewrite_guard = planner.planner_cuda_rewrite_guard_for_validation(
                apply_missing_old_gate,
                apply_missing_old_decision,
            )
            require(
                apply_rewrite_guard.get("guard_type") == "planner_cuda_rewrite_required",
                f"apply rewrite guard had wrong guard_type: {apply_rewrite_guard}",
            )
            require(
                apply_rewrite_guard.get("rewrite_lane") == "planner_cuda"
                and apply_rewrite_guard.get("rewrite_target") == "repo_apply_patch",
                f"apply rewrite guard did not target planner CUDA repo_apply_patch: {apply_rewrite_guard}",
            )
            require(
                "old_text must be an exact substring" in str(apply_rewrite_guard.get("next_instruction") or ""),
                f"apply rewrite guard did not instruct exact old_text rewrite: {apply_rewrite_guard}",
            )
            require(
                not planner._should_attempt_vulkan_repair(
                    apply_missing_old_decision,
                    apply_missing_old_gate,
                    history_read,
                ),
                "repo_apply_patch semantic validation failure was routed to Vulkan/GPU0 repair",
            )
            apply_result = {
                "ok": True,
                "tool": "repo_apply_patch",
                "path": target,
                "modified_paths": [target],
                "changed": True,
                "replacements": 1,
                "line_count_before": len(old_text.splitlines()),
                "line_count_after": len(new_text.splitlines()),
                "before_sha256": "before-smoke",
                "after_sha256": "after-smoke",
            }
            history_after_apply = history_read + [
                compact_history_row(
                    root=job_root,
                    step=2,
                    tool="repo_apply_patch",
                    arguments={"path": target, "old_text": old_text, "new_text": new_text},
                    result=apply_result,
                )
            ]
            post_apply_contract = planner.planner_evidence_contract(
                apply_validator_goal,
                history_after_apply,
            )
            post_write_contract = post_apply_contract.get("post_write_validation_contract") or {}
            require(
                post_write_contract.get("status") == "pending"
                and post_write_contract.get("validation_done") is False,
                f"post-write validation contract did not enter pending state: {post_write_contract}",
            )
            require(
                post_apply_contract.get("finalization_contract", {}).get("final_allowed") is False,
                f"post-write contract allowed final without validation: {post_apply_contract.get('finalization_contract')}",
            )
            post_apply_candidates = post_apply_contract.get("candidate_next_actions") or []
            require(
                any(
                    isinstance(item, dict)
                    and item.get("tool") == "repo_validate"
                    and target in ((item.get("arguments") or {}).get("paths") or [])
                    for item in post_apply_candidates
                ),
                f"post-write validation candidate missing targeted repo_validate: {post_apply_candidates}",
            )
            post_apply_policy = post_apply_contract.get("turn_tool_surface_policy") or {}
            require(
                post_apply_policy.get("reason") == "post_write_validation_required"
                and "repo_validate" in set(post_apply_policy.get("allowed_tool_names") or []),
                f"post-write policy did not require validation: {post_apply_policy}",
            )
            missing_validation_final_gate = planner.validate_planner_decision_against_evidence(
                apply_validator_goal,
                {"action": "final", "final_answer": "Patch applied."},
                history_after_apply,
            )
            require(
                "final_after_write_without_validation" in missing_validation_final_gate.get("violations", []),
                f"final without post-write validation was not rejected: {missing_validation_final_gate}",
            )
            failed_validation_result = {
                "ok": False,
                "tool": "repo_validate",
                "paths": [target],
                "results": [{
                    "index": 1,
                    "command": "python -m compileall -q 'pkg/example.py'",
                    "returncode": 1,
                    "ok": False,
                    "stderr_tail": "smoke failure",
                }],
            }
            history_after_failed_validation = history_after_apply + [
                compact_history_row(
                    root=job_root,
                    step=3,
                    tool="repo_validate",
                    arguments={"paths": [target]},
                    result=failed_validation_result,
                )
            ]
            failed_validation_final_gate = planner.validate_planner_decision_against_evidence(
                apply_validator_goal,
                {"action": "final", "final_answer": "Patch applied."},
                history_after_failed_validation,
            )
            require(
                "final_after_write_validation_failed" in failed_validation_final_gate.get("violations", []),
                f"final after failed post-write validation was not rejected: {failed_validation_final_gate}",
            )
            successful_validation_result = {
                "ok": True,
                "tool": "repo_validate",
                "paths": [target],
                "results": [{
                    "index": 1,
                    "command": "python -m compileall -q 'pkg/example.py'",
                    "returncode": 0,
                    "ok": True,
                }],
            }
            history_after_successful_validation = history_after_apply + [
                compact_history_row(
                    root=job_root,
                    step=4,
                    tool="repo_validate",
                    arguments={"paths": [target]},
                    result=successful_validation_result,
                )
            ]
            successful_validation_contract = planner.planner_evidence_contract(
                apply_validator_goal,
                history_after_successful_validation,
            )
            require(
                (successful_validation_contract.get("post_write_validation_contract") or {}).get("status") == "passed",
                "successful post-write validation did not mark the contract passed",
            )
            successful_validation_final_gate = planner.validate_planner_decision_against_evidence(
                apply_validator_goal,
                {"action": "final", "final_answer": "Patch applied and validation passed."},
                history_after_successful_validation,
            )
            require(
                successful_validation_final_gate.get("ok") is True,
                f"final after successful post-write validation was rejected: {successful_validation_final_gate}",
            )
            apply_duplicate_read_gate = planner.validate_planner_decision_against_evidence(
                apply_validator_goal,
                {
                    "action": "tool",
                    "tool": "repo_read",
                    "arguments": read_args,
                    "native_tool_call": True,
                    "raw_native_tool_call": {"function": {"name": "repo_read", "arguments": read_args}},
                },
                history_read,
            )
            require(
                "repo_read_window_already_successful_without_progress" in apply_duplicate_read_gate.get("violations", []),
                f"duplicate repo_read was not rejected for apply goal: {apply_duplicate_read_gate}",
            )
            apply_duplicate_contract = apply_duplicate_read_gate.get("evidence_contract") or {}
            apply_duplicate_progress = str(apply_duplicate_contract.get("required_next_progress") or "")
            require(
                "repo_apply_patch" in apply_duplicate_progress
                and "repo_propose_code_edit" not in apply_duplicate_progress
                and "code_product_build_state" not in apply_duplicate_progress,
                f"apply duplicate-read replan routed to code-product wording: {apply_duplicate_progress}",
            )
            apply_duplicate_candidates = apply_duplicate_contract.get("candidate_next_actions") or []
            require(
                not any(
                    isinstance(item, dict) and item.get("tool") == "planner_scratchpad_write"
                    for item in apply_duplicate_candidates
                ),
                f"apply duplicate-read replan exposed build-state scratchpad write: {apply_duplicate_candidates}",
            )
            repeat_placeholder_gate = planner.validate_planner_decision_against_evidence(
                code_product_validator_goal,
                placeholder_decision,
                history_read + [
                    {
                        "step": 2,
                        "decision": placeholder_decision,
                        "tool_result": {
                            "tool": "controller_guard",
                            "ok": True,
                            "guard_type": "planner_decision_validation",
                            "violations": ["repo_propose_code_edit_placeholder_text"],
                        },
                    }
                ],
            )
            require(
                "code_product_route_shift_required" in repeat_placeholder_gate.get("violations", []),
                f"repeated placeholder proposal did not force route shift: {repeat_placeholder_gate}",
            )
            repeat_contract = repeat_placeholder_gate.get("evidence_contract") or {}
            disallowed_signatures = repeat_contract.get("disallowed_next_decision_signatures") or []
            require(
                disallowed_signatures,
                f"second identical placeholder did not expose disallowed_next_decision_signatures: {repeat_placeholder_gate}",
            )
            repeat_candidates = [
                item for item in repeat_contract.get("candidate_next_actions") or []
                if isinstance(item, dict)
            ]
            require(
                not any(
                    item.get("tool") == "repo_propose_code_edit"
                    and not planner._code_product_action_has_complete_payload(item)
                    for item in repeat_candidates
                ),
                f"placeholder route exposed incomplete repo_propose_code_edit candidate: {repeat_candidates}",
            )
            repeated_placeholder_history = history_read + [
                {
                    "step": 2,
                    "decision": {"action": "continue_required", "reason": "rejected placeholder"},
                    "tool_result": {
                        "tool": "controller_guard",
                        "ok": True,
                        "guard_type": "planner_decision_validation",
                        "violations": ["repo_propose_code_edit_placeholder_text"],
                        "rejected_decision": paste_placeholder_decision,
                    },
                },
                {
                    "step": 3,
                    "decision": {"action": "continue_required", "reason": "rejected placeholder again"},
                    "tool_result": {
                        "tool": "controller_guard",
                        "ok": True,
                        "guard_type": "planner_decision_validation",
                        "violations": [
                            "repo_propose_code_edit_placeholder_text",
                            "code_product_route_shift_required",
                        ],
                        "rejected_decision": paste_placeholder_decision,
                    },
                },
            ]
            terminal_placeholder_gate = planner.validate_planner_decision_against_evidence(
                code_product_validator_goal,
                paste_placeholder_decision,
                repeated_placeholder_history,
            )
            require(
                "planner_repeated_invalid_code_product_decision" in terminal_placeholder_gate.get("violations", []),
                f"third identical placeholder did not become typed blocker: {terminal_placeholder_gate}",
            )
            require(
                terminal_placeholder_gate.get("invalid_decision_repeat_count") == 3,
                f"terminal placeholder repeat count should be 3: {terminal_placeholder_gate}",
            )
            valid_after_placeholder_history = planner.validate_planner_decision_against_evidence(
                code_product_validator_goal,
                {
                    "action": "tool",
                    "tool": "repo_propose_code_edit",
                    "arguments": {
                        "target_file": target,
                        "edit_kind": "unified_diff",
                        "rationale": "Verified old_text smoke after placeholder loop",
                        "old_text": old_text,
                        "new_text": new_text,
                    },
                },
                repeated_placeholder_history,
            )
            require(
                valid_after_placeholder_history.get("ok") is True,
                f"different valid repo_propose_code_edit was blocked by placeholder signature: {valid_after_placeholder_history}",
            )

            goal = "Generate a detailed code diff for pkg/example.py"
            prose_only = planner.validate_planner_decision_against_evidence(
                goal,
                {"action": "final", "final_answer": "Here is the idea in prose only."},
                history_read,
            )
            require(
                "missing_code_product_candidate" in prose_only.get("violations", []),
                "prose-only final did not trip missing_code_product_candidate",
            )
            require(
                planner.planner_cuda_rewrite_target(
                    prose_only,
                    {"action": "final", "final_answer": "Here is the idea in prose only."},
                ) == "final",
                f"prose-only final rejection did not request planner CUDA rewrite: {prose_only}",
            )
            final_rewrite_guard = planner.planner_cuda_rewrite_guard_for_validation(
                prose_only,
                {"action": "final", "final_answer": "Here is the idea in prose only."},
            )
            require(
                final_rewrite_guard.get("rewrite_lane") == "planner_cuda"
                and final_rewrite_guard.get("rewrite_target") == "final",
                f"final rewrite guard did not target planner CUDA final rewrite: {final_rewrite_guard}",
            )
            require(
                "Rewrite the final response" in str(final_rewrite_guard.get("next_instruction") or ""),
                f"final rewrite guard did not instruct final rewrite: {final_rewrite_guard}",
            )
            missing_contract = planner.planner_evidence_contract(goal, history_read)
            prompt_payload, _prompt_report = planner._build_planner_user_payload(
                job_id="smoke-tool-shape-examples",
                state={"goal": goal, "max_steps": 4, "approval_mode": None},
                step=2,
                history=history_read,
                tool_manifest=tool_manifest,
                evidence_contract=missing_contract,
                planner_memory={},
                intrinsic_context={},
                last_tool_result={},
            )
            prompt_text = json.dumps(prompt_payload, ensure_ascii=False, separators=(",", ":"), default=str)
            system_text = planner._planner_system_for_current_mode()
            combined_prompt_text = prompt_text + "\n" + system_text
            forbidden_prompt_examples = [
                "README.md",
                "old phrase",
                "new phrase",
                "-old",
                "+new",
                "<insert",
                '"query":"pattern"',
                '"query": "pattern"',
                "Complete validated answer section",
            ]
            for forbidden in forbidden_prompt_examples:
                require(
                    forbidden not in combined_prompt_text,
                    f"copyable prompt example still present: {forbidden}",
                )
            def iter_strings(value):
                if isinstance(value, str):
                    yield value
                elif isinstance(value, dict):
                    for sub in value.values():
                        yield from iter_strings(sub)
                elif isinstance(value, list):
                    for sub in value:
                        yield from iter_strings(sub)

            copyable_prompt_context_ids = [
                value for value in iter_strings(prompt_payload.get("tool_shape_examples") or {})
                if value.startswith("prompt-context-")
            ]
            require(
                not copyable_prompt_context_ids,
                f"copyable prompt-context document_id still present in tool shape examples: {copyable_prompt_context_ids}",
            )
            require(
                "EXAMPLE_ONLY_DO_NOT_COPY" in combined_prompt_text,
                "non-runnable EXAMPLE_ONLY_DO_NOT_COPY guidance missing from planner prompt",
            )
            require(
                "sqlite_prompt_context_window_read" in prompt_text
                and "code_product_build_state_write" in prompt_text,
                f"planner prompt lacks parallel SQL/window shape examples: {prompt_payload.get('tool_shape_examples')}",
            )
            final_contract = missing_contract.get("finalization_contract") or {}
            require(final_contract.get("final_allowed") is False, "code-product contract allowed final before proposal")
            require(
                missing_contract.get("planner_may_choose_final") is False,
                "code-product contract allowed planner final before proposal",
            )
            require(
                "repo_propose_code_edit" in str(missing_contract.get("required_next_progress") or ""),
                "code-product contract did not require repo_propose_code_edit as next progress",
            )
            proposal_candidates = [
                item for item in missing_contract.get("candidate_next_actions") or []
                if isinstance(item, dict) and item.get("tool") == "repo_propose_code_edit"
            ]
            require(
                not any(not planner._code_product_action_has_complete_payload(item) for item in proposal_candidates),
                f"code-product contract exposed incomplete repo_propose_code_edit candidate: {proposal_candidates}",
            )
            exact_goal = (
                "Generate a detailed complete unified code diff for refactoring pkg/example.py.\n"
                "Do not apply the patch; produce a report-only code product.\n"
                "Target file: pkg/example.py\n"
                "Exact old_text:\n"
                "def answer():\n"
                "    return 1\n"
                "Exact new_text:\n"
                "def answer():\n"
                "    return 2\n"
                "Required behavior: read the target with repo_read, then call repo_propose_code_edit."
            )
            exact_contract = planner.planner_evidence_contract(exact_goal, history_read)
            exact_candidates = [
                item for item in exact_contract.get("candidate_next_actions") or []
                if isinstance(item, dict) and item.get("tool") == "repo_propose_code_edit"
            ]
            require(exact_candidates, "exact old_text/new_text goal lacks repo_propose_code_edit candidate")
            exact_args = exact_candidates[0].get("arguments") or {}
            require(exact_args.get("old_text") == old_text.rstrip("\n"), f"candidate old_text not copied from goal: {exact_args}")
            require(exact_args.get("new_text") == new_text.rstrip("\n"), f"candidate new_text not copied from goal: {exact_args}")
            exact_gate = planner.validate_planner_decision_against_evidence(
                exact_goal,
                {"action": "tool", "tool": "repo_propose_code_edit", "arguments": exact_args},
                history_read,
            )
            require(exact_gate.get("ok") is True, f"concrete candidate from exact goal was rejected: {exact_gate}")
            repeated_rejections = [
                {
                    "step": i,
                    "guard_type": "planner_decision_validation",
                    "summary": "planner_decision_validation_failed: repo_propose_code_edit_missing_unified_diff",
                    "violations": ["repo_propose_code_edit_missing_unified_diff"],
                    "rejected_decision": {
                        "action": "tool",
                        "tool": "repo_propose_code_edit",
                        "arguments": {
                            "target_file": target,
                            "edit_kind": "unified_diff",
                            "rationale": "missing diff",
                        },
                    },
                }
                for i in range(1, 8)
            ]
            compact_rejections = planner._compact_validation_rejections_tail(repeated_rejections, limit=5)
            require(len(compact_rejections) == 1, f"identical validation rejections were not compacted: {compact_rejections}")
            require(
                compact_rejections[0].get("repeat_count") == 7,
                f"rejection repeat_count incorrect: {compact_rejections}",
            )

            rag_db = repo_root / "rag.sqlite"
            conn = sqlite3.connect(rag_db)
            try:
                conn.execute(
                    "CREATE TABLE rag_chunks (chunk_id TEXT PRIMARY KEY, source_path TEXT, chunk_index INTEGER, "
                    "char_start INTEGER, char_end INTEGER, text TEXT, text_hash TEXT, active INTEGER)"
                )
                conn.execute(
                    "CREATE VIRTUAL TABLE rag_chunks_fts USING fts5(chunk_id, source_path, text, metadata_json)"
                )
                rag_rows = [
                    (
                        "chunk-1",
                        "docs/code-product.md",
                        "Generate detailed code diff with repo_propose_code_edit.",
                    ),
                    (
                        "chunk-shared-core",
                        shared_target,
                        "core runtime planner validator broker loop _shared scope conflict repo_read evidence",
                    ),
                    (
                        "chunk-stale-lab-repo",
                        "ia_carmine/_shared/stale_missing.py",
                        "uniquestalemarker stale index path outside current LAB_REPO file set",
                    ),
                ]
                for index, (chunk_id, source_path, chunk_text) in enumerate(rag_rows):
                    conn.execute(
                        "INSERT INTO rag_chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            chunk_id,
                            source_path,
                            index,
                            0,
                            len(chunk_text),
                            chunk_text,
                            f"hash-{index + 1}",
                            1,
                        ),
                    )
                    conn.execute(
                        "INSERT INTO rag_chunks_fts(chunk_id, source_path, text, metadata_json) VALUES (?, ?, ?, ?)",
                        (chunk_id, source_path, chunk_text, "{}"),
                    )
                conn.commit()
            finally:
                conn.close()
            intrinsic = planner.build_planner_intrinsic_context(
                goal=goal,
                history=history_read,
                evidence_contract=missing_contract,
                planner_memory={"available": True, "source": "smoke", "records": [], "record_count": 0},
                rag_db=rag_db,
                num_ctx=32768,
                max_chars=9000,
                rag_top_k=4,
                rag_char_budget=2000,
            )
            require(intrinsic.get("schema") == "planner_intrinsic_context.v1", "intrinsic_context schema missing")
            require(
                intrinsic.get("retrieved_rag_chunks", {}).get("status") == "ready",
                f"intrinsic_context did not read rag.sqlite fixture: {intrinsic.get('retrieved_rag_chunks')}",
            )
            require(
                intrinsic.get("retrieved_rag_chunks", {}).get("items"),
                "intrinsic_context rag.sqlite fixture returned no chunks",
            )
            require(
                intrinsic.get("budget_report", {}).get("num_ctx_effective") == 32768,
                "intrinsic_context budget_report did not expose num_ctx_effective",
            )
            require(
                intrinsic.get("budget_report", {}).get("intrinsic_context_chars", 10_000) <= 9000,
                "intrinsic_context exceeded configured max_chars",
            )
            tool_manifest = [
                {
                    "name": item["function"]["name"],
                    "description": item["function"]["description"],
                    "parameters": item["function"]["parameters"],
                }
                for item in TOOLS_SCHEMA
                if isinstance(item.get("function"), dict)
                and item["function"].get("name") in planner.internal_tools_list(exclude_vulkan=False)
            ]
            planner_payload, prompt_report = planner._build_planner_user_payload(
                job_id="smoke-code-product",
                state={"goal": goal, "max_steps": 4, "approval_mode": None},
                step=1,
                history=history_read,
                tool_manifest=tool_manifest,
                evidence_contract=missing_contract,
                planner_memory={"available": True, "source": "smoke", "records": [], "record_count": 0},
                intrinsic_context=intrinsic,
                last_tool_result=history_read[-1]["tool_result"],
            )
            require(prompt_report.get("over_budget") is False, f"planner prompt pack over budget: {prompt_report}")
            require(
                (planner_payload.get("prompt_budget_report") or {}).get("sections") is None,
                "planner payload embeds the verbose budget section report and can self-overflow",
            )
            read_windows = (planner_payload.get("required_working_set") or {}).get("repo_reads") or []
            require(read_windows, "planner prompt pack lacks required repo_read window")
            first_window = read_windows[0].get("content_window") or {}
            require(first_window.get("text") == old_text, "required working set did not preserve target content")
            require(first_window.get("complete") is True, "small required target was not complete")
            require(first_window.get("sha256"), "required target window lacks hash")
            chunk_write = memory_tools.planner_scratchpad_write(
                {"kind": "answer_chunk", "tag": "section-1", "text": "Complete validated section one."},
                job_root,
            )
            require(chunk_write.get("ok") is True, f"answer_chunk scratchpad write failed: {chunk_write}")
            composed = memory_tools.planner_composed_answer(job_root)
            require(composed.get("ok") is True, f"planner composer did not read answer_chunk: {composed}")
            require("Complete validated section one." in composed.get("text", ""), "planner composer text missing chunk")
            empty_build_state = {
                "schema": "code_product_build_state.v1",
                "target_file": target,
                "status": "collecting_source",
                "source_windows": [],
                "rationale": "",
                "edit_kind": "unified_diff",
                "old_text": "",
                "new_text": "",
                "blocker": "",
            }
            empty_build_text = json.dumps(empty_build_state, ensure_ascii=False)
            empty_build_gate = planner.validate_planner_decision_against_evidence(
                goal,
                {
                    "action": "tool",
                    "tool": "planner_scratchpad_write",
                    "arguments": {"kind": "code_product_build_state", "target_file": target, "text": empty_build_text},
                },
                history_read,
            )
            require(
                "code_product_build_state_collecting_source_without_progress" in empty_build_gate.get("violations", []),
                f"empty collecting_source build state was not rejected: {empty_build_gate}",
            )
            progress_build_state = {
                "schema": "code_product_build_state.v1",
                "target_file": target,
                "status": "collecting_source",
                "source_windows": [{"document_id": "source-doc", "offset": 0, "complete": False, "sha256": "source"}],
                "rationale": "",
                "edit_kind": "unified_diff",
                "old_text": "",
                "new_text": "",
                "blocker": "",
            }
            progress_build_text = json.dumps(progress_build_state, ensure_ascii=False)
            progress_build_gate = planner.validate_planner_decision_against_evidence(
                goal,
                {
                    "action": "tool",
                    "tool": "planner_scratchpad_write",
                    "arguments": {"kind": "code_product_build_state", "target_file": target, "text": progress_build_text},
                },
                history_read,
            )
            require(progress_build_gate.get("ok") is True, f"progress collecting_source was rejected: {progress_build_gate}")
            progress_build_write = memory_tools.planner_scratchpad_write(
                {"kind": "code_product_build_state", "target_file": target, "text": progress_build_text},
                job_root,
            )
            progress_build_history = history_read + [
                compact_history_row(
                    root=job_root,
                    step=2,
                    tool="planner_scratchpad_write",
                    arguments={"kind": "code_product_build_state", "target_file": target, "text": progress_build_text},
                    result=progress_build_write,
                )
            ]
            duplicate_build_gate = planner.validate_planner_decision_against_evidence(
                goal,
                {
                    "action": "tool",
                    "tool": "planner_scratchpad_write",
                    "arguments": {"kind": "code_product_build_state", "target_file": target, "text": progress_build_text},
                },
                progress_build_history,
            )
            require(
                "code_product_build_state_duplicate_without_progress" in duplicate_build_gate.get("violations", []),
                f"duplicate build state write was not rejected: {duplicate_build_gate}",
            )
            empty_read_result = {
                "ok": True,
                "tool": "planner_scratchpad_read",
                "mode": "code_product_build_state",
                "kind": "code_product_build_state",
                "count": 0,
                "items": [],
            }
            empty_read_history = history_read + [
                compact_history_row(
                    root=job_root,
                    step=2,
                    tool="planner_scratchpad_read",
                    arguments={"kind": "code_product_build_state", "section": "code_product_build_state"},
                    result=empty_read_result,
                )
            ]
            require(
                latest_code_product_build_state(empty_read_history, target) == {},
                "empty code_product_build_state read produced a fake latest state",
            )
            empty_read_contract = planner.planner_evidence_contract(goal, empty_read_history)
            empty_read_actions = empty_read_contract.get("candidate_next_actions") or []
            require(
                not any(
                    isinstance(item, dict)
                    and item.get("tool") == "planner_scratchpad_read"
                    and (item.get("arguments") or {}).get("kind") == "code_product_build_state"
                    and not (item.get("arguments") or {}).get("document_id")
                    and not (item.get("arguments") or {}).get("target_file")
                    and (item.get("arguments") or {}).get("section") in ("", "code_product_build_state", None)
                    for item in empty_read_actions
                ),
                f"empty build-state read produced a generic targetless read candidate: {empty_read_actions}",
            )
            large_build_state = {
                "schema": "code_product_build_state.v1",
                "target_file": target,
                "status": "collecting_source",
                "source_windows": [{"document_id": "source-doc", "offset": 0, "complete": False, "sha256": "source"}],
                "rationale": "",
                "edit_kind": "unified_diff",
                "old_text": "A" * 13000,
                "new_text": "B" * 13000,
                "blocker": "",
            }
            large_build_text = json.dumps(large_build_state, ensure_ascii=False)
            large_build_write = memory_tools.planner_scratchpad_write(
                {"kind": "code_product_build_state", "target_file": target, "text": large_build_text, "max_chars": 2000},
                job_root,
            )
            require(large_build_write.get("ok") is True, f"large code_product_build_state write failed: {large_build_write}")
            large_build_read = memory_tools.planner_scratchpad_read(
                {
                    "kind": "code_product_build_state",
                    "target_file": target,
                    "document_id": large_build_write.get("document_id"),
                    "offset": 0,
                    "max_chars": 3000,
                },
                job_root,
            )
            require(large_build_read.get("ok") is True, f"large code_product_build_state read failed: {large_build_read}")
            large_item = (large_build_read.get("items") or [{}])[0]
            require(large_item.get("full_chars") == len(large_build_text), "large build state was truncated in SQLite")
            require(large_item.get("has_more_after") is True, "large build state was not exposed as a real window")
            large_build_history = history_read + [
                compact_history_row(
                    root=job_root,
                    step=2,
                    tool="planner_scratchpad_write",
                    arguments={"kind": "code_product_build_state", "target_file": target, "text": large_build_text},
                    result=large_build_write,
                )
            ]
            large_build_contract = planner.planner_evidence_contract(goal, large_build_history)
            large_build_actions = large_build_contract.get("candidate_next_actions") or []
            require(
                any(
                    isinstance(item, dict)
                    and item.get("tool") == "planner_scratchpad_read"
                    and (item.get("arguments") or {}).get("kind") == "code_product_build_state"
                    for item in large_build_actions
                ),
                f"non-ready build state did not route to code_product_build_state read: {large_build_actions}",
            )
            require(
                target not in action_argument_paths(large_build_actions, "repo_read"),
                "target already read was proposed again as repo_read instead of build-state progress",
            )
            progress_build_read = memory_tools.planner_scratchpad_read(
                {
                    "kind": "code_product_build_state",
                    "document_id": progress_build_write.get("document_id"),
                    "offset": 0,
                    "max_chars": 8000,
                },
                job_root,
            )
            loaded_progress_history = progress_build_history + [
                compact_history_row(
                    root=job_root,
                    step=3,
                    tool="planner_scratchpad_read",
                    arguments={"kind": "code_product_build_state", "document_id": progress_build_write.get("document_id")},
                    result=progress_build_read,
                )
            ]
            loaded_progress_contract = planner.planner_evidence_contract(goal, loaded_progress_history)
            loaded_progress_actions = loaded_progress_contract.get("candidate_next_actions") or []
            progress_write_candidates = [
                item for item in loaded_progress_actions
                if isinstance(item, dict)
                and item.get("tool") == "planner_scratchpad_write"
                and (item.get("arguments") or {}).get("kind") == "code_product_build_state"
            ]
            require(
                not any(
                    not str((item.get("arguments") or {}).get("text") or (item.get("arguments") or {}).get("content") or "").strip()
                    for item in progress_write_candidates
                ),
                f"candidate_next_actions exposed non-executable empty build-state write: {progress_write_candidates}",
            )
            require(
                "Empty collecting_source writes are rejected" in str(loaded_progress_contract.get("required_next_progress") or ""),
                f"loaded non-ready build state did not force real progress/block: {loaded_progress_contract.get('required_next_progress')}",
            )
            ready_build_state = {
                "schema": "code_product_build_state.v1",
                "target_file": target,
                "status": "ready_for_propose",
                "source_windows": [{"document_id": "source-doc", "offset": 0, "complete": True, "sha256": "source"}],
                "rationale": "Exact old_text/new_text from verified repo_read.",
                "edit_kind": "unified_diff",
                "old_text": old_text,
                "new_text": new_text,
                "blocker": "",
            }
            ready_build_text = json.dumps(ready_build_state, ensure_ascii=False)
            ready_build_write = memory_tools.planner_scratchpad_write(
                {"kind": "code_product_build_state", "target_file": target, "text": ready_build_text},
                job_root,
            )
            require(ready_build_write.get("complete_payload_ready") is True, f"ready build state not marked ready: {ready_build_write}")
            ready_build_read = memory_tools.planner_scratchpad_read(
                {
                    "kind": "code_product_build_state",
                    "document_id": ready_build_write.get("document_id"),
                    "offset": 0,
                    "max_chars": 8000,
                },
                job_root,
            )
            ready_history = history_read + [
                compact_history_row(
                    root=job_root,
                    step=3,
                    tool="planner_scratchpad_write",
                    arguments={"kind": "code_product_build_state", "target_file": target, "text": ready_build_text},
                    result=ready_build_write,
                ),
                compact_history_row(
                    root=job_root,
                    step=4,
                    tool="planner_scratchpad_read",
                    arguments={"kind": "code_product_build_state", "document_id": ready_build_write.get("document_id")},
                    result=ready_build_read,
                ),
            ]
            ready_contract = planner.planner_evidence_contract(goal, ready_history)
            ready_actions = ready_contract.get("candidate_next_actions") or []
            ready_proposals = [
                item for item in ready_actions
                if isinstance(item, dict) and item.get("tool") == "repo_propose_code_edit"
            ]
            require(ready_proposals, f"ready build state did not expose repo_propose_code_edit: {ready_actions}")
            ready_args = ready_proposals[0].get("arguments") or {}
            ready_gate = planner.validate_planner_decision_against_evidence(
                goal,
                {"action": "tool", "tool": "repo_propose_code_edit", "arguments": ready_args},
                ready_history,
            )
            require(ready_gate.get("ok") is True, f"ready build state proposal was rejected: {ready_gate}")
            ready_result = repo_tools.repo_propose_code_edit(ready_args, job_root)
            require(
                proposal_ok_or_dependency_only(ready_result),
                f"ready build state proposal tool failed for non-dependency reason: {ready_result}",
            )
            require("@@" in str(ready_result.get("unified_diff") or ""), "ready build state did not generate unified diff")
            blocked_build_state = {
                "schema": "code_product_build_state.v1",
                "target_file": target,
                "status": "blocked_incomplete",
                "source_windows": [{"document_id": "source-doc", "offset": 0, "complete": True, "sha256": "source"}],
                "rationale": "",
                "edit_kind": "unified_diff",
                "blocker": "no coherent edit anchor after reading all windows",
            }
            blocked_build_text = json.dumps(blocked_build_state, ensure_ascii=False)
            blocked_write = memory_tools.planner_scratchpad_write(
                {"kind": "code_product_build_state", "target_file": target, "text": blocked_build_text},
                job_root,
            )
            blocked_read = memory_tools.planner_scratchpad_read(
                {
                    "kind": "code_product_build_state",
                    "document_id": blocked_write.get("document_id"),
                    "offset": 0,
                    "max_chars": 8000,
                },
                job_root,
            )
            blocked_history = history_read + [
                compact_history_row(
                    root=job_root,
                    step=5,
                    tool="planner_scratchpad_write",
                    arguments={"kind": "code_product_build_state", "target_file": target, "text": blocked_build_text},
                    result=blocked_write,
                ),
                compact_history_row(
                    root=job_root,
                    step=6,
                    tool="planner_scratchpad_read",
                    arguments={"kind": "code_product_build_state", "document_id": blocked_write.get("document_id")},
                    result=blocked_read,
                ),
            ]
            blocked_contract = planner.planner_evidence_contract(goal, blocked_history)
            require(
                "code_product_build_state_blocked_incomplete" in str(blocked_contract.get("required_next_progress") or ""),
                f"blocked build state did not route to typed block: {blocked_contract.get('required_next_progress')}",
            )
            blocked_gate = planner.validate_planner_decision_against_evidence(
                goal,
                {
                    "action": "block",
                    "final_answer": "code_product_build_state_blocked_incomplete: no coherent edit anchor after reading all windows",
                    "reason": "code_product_build_state_blocked_incomplete",
                },
                blocked_history,
            )
            require(blocked_gate.get("ok") is True, f"blocked build state typed block was rejected: {blocked_gate}")
            require(
                planner._public_tool_response(ready_build_write) == {}
                and planner._public_tool_response(ready_build_read) == {},
                "code_product_build_state leaked into public tool response",
            )
            intrinsic_rerank_down = planner.build_planner_intrinsic_context(
                goal=goal,
                history=history_read,
                evidence_contract=missing_contract,
                planner_memory={"available": True, "source": "smoke", "records": [], "record_count": 0},
                rag_db=rag_db,
                num_ctx=32768,
                max_chars=9000,
                rag_top_k=4,
                rag_char_budget=2000,
                rerank_engine="external",
                rerank_url="http://127.0.0.1:9/v3/rerank",
                rerank_model="BAAI/bge-reranker-v2-m3",
                rerank_timeout_seconds=0.1,
                rag_embedding_batch_size=4,
            )
            rerank_status = intrinsic_rerank_down.get("retrieved_rag_chunks", {}).get("rerank", {}).get("status")
            require(
                rerank_status in {"unavailable", "error"},
                f"down external reranker was not reported explicitly: {rerank_status}",
            )
            require(
                intrinsic_rerank_down.get("retrieved_rag_chunks", {}).get("ranking_source")
                == "fts_only_rerank_unavailable",
                "down external reranker did not mark fts_only_rerank_unavailable",
            )
            scope_goal = (
                "Analisi della struttura del repository ia_carmine. "
                "_shared non e core. Generate a detailed code diff for the real core target."
            )
            scope_list_args = {"path": "ia_carmine", "limit": 120}
            scope_list_result = repo_tools.repo_list_files(scope_list_args, job_root)
            require(scope_list_result.get("ok") is True, f"scope repo_list_files failed: {scope_list_result}")
            scope_history = [
                compact_history_row(
                    root=job_root,
                    step=20,
                    tool="repo_list_files",
                    arguments=scope_list_args,
                    result=scope_list_result,
                )
            ]
            scope_base_contract = planner.planner_evidence_contract(scope_goal, scope_history)
            scope_intrinsic = planner.build_planner_intrinsic_context(
                goal=scope_goal,
                history=scope_history,
                evidence_contract=scope_base_contract,
                planner_memory={"available": True, "source": "smoke", "records": [], "record_count": 0},
                rag_db=rag_db,
                num_ctx=32768,
                max_chars=9000,
                rag_top_k=6,
                rag_char_budget=2000,
            )
            scope_contract = planner.planner_evidence_contract(
                scope_goal,
                scope_history,
                intrinsic_context=scope_intrinsic,
            )
            require(scope_contract.get("user_scope_claims"), "user_scope_claim for _shared was not extracted")
            discovery_candidates = scope_contract.get("core_discovery_candidates") or []
            require(
                any(
                    isinstance(item, dict)
                    and item.get("path") == shared_target
                    and item.get("claim_conflict") is True
                    for item in discovery_candidates
                ),
                f"RAG/rerank did not surface conflicting _shared read candidate: {discovery_candidates}",
            )
            candidate_reads = action_argument_paths(scope_contract.get("candidate_next_actions") or [], "repo_read")
            require(shared_target in candidate_reads, f"candidate_next_actions did not expose repo_read for _shared: {candidate_reads}")
            candidate_patches = [
                item for item in scope_contract.get("candidate_next_actions") or []
                if isinstance(item, dict)
                and item.get("tool") == "repo_propose_code_edit"
                and (item.get("arguments") or {}).get("target_file") == shared_target
            ]
            require(not candidate_patches, f"discovery forced a patch candidate instead of repo_read: {candidate_patches}")

            stale_index_goal = "uniquestalemarker"
            stale_index_base = planner.planner_evidence_contract(stale_index_goal, scope_history)
            stale_index_intrinsic = planner.build_planner_intrinsic_context(
                goal=stale_index_goal,
                history=scope_history,
                evidence_contract=stale_index_base,
                planner_memory={"available": True, "source": "smoke", "records": [], "record_count": 0},
                rag_db=rag_db,
                num_ctx=32768,
                max_chars=9000,
                rag_top_k=4,
                rag_char_budget=2000,
            )
            stale_index_contract = planner.planner_evidence_contract(
                stale_index_goal,
                scope_history,
                intrinsic_context=stale_index_intrinsic,
            )
            stale_status = stale_index_contract.get("core_discovery_status") or {}
            require(
                stale_status.get("source") == "ranking_rebuilt_from_lab_repo_evidence"
                and stale_status.get("rebuild_performed") is True,
                f"stale RAG index did not rebuild ranking for current LAB_REPO: {stale_status}",
            )
            stale_candidate_paths = [
                item.get("path") for item in stale_index_contract.get("core_discovery_candidates") or []
                if isinstance(item, dict)
            ]
            require(
                "ia_carmine/_shared/stale_missing.py" not in stale_candidate_paths,
                f"stale RAG path leaked into core_discovery_candidates: {stale_candidate_paths}",
            )

            shared_read_args = {"path": shared_target, "max_chars": 20000}
            shared_read_result = repo_tools.repo_read(shared_read_args, job_root)
            require(shared_read_result.get("ok") is True, f"_shared repo_read failed: {shared_read_result}")
            shared_history = scope_history + [
                compact_history_row(
                    root=job_root,
                    step=21,
                    tool="repo_read",
                    arguments=shared_read_args,
                    result=shared_read_result,
                )
            ]
            shared_diff = generate_unified_diff_from_texts(
                target_file=shared_target,
                old_text=shared_old,
                new_text=shared_new,
            )
            generic_shared_args = {
                "target_file": shared_target,
                "edit_kind": "unified_diff",
                "rationale": "Update shared helper.",
                "unified_diff": shared_diff,
            }
            generic_shared_gate = planner.validate_planner_decision_against_evidence(
                scope_goal,
                {"action": "tool", "tool": "repo_propose_code_edit", "arguments": generic_shared_args},
                shared_history,
            )
            require(
                "target_scope_conflict_unresolved" in generic_shared_gate.get("violations", []),
                f"generic _shared patch did not trip target_scope_conflict_unresolved: {generic_shared_gate}",
            )
            evidence_shared_args = dict(generic_shared_args)
            evidence_shared_args["rationale"] = (
                "repo_read content shows SharedCoreRuntime, planner_entrypoint, validator_gate, "
                "broker_loop and core_signal; that read evidence proves this _shared file is core "
                "runtime for the planner validator broker loop despite the user scope claim."
            )
            evidence_shared_gate = planner.validate_planner_decision_against_evidence(
                scope_goal,
                {"action": "tool", "tool": "repo_propose_code_edit", "arguments": evidence_shared_args},
                shared_history,
            )
            require(
                "target_scope_conflict_unresolved" not in evidence_shared_gate.get("violations", []),
                f"evidence-based _shared patch still failed scope conflict gate: {evidence_shared_gate}",
            )
            require(evidence_shared_gate.get("ok") is True, f"evidence-based _shared patch was rejected: {evidence_shared_gate}")

            forbidden_new_surfaces = [
                name for name in tool_registry.PLANNER_INTERNAL_TOOLS
                if "rag" in name.lower() or "chunk" in name.lower() or "intrinsic" in name.lower()
            ]
            require(
                not forbidden_new_surfaces,
                f"RAG/chunk/intrinsic leaked into planner tool surface: {forbidden_new_surfaces}",
            )
            openapi_schema = bridge_app.app.openapi()
            require(
                openapi_schema.get("x-aicarmine-public-surface") == ["vulkan_helper"],
                f"OpenWebUI public surface changed: {openapi_schema.get('x-aicarmine-public-surface')}",
            )
            vulkan_request_schema = (
                openapi_schema.get("paths", {})
                .get("/vulkan_helper", {})
                .get("post", {})
                .get("requestBody", {})
            )
            vulkan_request_text = json.dumps(vulkan_request_schema, ensure_ascii=False, default=str)
            for forbidden_field in ("core_discovery_candidates", "user_scope_claims", "expected_output"):
                require(
                    forbidden_field not in vulkan_request_text,
                    f"internal/regression field leaked into vulkan_helper request schema: {forbidden_field}",
                )

            proposal_args = {
                "target_file": target,
                "edit_kind": "unified_diff",
                "rationale": "Return 2 instead of 1 for the smoke fixture.",
                "unified_diff": diff_text,
                "ast_anchor": "answer",
                "ast_grep_rule": "return 1",
                "tree_sitter_language": "python",
            }
            tool_gate = planner.validate_planner_decision_against_evidence(
                goal,
                {"action": "tool", "tool": "repo_propose_code_edit", "arguments": proposal_args},
                history_read,
            )
            require(tool_gate.get("ok") is True, f"valid repo_propose_code_edit was rejected: {tool_gate}")
            proposal_result = repo_tools.repo_propose_code_edit(proposal_args, job_root)
            require(
                proposal_ok_or_dependency_only(proposal_result),
                f"repo_propose_code_edit failed for non-dependency reason: {proposal_result}",
            )
            require(proposal_result.get("unified_diff") == diff_text, "repo_propose_code_edit did not keep full diff inline")
            require(proposal_result.get("source_writes_performed") is False, "proposal wrote source")
            require(proposal_result.get("patch_application_performed") is False, "proposal applied a patch")
            require((repo_root / target).read_text(encoding="utf-8") == old_text, "proposal changed source file")
            phrase_result = repo_tools.repo_propose_code_edit(
                {
                    "target_file": target,
                    "edit_kind": "unified_diff",
                    "rationale": "Exact phrase replacement from repo_read.",
                    "old_text": "return 1",
                    "new_text": "return 2",
                    "tree_sitter_language": "python",
                },
                job_root,
            )
            require(
                proposal_ok_or_dependency_only(phrase_result),
                f"old_text/new_text phrase diff failed for non-dependency reason: {phrase_result}",
            )
            phrase_diff = str(phrase_result.get("unified_diff") or "")
            require("@@" in phrase_diff, "old_text/new_text phrase diff lacks hunk marker")
            require("-    return 1" in phrase_diff, "old_text/new_text phrase diff lacks original full line")
            require("+    return 2" in phrase_diff, "old_text/new_text phrase diff lacks replacement full line")
            if proposal_result.get("ok") is True:
                require(
                    (proposal_result.get("ast_evidence") or {}).get("tree_sitter", {}).get("ok") is True,
                    "tree-sitter evidence missing or failed",
                )
                require(
                    (proposal_result.get("ast_evidence") or {}).get("ast_grep", {}).get("match_found") is True,
                    "ast-grep evidence missing or failed",
                )
            else:
                require(
                    proposal_ok_or_dependency_only(proposal_result),
                    f"repo_propose_code_edit AST evidence failed for non-dependency reason: {proposal_result}",
                )
            proposal_result_for_history = dict(proposal_result)
            if proposal_result.get("ok") is not True:
                proposal_result_for_history["ok"] = True
                proposal_result_for_history["errors"] = []
                proposal_result_for_history["manual_review_required"] = True

            history_valid = history_read + [
                compact_history_row(
                    root=job_root,
                    step=2,
                    tool="repo_propose_code_edit",
                    arguments=proposal_args,
                    result=proposal_result_for_history,
                )
            ]
            code_product_answer = planner.answer_for_openwebui(
                "completed",
                "Planner prose should not be the primary answer for code products.",
                {"history": history_valid},
            )
            require("```diff" in code_product_answer, "code-product answer did not surface full diff")
            require(diff_text.rstrip("\n") in code_product_answer, "code-product answer omitted complete unified diff")
            require(
                not code_product_answer.startswith("Planner prose should not be the primary answer"),
                "code-product answer still starts from planner prose instead of artifact",
            )
            final_ok = planner.validate_planner_decision_against_evidence(
                goal,
                {"action": "final", "final_answer": "Diff produced in repo_propose_code_edit."},
                history_valid,
            )
            require(final_ok.get("ok") is True, f"valid code product final rejected: {final_ok}")
            valid_contract = planner.planner_evidence_contract(goal, history_valid)
            require(
                (valid_contract.get("finalization_contract") or {}).get("final_allowed") is True,
                "valid code product contract did not allow final after repo_propose_code_edit",
            )

            context = planner.build_tool_context_for_30b(
                "smoke-code-product",
                {"goal": goal},
                "completed",
                "done",
                {"history": history_valid, "planner_decision": {"action": "final", "final_answer": "done"}},
            )
            proposal_artifacts = [
                row for row in context.get("artifacts", [])
                if isinstance(row, dict)
                and row.get("tool") == "repo_propose_code_edit"
                and isinstance(row.get("artifact"), dict)
            ]
            require(proposal_artifacts, "tool_context_for_30b lacks public repo_propose_code_edit artifact")
            require(
                proposal_artifacts[-1]["artifact"].get("unified_diff") == diff_text,
                "public artifact did not preserve full unified_diff",
            )
            require(
                proposal_artifacts[-1]["artifact"].get("kind") == "code_edit_proposal",
                "public code proposal artifact has wrong kind",
            )
            serialized_context = json.dumps(context, ensure_ascii=False, default=str)
            require("unified_diff_preview" not in serialized_context, "context contains unified_diff_preview")
            require('"preview_only": true' not in serialized_context.lower(), "context marks preview_only=true")
            require("tool-results" not in serialized_context, "tool_context_for_30b leaked local tool-results path")
            require("planner_composer.sqlite" not in serialized_context, "tool_context_for_30b leaked composer sqlite path")
            require("document_id" not in serialized_context, "tool_context_for_30b leaked SQLite document_id")
            require("C:\\Users\\" not in serialized_context, "tool_context_for_30b leaked local Windows path")
            bridge_wrapped = bridge_app._agentic_v9_build_openwebui_response(
                {
                    "service": "vulkan_agent",
                    "job_id": "smoke-code-product",
                    "job_url": "http://127.0.0.1:3572/jobs/smoke-code-product",
                    "status": "completed",
                    "job_ok": True,
                    "answer_for_30b": "done",                    
                    "next_action_for_30b": {},
                    "result": {"preview": "planner preview"},
                    "full_result_available": True,
                    "bridge_status": "AGENT_RESULT_RETURNED",
                    "bridge_waited_for_agent": True,
                    "bridge_elapsed_seconds": 1.25,
                    "bridge_agent_url": "http://127.0.0.1:3572/vulkan/agent",
                    "wrapper_expected_contract": {
                        "type": "deterministic_public_tool_result",
                        "public_tool_x": "vulkan_helper",
                        "owner": "3572 broker",
                        "required_top_level_keys": ["ok", "payload_index_for_30b", "content"],
                    },
                    "tool_context_for_30b": context,
                }
            )
            for removed_public_field in (
                "job_id",
                "job_url",
                "next_action_for_30b",
                "full_result_available",
                "full_result_hint",
                "bridge_status",
                "bridge_waited_for_agent",
                "bridge_elapsed_seconds",
                "bridge_agent_url",
            ):
                require(
                    removed_public_field not in bridge_wrapped,
                    f"bridge v9 leaked public field: {removed_public_field}",
                )
            require(
                bridge_wrapped.get("result", {}).get("preview") == "planner preview",
                "bridge v9 removed or moved away result.preview",
            )
            require(
                "wrapper_expected_contract" not in bridge_wrapped,
                "bridge v9 leaked wrapper_expected_contract",
            )
            require(
                bridge_wrapped.get("required_top_level_keys")
                == [
                    "ok",
                    "service",
                    "mode",
                    "required_top_level_keys",
                    "evidence_guide_for_30b",
                    "payload_index_for_30b",
                    "priority_evidence_for_30b",
                    "materialization_report",
                    "openwebui_usage",
                    "tool_context_for_30b",
                ],
                "bridge v9 did not promote required_top_level_keys",
            )
            public_key_order = list(bridge_wrapped)
            require(
                public_key_order.index("payload_index_for_30b")
                < public_key_order.index("openwebui_usage")
                < public_key_order.index("priority_evidence_for_30b")
                < public_key_order.index("tool_context_for_30b"),
                f"bridge v9 public field order is wrong: {public_key_order}",
            )
            if "result" in public_key_order:
                require(
                    public_key_order.index("tool_context_for_30b") < public_key_order.index("result"),
                    f"bridge v9 result appeared before primary evidence: {public_key_order}",
                )
            require("content" not in bridge_wrapped, f"bridge v9 leaked content top-level: {public_key_order}")
            require("answer_for_30b" not in bridge_wrapped, f"bridge v9 leaked answer_for_30b: {public_key_order}")
            require("message_for_30b" not in bridge_wrapped, f"bridge v9 leaked message_for_30b: {public_key_order}")
            require("summary_for_30b" not in bridge_wrapped, f"bridge v9 leaked summary_for_30b: {public_key_order}")
            bridge_context_raw = bridge_wrapped.get("tool_context_for_30b")
            bridge_context = (
                json.loads(bridge_context_raw)
                if isinstance(bridge_context_raw, str)
                else bridge_context_raw
            )
            serialized_bridge_context = json.dumps(bridge_context, ensure_ascii=False, default=str)
            require(
                diff_text in collect_key_values(bridge_context, "unified_diff"),
                "bridge v9 tool_context_for_30b lost the full diff",
            )
            bridge_proposal_artifacts = [
                row for row in bridge_context.get("artifacts", [])
                if isinstance(row, dict)
                and row.get("tool") == "repo_propose_code_edit"
                and isinstance(row.get("artifact"), dict)
            ]
            require(
                bridge_proposal_artifacts
                and bridge_proposal_artifacts[-1]["artifact"].get("unified_diff") == diff_text,
                "bridge v9 public artifact lost the full diff",
            )
            require(
                "unified_diff_preview" not in serialized_bridge_context,
                "bridge v9 introduced unified_diff_preview",
            )
            require("tool-results" not in serialized_bridge_context, "bridge v9 leaked local tool-results path")
            require("planner_composer.sqlite" not in serialized_bridge_context, "bridge v9 leaked composer sqlite path")
            require("document_id" not in serialized_bridge_context, "bridge v9 leaked SQLite document_id")
            require("C:\\Users\\" not in serialized_bridge_context, "bridge v9 leaked local Windows path")

            preview_only = dict(proposal_result_for_history)
            preview_only.pop("unified_diff", None)
            preview_only["unified_diff_preview"] = diff_text[:20]
            preview_only["ok"] = True
            preview_history = history_read + [
                compact_history_row(
                    root=job_root,
                    step=3,
                    tool="repo_propose_code_edit",
                    arguments=proposal_args,
                    result=preview_only,
                )
            ]
            preview_gate = planner.validate_planner_decision_against_evidence(
                goal,
                {"action": "final", "final_answer": "bad"},
                preview_history,
            )
            require(
                "code_product_payload_not_complete" in preview_gate.get("violations", []),
                "preview-only proposal was not rejected",
            )

            broken_diff = dict(proposal_result_for_history)
            broken_diff["unified_diff"] = "--- a/pkg/example.py\n+++ b/pkg/example.py\n-old\n+new\n"
            broken_diff["ok"] = True
            broken_history = history_read + [
                compact_history_row(
                    root=job_root,
                    step=4,
                    tool="repo_propose_code_edit",
                    arguments=proposal_args,
                    result=broken_diff,
                )
            ]
            broken_gate = planner.validate_planner_decision_against_evidence(
                goal,
                {"action": "final", "final_answer": "bad"},
                broken_history,
            )
            require(
                "invalid_code_product_candidate" in broken_gate.get("violations", []),
                "diff without @@ was not rejected",
            )

            unread_gate = planner.validate_planner_decision_against_evidence(
                goal,
                {"action": "final", "final_answer": "bad"},
                [
                    compact_history_row(
                        root=job_root,
                        step=5,
                        tool="repo_propose_code_edit",
                        arguments=proposal_args,
                        result=proposal_result_for_history,
                    )
                ],
            )
            require(
                "code_product_target_not_read" in unread_gate.get("violations", []),
                "proposal target without repo_read was not rejected",
            )

            noop_gate = planner.validate_planner_decision_against_evidence(
                goal,
                {
                    "action": "tool",
                    "tool": "repo_propose_code_edit",
                    "arguments": {"target_file": target, "edit_kind": "no_op", "rationale": ""},
                },
                history_read,
            )
            require(
                "repo_propose_code_edit_missing_rationale" in noop_gate.get("violations", []),
                "no_op without rationale was not rejected",
            )
            require(
                not planner._should_attempt_vulkan_repair(
                    {
                        "action": "tool",
                        "tool": "repo_propose_code_edit",
                        "arguments": {"target_file": target, "edit_kind": "no_op", "rationale": ""},
                    },
                    noop_gate,
                    history_read,
                ),
                "repo_propose_code_edit validator failure was routed to Vulkan/GPU0 repair",
            )
            invalid_path_validation = {
                "ok": False,
                "violations": ["non_existing_path:src"],
                "evidence_contract": {
                    "known_paths_from_latest_repo_list_files": [f"pkg/file_{idx}.py" for idx in range(120)],
                    "successful_repo_read_paths": [target],
                    "verified_content_reads": [
                        {"path": target, "content_excerpt": "x" * 2000}
                        for _ in range(20)
                    ],
                    "code_product_contract": {
                        "required": True,
                        "required_tool": "repo_propose_code_edit",
                        "latest_violations": ["non_existing_path:src"],
                    },
                    "required_next_progress": "read a real target or propose a code product from verified evidence",
                },
            }
            require(
                not planner._should_attempt_vulkan_repair(
                    {
                        "action": "tool",
                        "tool": "repo_list_files",
                        "arguments": {"path": "src", "core": True},
                    },
                    invalid_path_validation,
                    history_read,
                ),
                "non_existing_path validator failure was routed to Vulkan/GPU0 repair",
            )
            bounded_repair_contract = planner._compact_vulkan_repair_evidence_contract(
                invalid_path_validation["evidence_contract"]
            )
            require(
                len(json.dumps(bounded_repair_contract, ensure_ascii=False, default=str)) < 8000,
                "Vulkan/GPU0 repair evidence contract was not bounded",
            )
            require(
                bounded_repair_contract.get("known_paths_from_latest_repo_list_files"),
                "bounded Vulkan/GPU0 repair evidence omitted known path evidence",
            )
            code_product_surface = planner._tool_surface_names_for_turn(
                goal=goal,
                evidence_contract={
                    "semantic_goal_classification": {"class": "code_product_report"},
                    "code_product_contract": {"required": True},
                    "goal_requests_apply": False,
                },
                intrinsic_context={},
            )
            require(
                "planner_scratchpad_read" not in code_product_surface,
                f"planner_scratchpad_read leaked into non-continuation code-product surface: {code_product_surface}",
            )
            require(
                "planner_scratchpad_write" in code_product_surface,
                f"planner_scratchpad_write missing from code-product surface: {code_product_surface}",
            )
            deterministic_internal_tools = {
                "repo_fd_files",
                "repo_rg_search",
                "repo_jq_query",
                "repo_ast_grep_search",
                "repo_ast_grep_dry_run",
                "repo_tree_sitter_parse",
                "repo_unidiff_validate",
                "repo_git_apply_check",
                "repo_ruff_check",
                "repo_pyright_check",
                "repo_pytest_run",
                "repo_shellcheck",
                "repo_ctags_symbols",
                "repo_semgrep_scan",
                "repo_hyperfine_benchmark",
            }
            missing_internal_tools = deterministic_internal_tools - set(tool_registry.PLANNER_INTERNAL_TOOLS)
            require(
                not missing_internal_tools,
                f"deterministic adapters missing from internal planner surface: {sorted(missing_internal_tools)}",
            )
            leaked_public_tools = deterministic_internal_tools & set(tool_registry.OPENWEBUI_PUBLIC_TOOLS)
            require(
                not leaked_public_tools,
                f"deterministic adapters leaked into OpenWebUI public tools: {sorted(leaked_public_tools)}",
            )
            analysis_surface = planner._tool_surface_names_for_turn(
                goal="analizza la repo e descrivi il funzionamento",
                evidence_contract={"semantic_goal_classification": {"class": "analysis_only"}},
                intrinsic_context={},
            )
            require(
                {"repo_fd_files", "repo_rg_search", "repo_ctags_symbols"}.issubset(set(analysis_surface)),
                f"analysis surface lacks deterministic discovery/symbol tools: {analysis_surface}",
            )
            require(
                "repo_propose_code_edit" not in analysis_surface
                and "repo_apply_patch" not in analysis_surface
                and "repo_hyperfine_benchmark" not in analysis_surface,
                f"analysis surface exposed code/apply/benchmark tools unexpectedly: {analysis_surface}",
            )
            require(
                {
                    "repo_ast_grep_search",
                    "repo_tree_sitter_parse",
                    "repo_unidiff_validate",
                    "repo_git_apply_check",
                    "repo_propose_code_edit",
                }.issubset(set(code_product_surface)),
                f"code-product surface lacks AST/diff/proposal tools: {code_product_surface}",
            )
            apply_surface = planner._tool_surface_names_for_turn(
                goal="applica una patch e valida con test",
                evidence_contract={
                    "semantic_goal_classification": {"class": "apply_write"},
                    "goal_requests_apply": True,
                },
                intrinsic_context={},
            )
            require(
                {"repo_apply_patch", "repo_ruff_check", "repo_pyright_check", "repo_pytest_run"}.issubset(set(apply_surface)),
                f"apply surface lacks apply/validation tools: {apply_surface}",
            )
            keyword_surface = planner._tool_surface_names_for_turn(
                goal="analizza JSON, security shell e performance benchmark",
                evidence_contract={"semantic_goal_classification": {"class": "analysis_only"}},
                intrinsic_context={},
            )
            require(
                {"repo_jq_query", "repo_semgrep_scan", "repo_shellcheck", "repo_hyperfine_benchmark"}.issubset(
                    set(keyword_surface)
                ),
                f"keyword surface lacks requested deterministic tools: {keyword_surface}",
            )
            native_surface_previous = planner.AGENTIC_PLANNER_NATIVE_TOOLS
            planner.AGENTIC_PLANNER_NATIVE_TOOLS = True
            native_surface_gate = planner.validate_planner_decision_against_evidence(
                "analizza la repo e descrivi il funzionamento",
                {
                    "action": "tool",
                    "tool": "repo_apply_patch",
                    "arguments": {"patch": "diff --git a/x b/x\n"},
                    "allowed_native_tool_names": ["repo_read"],
                    "native_tool_call": True,
                    "raw_native_tool_call": {"function": {"name": "repo_apply_patch"}},
                },
                [],
            )
            planner.AGENTIC_PLANNER_NATIVE_TOOLS = native_surface_previous
            require(
                "native_tool_not_in_turn_surface" in native_surface_gate.get("violations", []),
                f"native out-of-surface tool call was not rejected: {native_surface_gate}",
            )
            continuation_surface = planner._tool_surface_names_for_turn(
                goal=goal,
                evidence_contract={
                    "semantic_goal_classification": {"class": "code_product_report"},
                    "code_product_contract": {"required": True},
                },
                intrinsic_context={},
                prompt_context_continuation_required={
                    "tool": "planner_scratchpad_read",
                    "arguments": {
                        "kind": "prompt_context_window",
                        "document_id": "doc",
                        "offset": 10,
                        "max_chars": 500,
                    },
                },
            )
            require(
                continuation_surface == ["planner_scratchpad_read"],
                f"explicit continuation did not isolate planner_scratchpad_read surface: {continuation_surface}",
            )

            invalid_python_result = repo_tools.repo_propose_code_edit(
                {
                    "target_file": "pkg/bad.py",
                    "edit_kind": "no_op",
                    "rationale": "Smoke parse blocker.",
                    "tree_sitter_language": "python",
                },
                job_root,
            )
            require(invalid_python_result.get("ok") is False, "invalid Python parse did not block proposal")
            require(
                any(str(err).startswith("tree_sitter_") for err in invalid_python_result.get("errors", [])),
                f"invalid Python blocker was not typed: {invalid_python_result}",
            )

            normalized = planner.normalize_planner_decision(
                '{"action":"final","final_answer_lines":[]}',
                goal,
                1,
                {},
            )
            require(normalized.get("final_answer") == "", "final_answer_lines [] was not normalized")
            dirty = planner.normalize_planner_decision(
                'prefix {"action":"final","final_answer":"x"}',
                goal,
                1,
                {},
            )
            require(
                dirty.get("action") == "block"
                and dirty.get("reason") == "INVALID_PLANNER_OUTPUT_NON_JSON_PURE",
                "dirty JSON text was partially extracted",
            )
            fenced = planner.normalize_planner_decision(
                '```json\n{"action":"tool","tool":"repo_read","arguments":{"path":"pkg/example.py"}}\n```',
                goal,
                1,
                {},
            )
            require(
                fenced.get("action") == "block"
                and fenced.get("reason") == "INVALID_PLANNER_OUTPUT_NON_JSON_PURE",
                "markdown-fenced JSON was accepted as a pure planner decision",
            )
            require(
                planner._raw_planner_text_classification(
                    '```json\n{"action":"tool","tool":"repo_read","arguments":{"path":"pkg/example.py"}}\n```'
                )
                == "markdown_fenced_json_non_json",
                "markdown-fenced JSON was not classified as non-pure planner output",
            )
            require(planner.goal_has_write_intent("fix the bug in pkg/example.py"), "apply/fix intent no longer detected")
            require(planner.goal_requests_code_product(goal), "code product intent no longer detected")
            read_only_discovery_goal = (
                "Esegui una discovery read-only mirata alla ricerca di potenziali criticita' "
                "di codice o semantiche nell'area del loop agentico. Vincoli: read-only, "
                "non applicare patch, non scrivere file, non usare repo_apply_patch/repo_write_file. "
                "Devi citare path e funzioni lette, distinguere findings confermati da rischi da testare."
            )
            read_only_classification = planner.semantic_goal_classification(read_only_discovery_goal)
            require(
                read_only_classification.get("class") == "analysis_only",
                f"read-only discovery was incorrectly hard-routed: {read_only_classification}",
            )
            require(
                not planner.goal_requests_code_product(read_only_discovery_goal),
                "read-only negative patch constraint was incorrectly treated as code-product intent",
            )
            require(
                rag_preseed._preplanner_goal_class(read_only_discovery_goal) == "code_security_analysis",
                "preplanner RAG misclassified read-only discovery with negative patch constraints",
            )
            report_only_patch_goal = "Generate a detailed unified diff for pkg/example.py. Do not apply the patch."
            report_only_classification = planner.semantic_goal_classification(report_only_patch_goal)
            require(
                report_only_classification.get("class") == "code_product_report",
                f"report-only positive diff request no longer produces code-product report: {report_only_classification}",
            )
            require(
                rag_preseed._preplanner_goal_class(report_only_patch_goal) == "code_product_report",
                "preplanner RAG no longer distinguishes report-only diff from apply_write",
            )
            require(
                not planner.goal_has_write_intent(
                    "Leggi AGENTS.md nella repo lab e rispondi con una frase. Non modificare nulla."
                ),
                "read-only Italian file inspection was incorrectly classified as apply/write intent",
            )
            require(
                not planner.goal_has_write_intent(
                    "Generate a detailed unified diff for pkg/example.py. Do not apply the patch."
                ),
                "negated apply intent still triggers write guard",
            )
            stale_target = "pkg/stale.md"
            stale_text = "A" * 1200 + "\n"
            (repo_root / stale_target).write_text(stale_text, encoding="utf-8")
            stale_read_result = repo_tools.repo_read({"path": stale_target, "max_chars": 200}, job_root)
            require(
                (stale_read_result.get("items") or [{}])[0].get("truncated") is True,
                "stale fixture was not truncated",
            )
            (repo_root / stale_target).write_text("changed after read\n", encoding="utf-8")
            stale_history = [
                compact_history_row(
                    root=job_root,
                    step=6,
                    tool="repo_read",
                    arguments={"path": stale_target, "max_chars": 200},
                    result=stale_read_result,
                )
            ]
            stale_goal = f"Read {stale_target} and answer from available evidence"
            stale_contract = planner.planner_evidence_contract(stale_goal, stale_history)
            stale_payload, stale_prompt_report = planner._build_planner_user_payload(
                job_id="smoke-stale-md-window",
                state={"goal": stale_goal, "max_steps": 4, "approval_mode": None},
                step=1,
                history=stale_history,
                tool_manifest=tool_manifest,
                evidence_contract=stale_contract,
                planner_memory={"available": True, "source": "smoke", "records": [], "record_count": 0},
                intrinsic_context=intrinsic,
                last_tool_result=stale_history[-1]["tool_result"],
            )
            stale_required = stale_payload.get("required_working_set") or {}
            require(
                not stale_required.get("errors"),
                f"artifact-backed repo_read full context incorrectly blocked planner prompt: {stale_required.get('errors')}",
            )
            stale_reads = stale_required.get("repo_reads") or []
            require(stale_reads, "stale fixture did not produce repo_read working set")
            require(
                stale_reads[0].get("content_source") == "repo_read_artifact_rehydrated_for_prompt",
                f"stale fixture did not reconstruct full context from artifact: {stale_reads[0]}",
            )
            require(
                stale_reads[0].get("content_chars") == len(stale_text),
                "stale fixture did not preserve full artifact content length",
            )
            require(
                not stale_required.get("limits"),
                f"artifact-backed full context was incorrectly downgraded to limits: {stale_required.get('limits')}",
            )
            large_target = "pkg/large.py"
            large_text = "\n".join(
                [f"VALUE_{i} = {i}" for i in range(300)]
                + ["needle_anchor = 123"]
                + [f"TAIL_{i} = {i}" for i in range(300)]
            ) + "\n"
            (repo_root / large_target).write_text(large_text, encoding="utf-8")
            large_read_args = {"path": large_target, "max_chars": 500}
            large_read_result = repo_tools.repo_read(large_read_args, job_root)
            require(
                (large_read_result.get("items") or [{}])[0].get("truncated") is True,
                "large repo_read fixture was not truncated",
            )
            large_history = [
                compact_history_row(
                    root=job_root,
                    step=6,
                    tool="repo_read",
                    arguments=large_read_args,
                    result=large_read_result,
                )
            ]
            large_list_result = {
                "ok": True,
                "tool": "repo_list_files",
                "path": "pkg",
                "count": 300,
                "files": [{"path": f"pkg/generated_{i}.py", "size_bytes": i} for i in range(300)],
            }
            large_history.append(
                compact_history_row(
                    root=job_root,
                    step=7,
                    tool="repo_list_files",
                    arguments={"path": "pkg", "limit": 300},
                    result=large_list_result,
                )
            )
            large_goal = "Analyze pkg/large.py around needle_anchor with recursive context windows"
            large_contract = planner.planner_evidence_contract(large_goal, large_history)
            large_contract["candidate_next_actions"] = [
                {
                    "action": "tool",
                    "tool": "repo_read",
                    "arguments": {"path": "pkg/stale_candidate.py"},
                    "reason": "stale candidate should be suppressed while continuing required context",
                },
                {
                    "action": "tool",
                    "tool": "planner_scratchpad_write",
                    "arguments": {"kind": "code_product_build_state", "text": "{}"},
                    "reason": "out-of-surface candidate should be suppressed while continuing required context",
                },
            ]
            original_large_compact_ratio = planner.AGENTIC_PLANNER_PROMPT_COMPACT_RATIO
            try:
                planner.AGENTIC_PLANNER_PROMPT_COMPACT_RATIO = 0.10
                large_payload, large_prompt_report = planner._build_planner_user_payload(
                    job_id="smoke-code-product-large",
                    state={"goal": large_goal, "max_steps": 4, "approval_mode": None},
                    step=1,
                    history=large_history,
                    tool_manifest=tool_manifest,
                    evidence_contract=large_contract,
                    planner_memory={"available": True, "source": "smoke", "records": [], "record_count": 0},
                    intrinsic_context=intrinsic,
                    last_tool_result=large_history[-1]["tool_result"],
                )
            finally:
                planner.AGENTIC_PLANNER_PROMPT_COMPACT_RATIO = original_large_compact_ratio
            require(large_prompt_report.get("compact_mode") is True, "large prompt did not enter configured compact mode")
            large_reads = (large_payload.get("required_working_set") or {}).get("repo_reads") or []
            require(large_reads, "large prompt pack lacks repo_read window")
            large_item = large_reads[0]
            require(
                large_item.get("full_context_reconstructed") is True,
                f"truncated repo_read full context was not reconstructed: {large_item}",
            )
            require(
                large_item.get("content_source") in {
                    "repo_file_rehydrated_for_prompt_window",
                    "repo_read_artifact_rehydrated_for_prompt",
                },
                f"truncated repo_read used an invalid full-context source: {large_item}",
            )
            large_window = large_item.get("content_window") or {}
            require(large_window.get("schema") == "planner_prompt_context_window.v1", "large window is not SQLite-backed")
            require(large_window.get("document_id"), "large window lacks document_id")
            require(large_window.get("complete") is False, "large window unexpectedly complete")
            require(large_window.get("has_more_after") is True, "large window should advertise following context")
            require("needle_anchor" in large_window.get("text", ""), "large window did not center on goal anchor")
            large_prompt_actions = (large_payload.get("evidence_contract") or {}).get("candidate_next_actions") or []
            require(
                len(large_prompt_actions) == 1 and large_prompt_actions[0].get("tool") == "planner_scratchpad_read",
                f"required context continuation did not isolate candidate_next_actions: {large_prompt_actions}",
            )
            next_window = memory_tools.planner_scratchpad_read(
                {
                    "kind": "prompt_context_window",
                    "document_id": large_window.get("document_id"),
                    "offset": large_window.get("window_end"),
                    "max_chars": 700,
                },
                planner.agent_job_root("smoke-code-product-large"),
            )
            require(next_window.get("ok") is True, f"recursive prompt context read failed: {next_window}")
            next_items = next_window.get("items") or []
            require(next_items, "recursive prompt context read returned no windows")
            require(
                next_items[0].get("window_start") == large_window.get("window_end"),
                "recursive prompt context read did not continue from requested offset",
            )
            require(next_items[0].get("text"), "recursive prompt context read returned empty text")
            planner_requested_window_chars = 131072
            wide_window = memory_tools.planner_prompt_context_store_window(
                planner.agent_job_root("smoke-code-product-large"),
                section="repo_read:pkg/huge.py",
                text="A" * (planner_requested_window_chars * 3),
                query="",
                max_chars=planner_requested_window_chars,
                metadata={"kind": "repo_read_content", "path": "pkg/huge.py"},
            )
            wide_next_window = memory_tools.planner_scratchpad_read(
                {
                    "kind": "prompt_context_window",
                    "document_id": wide_window.get("document_id"),
                    "offset": wide_window.get("window_end"),
                    "max_chars": planner_requested_window_chars,
                },
                planner.agent_job_root("smoke-code-product-large"),
            )
            wide_next_items = wide_next_window.get("items") or []
            require(wide_next_items, f"wide recursive prompt context read returned no windows: {wide_next_window}")
            require(
                wide_next_items[0].get("window_chars") == planner_requested_window_chars,
                f"wide recursive prompt context read ignored planner-requested max_chars: {wide_next_items[0]}",
            )
            long_scratchpad_text = "S" * 20000
            scratchpad_cap_root = planner.agent_job_root("smoke-cap-runtime")
            long_scratchpad_write = memory_tools.planner_scratchpad_write(
                {"kind": "note", "tag": "runtime_cap", "text": long_scratchpad_text},
                scratchpad_cap_root,
            )
            require(long_scratchpad_write.get("ok") is True, f"long scratchpad write failed: {long_scratchpad_write}")
            long_scratchpad_read = memory_tools.planner_scratchpad_read(
                {"tag": "runtime_cap", "limit": 1},
                scratchpad_cap_root,
            )
            long_scratchpad_items = long_scratchpad_read.get("items") or []
            require(long_scratchpad_items, f"long scratchpad read returned no items: {long_scratchpad_read}")
            require(
                long_scratchpad_items[-1].get("text") == long_scratchpad_text,
                "planner_scratchpad_write truncated text instead of preserving planner-provided content",
            )
            next_compact = planner.compact_tool_result_for_planner("planner_scratchpad_read", next_window)
            compact_next_items = next_compact.get("items") or []
            require(compact_next_items, "compact recursive prompt context read returned no items")
            for required_key in (
                "document_id", "section", "window_start", "window_end", "full_chars",
                "window_chars", "complete", "has_more_before", "has_more_after",
                "sha256", "window_sha256", "text",
            ):
                require(
                    required_key in compact_next_items[0],
                    f"compact prompt context window dropped required field {required_key}: {compact_next_items[0]}",
                )
            next_history = large_history + [
                {
                    "step": 8,
                    "decision": {
                        "action": "tool",
                        "tool": "planner_scratchpad_read",
                        "arguments": {
                            "kind": "prompt_context_window",
                            "document_id": large_window.get("document_id"),
                            "offset": large_window.get("window_end"),
                            "max_chars": 700,
                        },
                        "reason": "smoke recursive window",
                    },
                    "tool_result": next_compact,
                }
            ]
            consumed_offsets = planner._prompt_window_consumed_offsets(next_history)
            require(
                consumed_offsets.get(str(large_window.get("document_id"))) == compact_next_items[0].get("window_end"),
                f"consumed offset did not advance from compact history: {consumed_offsets}",
            )
            bad_window_history = large_history + [
                {
                    "step": 9,
                    "decision": {
                        "action": "tool",
                        "tool": "planner_scratchpad_read",
                        "arguments": {
                            "kind": "prompt_context_window",
                            "document_id": large_window.get("document_id"),
                            "offset": large_window.get("window_end"),
                            "max_chars": 700,
                        },
                        "reason": "old broken compact payload",
                    },
                    "tool_result": {
                        "tool": "planner_scratchpad_read",
                        "ok": True,
                        "mode": "prompt_context_window",
                        "items": [{"text_preview": "old broken preview only"}],
                    },
                }
            ]
            metadata_validation = planner.validate_planner_decision_against_evidence(
                large_goal,
                {
                    "action": "tool",
                    "tool": "repo_read",
                    "arguments": {"path": "pkg/large.py", "max_chars": 1000},
                    "reason": "smoke metadata missing",
                },
                bad_window_history,
            )
            require(
                "prompt_context_window_tracking_metadata_missing" in metadata_validation.get("violations", []),
                f"missing prompt window metadata was not blocked: {metadata_validation}",
            )
            already_consumed_validation = planner.validate_planner_decision_against_evidence(
                large_goal,
                {
                    "action": "tool",
                    "tool": "planner_scratchpad_read",
                    "arguments": {
                        "kind": "prompt_context_window",
                        "document_id": large_window.get("document_id"),
                        "offset": large_window.get("window_end"),
                        "max_chars": 700,
                    },
                    "reason": "repeat consumed window",
                },
                next_history,
            )
            require(
                "planner_scratchpad_window_already_successful_without_progress" in already_consumed_validation.get("violations", []),
                f"repeat consumed prompt window was not blocked: {already_consumed_validation}",
            )
            cache_key_a = planner._tool_cache_key(
                "planner_scratchpad_read",
                {
                    "kind": "prompt_context_window",
                    "document_id": large_window.get("document_id"),
                    "offset": large_window.get("window_end"),
                    "max_chars": 700,
                },
            )
            cache_key_b = planner._tool_cache_key(
                "planner_scratchpad_read",
                {
                    "kind": "prompt_context_window",
                    "document_id": large_window.get("document_id"),
                    "offset": compact_next_items[0].get("window_end"),
                    "max_chars": 700,
                },
            )
            require(cache_key_a != cache_key_b, "prompt context cache key ignored window offset")
            ia_view_root = repo_root / ".ia-view-job"
            ia_view_root.mkdir(parents=True, exist_ok=True)
            ia_prompt_path = ia_view_root / "planner-prompts" / "step-001-planner-payload.json"
            ia_stream_path = ia_view_root / "planner-stream" / "step-001.raw.ndjson"
            write_json(
                ia_prompt_path,
                {
                    "schema": "planner_payload_capture.v1",
                    "job_id": "smoke-ia-view",
                    "step": 1,
                    "planner_url": "http://127.0.0.1:11434/api/chat",
                    "planner_model": "smoke-model",
                    "num_ctx_effective": 14336,
                    "prompt_budget_report": {"total_prompt_chars": 1234},
                    "user_payload": {
                        "required_working_set": {"repo_reads": [{"content_window": large_window}]},
                        "optional_context": {"intrinsic_context": {"schema": "planner_intrinsic_context.v1"}},
                        "evidence_contract": {"candidate_next_actions": []},
                    },
                    "planner_payload": {"messages": [{"role": "user", "content": "smoke"}]},
                },
            )
            ia_stream_path.parent.mkdir(parents=True, exist_ok=True)
            ia_stream_path.write_text(
                json.dumps(
                    {
                        "model": "smoke-model",
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "repo_status",
                                        "arguments": {},
                                    }
                                }
                            ],
                        },
                        "done": True,
                        "done_reason": "stop",
                        "prompt_eval_count": 14336,
                        "eval_count": 3,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            ia_raw_tool_path = ia_view_root / "tool-results" / "step-001-planner_scratchpad_read.json"
            ia_raw_tool_path_2 = ia_view_root / "tool-results" / "step-001-02-planner_scratchpad_read.json"
            write_json(ia_raw_tool_path, next_window)
            write_json(ia_raw_tool_path_2, {**next_window, "tool": "planner_scratchpad_read", "substep": 2})
            ia_events = [
                {
                    "time": "smoke",
                    "step": 1,
                    "event_type": "planner_request_started",
                    "message": "smoke request",
                    "payload": {"planner_payload_capture": {"ok": True, "path": str(ia_prompt_path)}},
                },
                {
                    "time": "smoke",
                    "step": 1,
                    "event_type": "planner_decision",
                    "message": "Decision: tool repo_status",
                    "payload": {
                        "action": "tool",
                        "tool": "repo_status",
                        "arguments": {},
                        "native_tool_call": True,
                    },
                },
                {
                    "time": "smoke",
                    "step": 1,
                    "event_type": "tool_result",
                    "message": "smoke tool",
                    "payload": {**next_compact, "substep": 1, "artifact": str(ia_raw_tool_path)},
                },
                {
                    "time": "smoke",
                    "step": 1,
                    "event_type": "tool_result",
                    "message": "smoke tool substep 2",
                    "payload": {**next_compact, "substep": 2, "artifact": str(ia_raw_tool_path_2)},
                },
            ]
            original_view_root = job_html.agent_job_root
            original_view_state = job_html.load_agent_job_state
            original_view_events = job_html.read_agent_events
            original_compact_status = job_html.compact_agent_status
            ia_payload: dict[str, Any] = {}
            ia_dashboard_html = ""
            ia_control_html = ""
            ia_lazy_raw_tool_html = ""
            ia_lazy_terminal_html = ""
            ia_stream_text = ""
            try:
                job_html.agent_job_root = lambda _job_id: ia_view_root
                job_html.load_agent_job_state = lambda _job_id: {
                    "job_id": "smoke-ia-view",
                    "status": "running_agentic",
                    "goal": "smoke view",
                    "current_step": 1,
                    "workspace": str(ia_view_root),
                }
                job_html.read_agent_events = lambda _job_id, _limit=5000: list(ia_events)
                job_html.compact_agent_status = lambda _job_id, include_events=False: {
                    "ok": True,
                    "job_id": "smoke-ia-view",
                    "status": "running_agentic",
                    "goal": "smoke view",
                    "workspace": str(ia_view_root),
                    "final_summary": "smoke summary",
                    "events_tail": list(ia_events) if include_events else [],
                }
                ia_payload = job_html.agent_job_ia_view_payload("smoke-ia-view")
                ia_dashboard_html = job_html.agent_job_html("smoke-ia-view")
                ia_control_html = job_html.agent_job_ia_view_html("smoke-ia-view")
                ia_lazy_raw_tool_html = job_html.agent_job_ia_view_section_html(
                    "smoke-ia-view",
                    "raw_tool_result",
                    step=1,
                )
                ia_lazy_terminal_html = job_html.agent_job_ia_view_section_html(
                    "smoke-ia-view",
                    "openwebui_payload",
                )
                ia_stream_text = job_html.agent_job_planner_stream_text("smoke-ia-view")
            finally:
                job_html.agent_job_root = original_view_root
                job_html.load_agent_job_state = original_view_state
                job_html.read_agent_events = original_view_events
                job_html.compact_agent_status = original_compact_status
            require(ia_payload.get("ok") is True, f"IA view payload failed: {ia_payload}")
            require(
                (ia_payload.get("mutation_check") or {}).get("event_count_changed") is False,
                f"IA view mutated event count: {ia_payload.get('mutation_check')}",
            )
            ia_steps = ia_payload.get("steps") or []
            require(ia_steps and ia_steps[-1].get("prompt_capture", {}).get("available") is True, "IA view did not load planner prompt capture")
            ia_native_stream = ia_steps[-1].get("planner_stream", {}).get("native_stream", {})
            require(
                ia_native_stream.get("native_tool_call_count") == 1,
                f"IA view did not expose native tool_calls from raw ndjson: {ia_native_stream}",
            )
            require("message.tool_calls" in ia_control_html, "IA view HTML did not surface native tool call stream")
            require("data-lazy-url" in ia_control_html, "IA view HTML did not expose lazy-load sections")
            require(
                "planner_scratchpad_read" in ia_lazy_raw_tool_html,
                "IA view lazy raw tool section did not rehydrate tool payload",
            )
            require(
                "HEAVY" not in ia_control_html and "planner_scratchpad_read" not in ia_control_html,
                "IA view initial HTML rendered lazy raw tool payload inline",
            )
            require(
                "openwebui_30b_payload" in ia_lazy_terminal_html or "{}" in ia_lazy_terminal_html,
                "IA view lazy terminal payload endpoint did not render",
            )
            require(
                "Planner request to 11434" not in ia_dashboard_html
                and "Planner stream from 11434" not in ia_dashboard_html
                and "Planner decision and validator" not in ia_dashboard_html,
                "dashboard HTML still duplicates planner control data",
            )
            require("native_tool_call_count" in ia_stream_text, "planner-stream text lacks native summary")
            require("repo_status" in ia_stream_text, "planner-stream text lacks native tool call name")
            require(
                ia_steps[-1].get("raw_tool_result_rehydrated", {}).get("tool") == "planner_scratchpad_read",
                f"IA view did not rehydrate raw tool payload: {ia_steps[-1]}",
            )
            require(
                len(ia_steps[-1].get("history_tool_results_fed_back_to_planner") or []) == 2
                and ia_steps[-1].get("history_tool_result_fed_back_to_planner", {}).get("substep") == 2,
                f"IA view did not preserve same-step tool_result substeps: {ia_steps[-1]}",
            )
            require(
                "payload_count" in ia_lazy_raw_tool_html and "substep" in ia_lazy_raw_tool_html,
                "IA view lazy raw tool section did not expose same-step substep payload list",
            )
            require(
                ia_steps[-1].get("payload_audit", {}).get("compact_payload_complete") is True,
                f"IA view payload audit failed on complete compact payload: {ia_steps[-1].get('payload_audit')}",
            )
            payload_windows = (
                (large_payload.get("optional_context") or {}).get("successful_tool_payload_windows") or []
            )
            list_windows = [
                item for item in payload_windows
                if isinstance(item, dict) and item.get("tool") == "repo_list_files"
            ]
            require(list_windows, "compact mode did not create raw repo_list_files payload window")
            list_window = list_windows[-1].get("window") or {}
            require(
                list_window.get("schema") == "planner_prompt_context_window.v1",
                f"repo_list_files payload was not SQLite-windowed: {list_window}",
            )
            require(list_window.get("document_id"), "repo_list_files payload window lacks document_id")
            require("generated_" in list_window.get("text", ""), "repo_list_files window lacks real payload text")

            budget_files: list[str] = []
            for index in range(8):
                budget_target = (
                    "ia_carmine/cli.py"
                    if index == 0
                    else f"ia_carmine/_shared/window_budget_{index:02d}.py"
                )
                budget_files.append(budget_target)
                budget_path = repo_root / budget_target
                budget_path.parent.mkdir(parents=True, exist_ok=True)
                budget_path.write_text(
                    "\n".join(
                        f"def budget_{index}_{line}(): return {line}"
                        for line in range(80)
                    )
                    + "\n",
                    encoding="utf-8",
                )
            window_budget_history: list[dict[str, Any]] = []
            budget_list_result = {
                "ok": True,
                "tool": "repo_list_files",
                "path": "ia_carmine",
                "count": len(budget_files),
                "total_matches": len(budget_files),
                "limit": len(budget_files),
                "files": [
                    {"path": path, "size_bytes": (repo_root / path).stat().st_size}
                    for path in budget_files
                ],
            }
            window_budget_history.append(
                compact_history_row(
                    root=job_root,
                    step=20,
                    tool="repo_list_files",
                    arguments={"path": "ia_carmine", "limit": len(budget_files)},
                    result=budget_list_result,
                )
            )
            for offset, path in enumerate(budget_files, start=21):
                read_result_for_budget = repo_tools.repo_read(
                    {"path": path, "max_chars": 500},
                    job_root,
                )
                window_budget_history.append(
                    compact_history_row(
                        root=job_root,
                        step=offset,
                        tool="repo_read",
                        arguments={"path": path, "max_chars": 500},
                        result=read_result_for_budget,
                    )
                )
            budget_goal = "Analizza la repo, in particolare IA_CARMINE, e proponi refactor concreto."
            budget_contract = planner.planner_evidence_contract(budget_goal, window_budget_history)
            require(
                planner.goal_requests_code_product(budget_goal),
                "Italian broad concrete refactor request was not classified as code-product",
            )
            require(
                budget_contract.get("code_product_contract", {}).get("required") is True,
                "Italian broad concrete refactor did not require repo_propose_code_edit",
            )
            require(
                budget_contract.get("finalization_contract", {}).get("final_allowed") is False,
                "Italian broad concrete refactor allowed prose-only final before code product",
            )
            budget_code_contract = budget_contract.get("code_product_contract", {})
            candidate_target = str(budget_code_contract.get("candidate_target_file") or "")
            require(
                candidate_target.startswith("ia_carmine/") and not candidate_target.endswith("__init__.py"),
                f"Italian broad concrete refactor selected invalid candidate target: {budget_code_contract}",
            )
            refactor_candidates = budget_contract.get("candidate_next_actions") or []
            require(
                not any(
                    isinstance(item, dict)
                    and item.get("tool") == "repo_propose_code_edit"
                    and not planner._code_product_action_has_complete_payload(item)
                    for item in refactor_candidates
                ),
                f"Italian broad concrete refactor exposed incomplete repo_propose_code_edit candidate: {refactor_candidates}",
            )
            budget_payload_probe, budget_prompt_probe = planner._build_planner_user_payload(
                job_id="smoke-broad-refactor-working-set",
                state={"goal": budget_goal, "max_steps": 20, "approval_mode": "safe_write_lab"},
                step=len(window_budget_history) + 1,
                history=window_budget_history,
                tool_manifest=tool_manifest,
                evidence_contract=budget_contract,
                planner_memory={"available": True, "source": "smoke", "records": [], "record_count": 0},
                intrinsic_context={"schema": "planner_intrinsic_context.v1"},
                last_tool_result=window_budget_history[-1]["tool_result"],
            )
            budget_required = budget_payload_probe.get("required_working_set") or {}
            require(
                candidate_target in (budget_required.get("target_paths") or []),
                f"code-product candidate target missing from required working set: {budget_required}",
            )
            require(
                any(item.get("path") == candidate_target for item in (budget_required.get("repo_reads") or [])),
                f"code-product candidate repo_read window missing from required working set: {budget_required}",
            )
            require(
                budget_prompt_probe.get("required_working_set_errors") == [],
                f"broad refactor working set produced errors: {budget_prompt_probe}",
            )
            bad_proposal_decision = {
                "action": "tool",
                "tool": "repo_propose_code_edit",
                "arguments": {
                    "target_file": candidate_target,
                    "edit_kind": "unified_diff",
                    "rationale": "Smoke invalid proposal without complete diff.",
                },
            }
            first_bad_validation = planner.validate_planner_decision_against_evidence(
                budget_goal,
                bad_proposal_decision,
                window_budget_history,
            )
            require(
                "repo_propose_code_edit_missing_unified_diff" in first_bad_validation.get("violations", []),
                f"missing diff proposal was not rejected: {first_bad_validation}",
            )
            first_guard = planner.controller_guard_result_for_validation(
                first_bad_validation,
                bad_proposal_decision,
            )
            history_after_bad_proposal = window_budget_history + [
                {
                    "step": 90,
                    "decision": {
                        "action": "continue_required",
                        "reason": "smoke rejected bad code-product proposal",
                        "rejected_decision": bad_proposal_decision,
                    },
                    "tool_result": first_guard,
                }
            ]
            require(
                planner.repeated_tool_call_count(
                    history_after_bad_proposal,
                    "repo_propose_code_edit",
                    bad_proposal_decision["arguments"],
                ) == 1,
                "repeat counter did not count rejected repo_propose_code_edit decision",
            )
            second_bad_validation = planner.validate_planner_decision_against_evidence(
                budget_goal,
                bad_proposal_decision,
                history_after_bad_proposal,
            )
            require(
                "code_product_route_shift_required" in second_bad_validation.get("violations", []),
                f"repeated missing-diff proposal did not require route shift: {second_bad_validation}",
            )
            malformed_diff_decision = {
                "action": "tool",
                "tool": "repo_propose_code_edit",
                "arguments": {
                    "target_file": candidate_target,
                    "edit_kind": "unified_diff",
                    "rationale": "Smoke malformed diff should be rejected before tool execution.",
                    "unified_diff": (
                        f"--- a/{candidate_target}\n"
                        f"+++ b/{candidate_target}\n"
                        "@@ -1,1 +1,1 @@\n"
                        "+added line one\n"
                        "+added line two\n"
                    ),
                },
            }
            malformed_diff_validation = planner.validate_planner_decision_against_evidence(
                budget_goal,
                malformed_diff_decision,
                history_after_bad_proposal,
            )
            if importlib.util.find_spec("unidiff") is not None:
                require(
                    "invalid_code_product_candidate" in malformed_diff_validation.get("violations", []),
                    f"malformed unified_diff passed validator: {malformed_diff_validation}",
                )
                require(
                    any(
                        str(v).startswith("repo_propose_code_edit_unified_diff_error:unidiff_parse_")
                        for v in malformed_diff_validation.get("violations", [])
                    ),
                    f"malformed unified_diff rejection did not expose parser error: {malformed_diff_validation}",
                )
            failed_tool_history = history_after_bad_proposal + [
                {
                    "step": 91,
                    "decision": malformed_diff_decision,
                    "tool_result": {
                        "tool": "repo_propose_code_edit",
                        "ok": False,
                        "target_file": candidate_target,
                        "edit_kind": "unified_diff",
                        "errors": ["unidiff_parse_failed:UnidiffParseError"],
                        "summary": "repo_propose_code_edit parse failed",
                    },
                }
            ]
            failed_tool_contract = planner.planner_evidence_contract(budget_goal, failed_tool_history)
            failed_tail = failed_tool_contract.get("validation_rejections_tail") or []
            require(
                any(
                    isinstance(row, dict)
                    and row.get("guard_type") == "tool_result_validation"
                    and "invalid_code_product_candidate" in (row.get("violations") or [])
                    for row in failed_tail
                ),
                f"repo_propose_code_edit ok=false did not feed validation rejections: {failed_tail}",
            )
            route_contract = planner.planner_evidence_contract(budget_goal, history_after_bad_proposal)
            route_code_contract = route_contract.get("code_product_contract", {})
            require(
                route_code_contract.get("route_shift_after_payload_rejection") is True,
                f"route-shift flag missing after invalid code-product proposal: {route_code_contract}",
            )
            route_candidates = route_contract.get("candidate_next_actions") or []
            require(
                route_candidates
                and route_candidates[0].get("tool") == "repo_read"
                and (route_candidates[0].get("arguments") or {}).get("path") == candidate_target
                and "line" in (route_candidates[0].get("arguments") or {}),
                f"route shift did not force a concrete repo_read window candidate: {route_candidates}",
            )
            route_guard = planner.controller_guard_result_for_validation(
                second_bad_validation,
                bad_proposal_decision,
            )
            require(
                "Route shift required" in str(route_guard.get("next_instruction") or ""),
                f"route-shift guard did not expose next_instruction: {route_guard}",
            )
            require(
                route_guard.get("candidate_next_actions")
                and route_guard["candidate_next_actions"][0].get("tool") == "repo_read"
                and (route_guard["candidate_next_actions"][0].get("arguments") or {}).get("path") == candidate_target,
                f"route-shift guard did not expose concrete candidate_next_actions: {route_guard}",
            )
            route_read_args = route_candidates[0].get("arguments") or {}
            route_read_result = repo_tools.repo_read(route_read_args, job_root)
            history_after_route_window = history_after_bad_proposal + [
                compact_history_row(
                    root=job_root,
                    step=91,
                    tool="repo_read",
                    arguments=route_read_args,
                    result=route_read_result,
                )
            ]
            duplicate_route_read_validation = planner.validate_planner_decision_against_evidence(
                budget_goal,
                {"action": "tool", "tool": "repo_read", "arguments": route_read_args},
                history_after_route_window,
            )
            require(
                "repo_read_window_already_successful_without_progress" in duplicate_route_read_validation.get("violations", []),
                f"duplicate repo_read window was not rejected before cache: {duplicate_route_read_validation}",
            )
            fresh_route_read_args = dict(route_read_args)
            fresh_route_read_args["line"] = int(fresh_route_read_args.get("line") or 1) + 1
            fresh_route_read_validation = planner.validate_planner_decision_against_evidence(
                budget_goal,
                {"action": "tool", "tool": "repo_read", "arguments": fresh_route_read_args},
                history_after_route_window,
            )
            require(
                fresh_route_read_validation.get("ok") is True,
                f"different repo_read window was incorrectly rejected: {fresh_route_read_validation}",
            )
            duplicate_route_guard = planner.controller_guard_result_for_validation(
                duplicate_route_read_validation,
                {"action": "tool", "tool": "repo_read", "arguments": route_read_args},
            )
            duplicate_route_candidates = duplicate_route_guard.get("candidate_next_actions") or []
            duplicate_signature = planner._repo_read_window_signature(route_read_args)
            require(
                not any(
                    isinstance(item, dict)
                    and item.get("tool") == "repo_read"
                    and planner._repo_read_window_signature(item.get("arguments") or {}) == duplicate_signature
                    for item in duplicate_route_candidates
                ),
                f"duplicate repo_read guard still exposed the same window: {duplicate_route_guard}",
            )
            contract_after_route_window = planner.planner_evidence_contract(budget_goal, history_after_route_window)
            contract_after_route_candidates = contract_after_route_window.get("candidate_next_actions") or []
            require(
                not any(
                    isinstance(item, dict)
                    and item.get("tool") == "repo_read"
                    and planner._repo_read_window_signature(item.get("arguments") or {}) == duplicate_signature
                    for item in contract_after_route_candidates
                ),
                f"route contract kept duplicate repo_read candidate after window was consumed: {contract_after_route_candidates}",
            )
            sqlite_window_result = {
                "ok": True,
                "tool": "planner_scratchpad_read",
                "mode": "prompt_context_window",
                "count": 1,
                "items": [
                    {
                        "document_id": "prompt-context-smoke",
                        "section": f"repo_read:{candidate_target}",
                        "store": "job_local_sqlite",
                        "metadata": {"kind": "repo_read_content", "path": candidate_target},
                        "text": "x" * 2500,
                        "window_start": 0,
                        "window_end": 2500,
                        "full_chars": 6000,
                        "window_chars": 2500,
                        "complete": False,
                        "has_more_before": False,
                        "has_more_after": True,
                        "sha256": "prompt-context-smoke-full",
                        "window_sha256": "prompt-context-smoke-window-0",
                    }
                ],
            }
            sqlite_window_args = {
                "kind": "prompt_context_window",
                "document_id": "prompt-context-smoke",
                "offset": 0,
                "max_chars": 2500,
            }
            sqlite_window_history = history_after_bad_proposal + [
                compact_history_row(
                    root=job_root,
                    step=92,
                    tool="planner_scratchpad_read",
                    arguments=sqlite_window_args,
                    result=sqlite_window_result,
                )
            ]
            duplicate_sqlite_validation = planner.validate_planner_decision_against_evidence(
                budget_goal,
                {"action": "tool", "tool": "planner_scratchpad_read", "arguments": sqlite_window_args},
                sqlite_window_history,
            )
            require(
                "planner_scratchpad_window_already_successful_without_progress" in duplicate_sqlite_validation.get("violations", []),
                f"duplicate SQLite window was not rejected: {duplicate_sqlite_validation}",
            )
            duplicate_sqlite_guard = planner.controller_guard_result_for_validation(
                duplicate_sqlite_validation,
                {"action": "tool", "tool": "planner_scratchpad_read", "arguments": sqlite_window_args},
            )
            require(
                duplicate_sqlite_guard.get("candidate_next_actions")
                and duplicate_sqlite_guard["candidate_next_actions"][0].get("tool") == "planner_scratchpad_read"
                and (duplicate_sqlite_guard["candidate_next_actions"][0].get("arguments") or {}).get("offset") == 2500,
                f"duplicate SQLite guard did not route to the next offset: {duplicate_sqlite_guard}",
            )
            dunder_history: list[dict[str, Any]] = []
            for offset, path in enumerate(("ia_carmine/__init__.py", "ia_carmine/_shared/__init__.py"), start=40):
                dunder_result = repo_tools.repo_read({"path": path, "max_chars": 6000}, job_root)
                dunder_history.append(
                    compact_history_row(
                        root=job_root,
                        step=offset,
                        tool="repo_read",
                        arguments={"path": path, "max_chars": 6000},
                        result=dunder_result,
                    )
                )
            dunder_contract = planner.planner_evidence_contract(budget_goal, dunder_history)
            dunder_candidates = dunder_contract.get("candidate_next_actions") or []
            dunder_named_decision = planner.normalize_planner_decision(
                json.dumps(
                    {
                        "action": "tool",
                        "name": "repo_propose_code_edit",
                        "arguments": {
                            "target_file": "ia_carmine/__init__.py",
                            "edit_kind": "unified_diff",
                            "unified_diff": (
                                "--- a/ia_carmine/__init__.py\n"
                                "+++ b/ia_carmine/__init__.py\n"
                                "@@ -1 +1,2 @@\n"
                                " \"\"\"Central AI tool package surface.\"\"\"\n"
                                "+from .new_module import new_function\n"
                            ),
                            "rationale": "Smoke invalid broad refactor target.",
                        },
                    },
                    ensure_ascii=False,
                ),
                budget_goal,
                91,
                {},
            )
            require(
                dunder_named_decision.get("tool") == "repo_propose_code_edit",
                f"planner tool alias name was not normalized: {dunder_named_decision}",
            )
            dunder_validation = planner.validate_planner_decision_against_evidence(
                budget_goal,
                dunder_named_decision,
                dunder_history,
            )
            require(
                any(
                    str(violation).startswith("code_product_low_signal_target:")
                    for violation in dunder_validation.get("violations", [])
                ),
                f"broad refactor proposal on dunder target was not rejected: {dunder_validation}",
            )
            require(
                not planner._should_attempt_vulkan_repair(
                    dunder_named_decision,
                    dunder_validation,
                    dunder_history,
                ),
                "semantic low-signal code-product rejection was routed to Vulkan/GPU0 repair",
            )
            require(
                dunder_contract.get("finalization_contract", {}).get("final_allowed") is False,
                "broad concrete refactor with only dunder reads allowed final",
            )
            require(
                not any(
                    isinstance(item, dict)
                    and item.get("tool") == "repo_propose_code_edit"
                    and str((item.get("arguments") or {}).get("target_file") or "").endswith("__init__.py")
                    for item in dunder_candidates
                ),
                f"broad concrete refactor proposed code product on dunder-only evidence: {dunder_candidates}",
            )
            original_prompt_budget = planner.AGENTIC_PLANNER_PROMPT_CHAR_BUDGET
            budget_job_id = "smoke-hard-budget-sqlite-optional-windows"
            try:
                planner.AGENTIC_PLANNER_PROMPT_CHAR_BUDGET = 34000
                budget_payload, budget_report = planner._build_planner_user_payload(
                    job_id=budget_job_id,
                    state={"goal": budget_goal, "max_steps": 20, "approval_mode": "safe_write_lab"},
                    step=len(window_budget_history) + 1,
                    history=window_budget_history,
                    tool_manifest=tool_manifest,
                    evidence_contract=budget_contract,
                    planner_memory={"available": True, "source": "smoke", "records": [], "record_count": 0},
                    intrinsic_context={"schema": "planner_intrinsic_context.v1"},
                    last_tool_result=window_budget_history[-1]["tool_result"],
                )
            finally:
                planner.AGENTIC_PLANNER_PROMPT_CHAR_BUDGET = original_prompt_budget
            require(
                budget_report.get("over_budget") is False,
                f"SQLite-windowed optional payload still triggered hard budget: {budget_report}",
            )
            require(
                budget_report.get("required_working_set_errors") == [],
                f"hard-budget compaction damaged required working set: {budget_report}",
            )
            with sqlite3.connect(planner.agent_job_root(budget_job_id) / "planner_composer.sqlite") as con:
                stored_windows = con.execute(
                    "select count(*) from planner_prompt_context_documents"
                ).fetchone()[0]
            require(stored_windows > 0, "optional windows were omitted without SQLite storage")

        finally:
            for module, original_root in original_repo_tools_roots.items():
                module.LAB_REPO = original_root
            planner.LAB_REPO = original_planner_root
            planner.AGENTIC_PLANNER_NATIVE_TOOLS = original_native_tools
            if has_require_native_tools:
                setattr(planner, planner_require_native_tools_attr, original_require_native_tools)

    print("code_product_contract_smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
