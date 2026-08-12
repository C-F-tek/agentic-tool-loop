"""Build Full0To10 repository quality packet."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import FINDINGS_JSON, INVENTORY_JSON, PACKET_JSON, PACKET_MD, SAFETY_FLAGS, TOOL_PLAN_JSON
from .findings import build_findings
from .inventory import build_inventory
from .json_reader import read_json_file
from .md_reader import read_markdown
from .outputs import write_user_output
from .paths import ensure_dir, repo_relative, resolve_path
from .py_reader import read_python
from .render import render_packet
from .tool_plan import build_tool_plan


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_quality_inputs(repo_root: Path, inventory: dict[str, Any]) -> list[dict[str, Any]]:
    reads: list[dict[str, Any]] = []
    for item in inventory["items"]:
        if not item["exists"]:
            continue
        path = resolve_path(repo_root, item["path"])
        if item["kind"] == "markdown":
            reads.append(read_markdown(repo_root, path))
        elif item["kind"] == "python":
            reads.append(read_python(repo_root, path))
        elif item["kind"] == "json":
            reads.append(read_json_file(repo_root, path))
    return reads


def build_repo_quality_packet(
    repo_root: Path,
    output_dir: Path,
    input_paths: list[str],
    output_file: str,
    tool: str,
    request: str,
    write_output: bool,
    allow_output_outside_output: bool,
    max_files: int,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output_dir = ensure_dir(output_dir)
    inventory = build_inventory(repo_root, input_paths, max_files)
    reads = read_quality_inputs(repo_root, inventory)
    findings = build_findings(reads, inventory)
    tool_plan = build_tool_plan(tool, request, inventory)

    packet: dict[str, Any] = {
        "kind": "full0to10_repo_quality_packet",
        "passed": inventory["passed"] and findings["passed"] and tool_plan["passed"],
        "request": request,
        "inventory": inventory,
        "reads": reads,
        "findings": findings,
        "tool_plan": tool_plan,
        "errors": inventory.get("errors", []) + findings.get("errors", []),
        "warnings": [],
    }
    packet.update(SAFETY_FLAGS)

    markdown = render_packet(packet)
    output_manifest = write_user_output(repo_root, output_file, packet, markdown, write_output, allow_output_outside_output)
    packet["user_output"] = output_manifest
    packet["source_writes_performed"] = bool(output_manifest["written"] and not output_manifest["under_output"])

    files = {
        "packet": output_dir / PACKET_JSON,
        "markdown": output_dir / PACKET_MD,
        "inventory": output_dir / INVENTORY_JSON,
        "findings": output_dir / FINDINGS_JSON,
        "tool_plan": output_dir / TOOL_PLAN_JSON,
    }
    write_json(files["packet"], packet)
    files["markdown"].write_text(markdown, encoding="utf-8")
    write_json(files["inventory"], inventory)
    write_json(files["findings"], findings)
    write_json(files["tool_plan"], tool_plan)
    packet["outputs"] = {role: repo_relative(path, repo_root) for role, path in files.items()}
    return packet
