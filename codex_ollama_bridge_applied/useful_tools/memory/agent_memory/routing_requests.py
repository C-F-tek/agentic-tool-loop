"""Broker request builders for agent memory routing."""

from __future__ import annotations

import argparse
from typing import Any

from .common import safe_identifier, split_csv_values

DEFAULT_OUTPUT = "output/validation/agent_memory_routing_policy.json"
DEFAULT_MARKDOWN = "output/validation/agent_memory_routing_policy.md"
DEFAULT_BROKER_REQUEST = ""


def safe_id(value: str, default: str = "memory_route") -> str:
    return safe_identifier(value, default)


def split_values(values: list[str]) -> list[str]:
    return split_csv_values(values)

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
    persistent_queries = split_values(args.persistent_query) or [
        item["query"] for item in default_persistent_queries(args.objective)
    ]
    operational_queries = split_values(args.operational_query) or [
        item["query"] for item in default_operational_queries(args.objective)
    ]
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
                args={
                    "action": "clear_operational",
                    "scope": "operational",
                    "confirm": "clear_operational",
                },
            )
        )

    for index, query in enumerate(persistent_queries, start=1):
        requests.append(
            tool_request(
                request_id=f"persistent_memory_search_{index:02d}",
                tool="runtime_sqlite_memory",
                reason="Search durable memory read-only for stable project facts and validated lessons.",
                args={
                    "action": "search",
                    "scope": "persistent",
                    "query": query,
                    "limit": args.memory_search_limit,
                },
            )
        )

    for index, query in enumerate(operational_queries, start=1):
        requests.append(
            tool_request(
                request_id=f"operational_memory_search_{index:02d}",
                tool="runtime_sqlite_memory",
                reason="Search scratch operational memory for current-cycle state and recent tool results.",
                args={
                    "action": "search",
                    "scope": "operational",
                    "query": query,
                    "limit": args.memory_search_limit,
                },
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
            args={"root": ["tools/ai", "tools/validation", "tools/workflow", "tools/npu"]},
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
                    args={
                        "input": [
                            "tools/ai",
                            "tools/validation",
                            "tools/workflow",
                            "tools/npu",
                        ]
                    },
                ),
                tool_request(
                    request_id="refactor_duplication_audit",
                    tool="refactor_duplication_audit",
                    reason="Audit duplicated helper/function patterns and verify refactor layering before proposing implementation patches.",
                    args={
                        "root": [
                            "tools/ai",
                            "tools/validation",
                            "tools/workflow",
                            "tools/npu",
                        ]
                    },
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
