#!/usr/bin/env python3
"""Memory/tool routing policy for IA-Carmine runtime planners.

This module does not execute tools directly. It builds a broker-compatible
`tool_requests` packet so the report-only runtime broker can execute allowlisted
tools as controlled instruments.

Memory model:
- persistent memory: consistent/durable project memory, read-only here;
- operational memory: scratch working context under output/**, writable and
  clearable by the broker;
- promotion: never automatic, only proposal after validation evidence.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Tools.ai.code_patch_plan_common import read_json_object
    from Tools.validation.report_utils import write_json_report
except ImportError:
    repo_root_for_import = Path(__file__).resolve().parents[2]
    import sys
    if str(repo_root_for_import) not in sys.path:
        sys.path.insert(0, str(repo_root_for_import))
    from Tools.ai.code_patch_plan_common import read_json_object  # type: ignore
    from Tools.validation.report_utils import write_json_report  # type: ignore


DEFAULT_OUTPUT = "output/validation/agent_memory_routing_policy.json"
DEFAULT_MARKDOWN = "output/validation/agent_memory_routing_policy.md"
DEFAULT_BROKER_REQUEST = "output/ai_runtime_tools/agent_memory_routing_policy_tool_requests.json"
SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def resolve_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def repo_rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except ValueError:
        return str(path)


def safe_id(value: str, fallback: str = "memory_route") -> str:
    text = SAFE_ID_RE.sub("_", str(value or "").strip()).strip("._-")
    return text[:80] or fallback


def split_values(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        for part in str(value).split(","):
            normalized = part.strip()
            if normalized and normalized not in out:
                out.append(normalized)
    return out


def default_persistent_queries(objective: str) -> list[dict[str, str]]:
    objective_lower = objective.lower()
    queries: list[dict[str, str]] = [
        {
            "query": "IA-Carmine project guardrails workflow evidence policy",
            "reason": "Need durable project constraints before planning tool use.",
        }
    ]
    if any(token in objective_lower for token in ("refactor", "codice", "code", "tool", "broker")):
        queries.append(
            {
                "query": "IA-Carmine refactor workflow tool broker memory guardrails",
                "reason": "Need stable refactor/tool-use constraints.",
            }
        )
    if any(token in objective_lower for token in ("npu", "gpu", "planner", "audit")):
        queries.append(
            {
                "query": "GPU NPU planner audit scheduling diagnostics",
                "reason": "Need durable lessons about GPU/NPU planning and audit lanes.",
            }
        )
    return queries


def default_operational_queries(objective: str) -> list[dict[str, str]]:
    return [
        {
            "query": objective[:220],
            "reason": "Need current scratch context related to this objective.",
        },
        {
            "query": "current run tool results broker planner diagnostics",
            "reason": "Need recent runtime observations and tool outputs from the current cycle.",
        },
    ]


def tool_request(
    *,
    request_id: str,
    tool: str,
    reason: str,
    args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": safe_id(request_id),
        "tool": tool,
        "reason": reason,
        "args": dict(args or {}),
    }


def build_memory_tool_requests(args: argparse.Namespace) -> list[dict[str, Any]]:
    persistent_queries = split_values(args.persistent_query) or [item["query"] for item in default_persistent_queries(args.objective)]
    operational_queries = split_values(args.operational_query) or [item["query"] for item in default_operational_queries(args.objective)]
    remember_notes = split_values(args.remember_note)

    requests: list[dict[str, Any]] = [
        tool_request(
            request_id="persistent_memory_status",
            tool="runtime_sqlite_memory",
            reason="Inspect persistent/consistent memory status in read-only mode.",
            args={"action": "status", "scope": "persistent"},
        ),
        tool_request(
            request_id="operational_memory_status",
            tool="runtime_sqlite_memory",
            reason="Inspect scratch operational memory status for the current runtime cycle.",
            args={"action": "status", "scope": "operational"},
        ),
    ]

    if args.clear_operational:
        requests.append(
            tool_request(
                request_id="operational_memory_clear",
                tool="runtime_sqlite_memory",
                reason="Clear scratch operational context because the user requested a fresh working tray.",
                args={"action": "clear_operational", "scope": "operational", "confirm": "clear_operational"},
            )
        )

    for index, query in enumerate(persistent_queries, start=1):
        requests.append(
            tool_request(
                request_id=f"persistent_memory_search_{index:02d}",
                tool="runtime_sqlite_memory",
                reason="Search durable memory read-only for stable project facts and validated lessons.",
                args={"action": "search", "scope": "persistent", "query": query, "limit": args.memory_search_limit},
            )
        )

    for index, query in enumerate(operational_queries, start=1):
        requests.append(
            tool_request(
                request_id=f"operational_memory_search_{index:02d}",
                tool="runtime_sqlite_memory",
                reason="Search scratch operational memory for current-cycle state and recent tool results.",
                args={"action": "search", "scope": "operational", "query": query, "limit": args.memory_search_limit},
            )
        )

    for index, note in enumerate(remember_notes, start=1):
        requests.append(
            tool_request(
                request_id=f"operational_memory_remember_{index:02d}",
                tool="runtime_sqlite_memory",
                reason="Store temporary working context in scratch operational memory only.",
                args={
                    "action": "remember",
                    "scope": "operational",
                    "summary": note[:180],
                    "content": note,
                    "role": "runtime_planner_note",
                    "tag": ["operational_memory", "planner_note"],
                },
            )
        )

    return requests


def build_discovery_tool_requests(args: argparse.Namespace) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = [
        tool_request(
            request_id="agent_memory_inventory",
            tool="build_agent_memory_inventory",
            reason="Build read-only inventory of persistent memory before deciding whether more durable context is needed.",
            args={"objective": args.objective},
        ),
        tool_request(
            request_id="agnostic_tool_inventory",
            tool="build_agent_agnostic_tool_inventory",
            reason="Discover existing reusable tools/helpers before proposing new code or refactors.",
            args={"root": ["Tools/ai", "Tools/validation", "Tools/workflow", "Tools/npu"]},
        ),
        tool_request(
            request_id="transient_request_context",
            tool="build_agent_transient_request_context",
            reason="Create request-scoped context packet from objective and memory notes.",
            args={
                "objective": args.objective,
                "memory_note": [
                    "Persistent memory is read-only unless a later manual promotion PR is explicitly requested.",
                    "Operational memory is scratch context under output/** and may be cleared.",
                    "Runtime tools must be executed only through the report-only broker allowlist.",
                ],
            },
        ),
    ]

    if args.profile in {"refactor", "full_refactor"}:
        requests.extend(
            [
                tool_request(
                    request_id="python_line_count_inventory",
                    tool="build_python_line_count_csv",
                    reason="Build complete Python inventory before choosing refactor candidates.",
                    args={},
                ),
                tool_request(
                    request_id="code_interpreter_report",
                    tool="build_code_interpreter_report",
                    reason="Build static code report over existing tool roots before proposing refactor seams.",
                    args={"input": ["Tools/ai", "Tools/validation", "Tools/workflow", "Tools/npu"]},
                ),

                tool_request(
                    request_id="refactor_duplication_audit",
                    tool="build_refactor_duplication_audit",
                    reason="Audit duplicated helper/function patterns and verify refactor layering before proposing implementation patches.",
                    args={"root": ["Tools/ai", "Tools/validation", "Tools/workflow", "Tools/npu"]},
                ),
                tool_request(
                    request_id="python_syntax_check",
                    tool="check_python_syntax",
                    reason="Validate repository Python syntax as a safe baseline.",
                    args={},
                ),
                tool_request(
                    request_id="gpu_contract_smoke",
                    tool="run_gpu_planner_json_contract_smoke",
                    reason="Validate planner JSON contract helpers before planner integration.",
                    args={},
                ),
            ]
        )

    if args.profile == "full_refactor":
        requests.append(
            tool_request(
                request_id="validation_report_contract",
                tool="check_validation_report_contract",
                reason="Validate existing validation report contracts for evidence quality.",
                args={},
            )
        )

    return requests


def build_promotion_candidates(args: argparse.Namespace) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for note in split_values(args.promotion_candidate):
        candidates.append(
            {
                "summary": note[:220],
                "source": "user_or_planner_candidate",
                "requires_evidence": True,
                "requires_manual_review": True,
                "automatic_promotion_allowed": False,
            }
        )
    return candidates


def build_policy(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    broker_request_path = resolve_path(repo_root, args.broker_request_output)
    memory_requests = build_memory_tool_requests(args)
    discovery_requests = build_discovery_tool_requests(args)
    tool_requests = memory_requests + discovery_requests
    promotion_candidates = build_promotion_candidates(args)

    broker_request = {
        "schema_version": 1,
        "kind": "agent_runtime_tool_request_packet",
        "generated_at": now_iso(),
        "objective": args.objective,
        "profile": args.profile,
        "tool_requests": tool_requests,
        "guardrails": {
            "free_shell_allowed": False,
            "broker_allowlist_required": True,
            "persistent_memory_write_allowed": False,
            "operational_memory_write_allowed_under_output": True,
            "automatic_promotion_allowed": False,
        },
    }
    broker_request_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_report(broker_request, broker_request_path)

    persistent_count = sum(1 for item in tool_requests if item.get("tool") == "runtime_sqlite_memory" and item.get("args", {}).get("scope") == "persistent")
    operational_count = sum(1 for item in tool_requests if item.get("tool") == "runtime_sqlite_memory" and item.get("args", {}).get("scope") == "operational")
    operational_write_count = sum(
        1
        for item in tool_requests
        if item.get("tool") == "runtime_sqlite_memory"
        and item.get("args", {}).get("scope") == "operational"
        and item.get("args", {}).get("action") in {"remember", "clear_operational"}
    )

    return {
        "schema_version": 1,
        "kind": "agent_memory_routing_policy",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "objective": args.objective,
        "profile": args.profile,
        "passed": True,
        "errors": [],
        "warnings": [],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "operational_sqlite_write_performed": False,
        "broker_request_written": repo_rel(broker_request_path, repo_root),
        "memory_plan": {
            "persistent_read_only": True,
            "persistent_query_count": persistent_count,
            "operational_query_or_write_count": operational_count,
            "operational_write_request_count": operational_write_count,
            "tool_request_count": len(tool_requests),
            "tool_requests": tool_requests,
            "promotion_candidates": promotion_candidates,
        },
        "decision": {
            "use_persistent_memory_for": [
                "validated durable project facts",
                "guardrails",
                "historical lessons",
                "stable architecture state",
            ],
            "use_operational_memory_for": [
                "current run state",
                "temporary planner notes",
                "tool results",
                "hypotheses not yet validated",
            ],
            "promotion_policy": "manual_review_after_evidence_only",
            "next_layer": "agent_runtime_tool_broker",
        },
        "guardrails": {
            "free_shell_allowed": False,
            "broker_allowlist_required": True,
            "persistent_memory_read_only": True,
            "persistent_memory_write_performed": False,
            "sqlite_write_performed": False,
            "operational_memory_write_allowed_under_output": True,
            "automatic_persistent_promotion_allowed": False,
            "manual_review_required_for_promotion": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "blender_runtime_touched": False,
            "git_write_performed": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Agent Memory Routing Policy", ""]
    for key in (
        "passed",
        "profile",
        "broker_request_written",
        "provider_execution_performed",
        "patch_application_performed",
        "sqlite_write_performed",
        "persistent_memory_write_performed",
        "operational_sqlite_write_performed",
    ):
        lines.append(f"- {key}: `{report.get(key)}`")
    lines.append("")
    lines.append(f"- Objective: `{report.get('objective')}`")
    lines.append("")
    lines.append("## Memory plan")
    plan = report.get("memory_plan", {})
    for key in (
        "persistent_read_only",
        "persistent_query_count",
        "operational_query_or_write_count",
        "operational_write_request_count",
        "tool_request_count",
    ):
        lines.append(f"- `{key}`: `{plan.get(key)}`")
    lines.append("")
    lines.append("## Tool requests")
    lines.append("")
    for item in plan.get("tool_requests", []):
        lines.append(f"- `{item.get('id')}` -> `{item.get('tool')}`: {item.get('reason')}")
    lines.append("")
    lines.append("## Guardrails")
    lines.append("")
    for key, value in report.get("guardrails", {}).items():
        lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--objective", required=True)
    parser.add_argument("--profile", choices=("basic", "refactor", "full_refactor"), default="basic")
    parser.add_argument("--persistent-query", action="append", default=[])
    parser.add_argument("--operational-query", action="append", default=[])
    parser.add_argument("--remember-note", action="append", default=[])
    parser.add_argument("--promotion-candidate", action="append", default=[])
    parser.add_argument("--memory-search-limit", type=int, default=8)
    parser.add_argument("--clear-operational", action="store_true")
    parser.add_argument("--broker-request-output", default=DEFAULT_BROKER_REQUEST)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = build_policy(args)
    output = resolve_path(repo_root, args.output)
    markdown = resolve_path(repo_root, args.markdown_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    write_json_report(report, output)
    markdown.write_text(render_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "output": str(output),
                "markdown": str(markdown),
                "broker_request": report["broker_request_written"],
                "tool_request_count": report["memory_plan"]["tool_request_count"],
                "persistent_query_count": report["memory_plan"]["persistent_query_count"],
                "operational_query_or_write_count": report["memory_plan"]["operational_query_or_write_count"],
                "provider_execution_performed": report["provider_execution_performed"],
                "patch_application_performed": report["patch_application_performed"],
                "sqlite_write_performed": report["sqlite_write_performed"],
                "persistent_memory_write_performed": report["persistent_memory_write_performed"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())