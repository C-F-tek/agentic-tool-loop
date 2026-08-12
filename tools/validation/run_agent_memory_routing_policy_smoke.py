#!/usr/bin/env python3
"""Smoke-test memory routing policy and broker execution."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def resolve_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_command(repo_root: Path, command: list[str]) -> tuple[int, str, str]:
    completed = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    return completed.returncode, completed.stdout[-12000:], completed.stderr[-12000:]


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("kind") != "agent_memory_routing_policy":
        errors.append("unexpected policy kind")
    if policy.get("passed") is not True:
        errors.append("policy did not pass")
    plan = policy.get("memory_plan", {})
    requests = plan.get("tool_requests", [])
    if not isinstance(requests, list) or len(requests) < 8:
        errors.append("expected at least 8 tool requests")
    if not any(item.get("tool") == "runtime_sqlite_memory" and item.get("args", {}).get("scope") == "persistent" for item in requests):
        errors.append("missing persistent runtime_sqlite_memory request")
    if not any(item.get("tool") == "runtime_sqlite_memory" and item.get("args", {}).get("scope") == "operational" for item in requests):
        errors.append("missing operational runtime_sqlite_memory request")
    if not any(item.get("tool") == "build_agent_transient_request_context" for item in requests):
        errors.append("missing transient request context request")
    if any(item.get("tool") == "shell" for item in requests):
        errors.append("policy must not request shell")
    for key in ("provider_execution_performed", "patch_application_performed", "sqlite_write_performed", "persistent_memory_write_performed"):
        if policy.get(key) is not False:
            errors.append(f"{key} must be false")
    if policy.get("guardrails", {}).get("automatic_persistent_promotion_allowed") is not False:
        errors.append("automatic persistent promotion must be disabled")
    return errors


def validate_broker(broker: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if broker.get("kind") != "agent_runtime_tool_broker":
        errors.append("unexpected broker kind")
    if broker.get("passed") is not True:
        errors.append("broker report did not pass")
    if broker.get("blocked_tool_count") != 0:
        errors.append("policy-generated broker request should not contain blocked tools")
    if broker.get("tool_execution_count", 0) < 8:
        errors.append("expected at least 8 executed tools")
    if broker.get("provider_execution_performed") is not False:
        errors.append("provider execution must be false")
    if broker.get("patch_application_performed") is not False:
        errors.append("patch application must be false")
    if broker.get("sqlite_write_performed") is not False:
        errors.append("protected sqlite_write_performed must be false")
    if broker.get("persistent_memory_write_performed") is not False:
        errors.append("persistent memory writes must be false")
    if broker.get("operational_sqlite_write_performed") is not True:
        errors.append("operational sqlite write should be true because policy writes one scratch note")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default=None)
    parser.add_argument("--markdown-output", default=None)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    run_stamp = stamp()
    policy_output = resolve_path(repo_root, f"output/validation/agent_memory_routing_policy_smoke_{run_stamp}.json")
    policy_md = resolve_path(repo_root, f"output/validation/agent_memory_routing_policy_smoke_{run_stamp}.md")
    broker_request = resolve_path(repo_root, f"output/ai_runtime_tools/agent_memory_routing_policy_smoke_{run_stamp}_tool_requests.json")
    broker_output = resolve_path(repo_root, f"output/validation/agent_memory_routing_policy_broker_smoke_{run_stamp}.json")
    broker_md = resolve_path(repo_root, f"output/validation/agent_memory_routing_policy_broker_smoke_{run_stamp}.md")
    final_output = resolve_path(repo_root, args.output or f"output/validation/agent_memory_routing_policy_smoke_result_{run_stamp}.json")
    final_md = resolve_path(repo_root, args.markdown_output or f"output/validation/agent_memory_routing_policy_smoke_result_{run_stamp}.md")

    policy_cmd = [
        sys.executable,
        "Tools/ai/agent_memory_routing_policy.py",
        "--repo-root",
        ".",
        "--objective",
        "Refactor the runtime broker and memory tools using existing IA-Carmine tools without wasting generated artifacts.",
        "--profile",
        "refactor",
        "--remember-note",
        "Smoke: operational scratch memory stores current planner working context only.",
        "--promotion-candidate",
        "Potential durable lesson: runtime tools should be brokered through allowlists.",
        "--broker-request-output",
        str(broker_request),
        "--output",
        str(policy_output),
        "--markdown-output",
        str(policy_md),
    ]
    policy_code, policy_stdout, policy_stderr = run_command(repo_root, policy_cmd)
    policy_report = read_json(policy_output) if policy_output.exists() else {}

    broker_cmd = [
        sys.executable,
        "Tools/ai/agent_runtime_tool_broker.py",
        "--repo-root",
        ".",
        "--request-file",
        str(broker_request),
        "--tool-output-dir",
        f"output/ai_runtime_tools/memory_routing_policy_smoke_{run_stamp}",
        "--timeout-seconds",
        "300",
        "--output",
        str(broker_output),
        "--markdown-output",
        str(broker_md),
    ]
    broker_code, broker_stdout, broker_stderr = run_command(repo_root, broker_cmd)
    broker_report = read_json(broker_output) if broker_output.exists() else {}

    errors = []
    if policy_code != 0:
        errors.append(f"policy command returned {policy_code}")
    if broker_code != 0:
        errors.append(f"broker command returned {broker_code}")
    errors.extend(validate_policy(policy_report))
    errors.extend(validate_broker(broker_report))

    report = {
        "schema_version": 1,
        "kind": "agent_memory_routing_policy_smoke",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": [],
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "policy_output": str(policy_output),
        "broker_request": str(broker_request),
        "broker_output": str(broker_output),
        "policy_returncode": policy_code,
        "broker_returncode": broker_code,
        "policy_stdout_tail": policy_stdout,
        "policy_stderr_tail": policy_stderr,
        "broker_stdout_tail": broker_stdout,
        "broker_stderr_tail": broker_stderr,
        "policy_summary": {
            "tool_request_count": policy_report.get("memory_plan", {}).get("tool_request_count"),
            "persistent_query_count": policy_report.get("memory_plan", {}).get("persistent_query_count"),
            "operational_query_or_write_count": policy_report.get("memory_plan", {}).get("operational_query_or_write_count"),
        },
        "broker_summary": {
            "tool_request_count": broker_report.get("tool_request_count"),
            "tool_execution_count": broker_report.get("tool_execution_count"),
            "blocked_tool_count": broker_report.get("blocked_tool_count"),
            "operational_sqlite_write_performed": broker_report.get("operational_sqlite_write_performed"),
        },
    }
    write_json(final_output, report)
    final_md.parent.mkdir(parents=True, exist_ok=True)
    final_md.write_text(
        "\n".join(
            [
                "# Agent Memory Routing Policy Smoke",
                "",
                f"- Passed: `{report['passed']}`",
                f"- Policy return code: `{policy_code}`",
                f"- Broker return code: `{broker_code}`",
                f"- Policy tool requests: `{report['policy_summary']['tool_request_count']}`",
                f"- Broker tool executions: `{report['broker_summary']['tool_execution_count']}`",
                f"- Broker blocked tools: `{report['broker_summary']['blocked_tool_count']}`",
                f"- Operational SQLite write performed: `{report['broker_summary']['operational_sqlite_write_performed']}`",
                f"- Provider execution performed: `{report['provider_execution_performed']}`",
                f"- Patch application performed: `{report['patch_application_performed']}`",
                f"- Persistent memory write performed: `{report['persistent_memory_write_performed']}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "output": str(final_output),
                "markdown": str(final_md),
                "policy_tool_request_count": report["policy_summary"]["tool_request_count"],
                "broker_tool_execution_count": report["broker_summary"]["tool_execution_count"],
                "broker_blocked_tool_count": report["broker_summary"]["blocked_tool_count"],
                "operational_sqlite_write_performed": report["broker_summary"]["operational_sqlite_write_performed"],
                "provider_execution_performed": False,
                "patch_application_performed": False,
                "persistent_memory_write_performed": False,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

