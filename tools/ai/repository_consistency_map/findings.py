"""Finding construction for repository consistency maps."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from Tools.ai.repository_consistency_map.python_inventory import smoke_candidates_for_script


def build_findings(
    *,
    md_refs: list[dict[str, Any]],
    md_commands: list[dict[str, Any]],
    py_inventory: dict[str, dict[str, Any]],
    import_findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for ref in md_refs:
        if ref["kind"] in {"python", "powershell", "markdown"} and not ref["exists"]:
            severity = "high" if ref["kind"] in {"python", "powershell"} else "medium"
            findings.append(
                {
                    "kind": f"md_mentions_missing_{ref['kind']}_path",
                    "severity": severity,
                    "source": ref["source"],
                    "line": ref["line"],
                    "target": ref["raw_ref"],
                    "evidence": ref["snippet"],
                    "recommendation": "Correct the documentation reference or restore the missing target if it is still required.",
                }
            )
    for command in md_commands:
        if not command["script_exists"]:
            findings.append(
                {
                    "kind": "md_python_command_script_missing",
                    "severity": "high",
                    "source": command["source"],
                    "line": command["line"],
                    "target": command["script_raw"],
                    "evidence": command["snippet"],
                    "recommendation": "Update the command to a real script path or remove the obsolete command.",
                }
            )
            continue
        script = command["script_resolved"]
        known_flags = set(py_inventory.get(script, {}).get("argparse_flags", []))
        for flag in command["flags"]:
            if known_flags and flag not in known_flags:
                findings.append(
                    {
                        "kind": "md_cli_arg_not_in_argparse",
                        "severity": "medium",
                        "source": command["source"],
                        "line": command["line"],
                        "target": script,
                        "flag": flag,
                        "known_flags_sample": sorted(known_flags)[:40],
                        "evidence": command["snippet"],
                        "recommendation": "Correct the documented CLI flag or update the script argparse contract in a focused PR.",
                    }
                )
    for item in import_findings:
        findings.append(
            {
                "kind": item["kind"],
                "severity": "high",
                "source": item["source"],
                "line": item["line"],
                "target": item["module"],
                "evidence": f"local import `{item['module']}` cannot be resolved to a repository Python module",
                "recommendation": "Fix the import or add the missing module in a focused code PR.",
            }
        )
    all_py = sorted(py_inventory)
    cited_scripts = sorted({command["script_resolved"] for command in md_commands if command.get("script_exists")})
    for script in cited_scripts:
        if script not in py_inventory:
            continue
        if not smoke_candidates_for_script(script, all_py):
            findings.append(
                {
                    "kind": "documented_python_script_without_obvious_smoke",
                    "severity": "low",
                    "source": script,
                    "line": 0,
                    "target": script,
                    "evidence": "Script is cited by documentation commands but no obvious smoke/check/test file references its stem under Tools/validation.",
                    "recommendation": "Consider adding a smoke validator or documenting why none is needed.",
                }
            )
    return findings


def build_provider_hints(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in findings:
        by_kind[str(finding.get("kind"))].append(finding)
    hints: list[dict[str, Any]] = []
    for kind, items in sorted(by_kind.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        targets = sorted({str(item.get("target") or item.get("source") or "") for item in items if item.get("target") or item.get("source")})
        sources = sorted({str(item.get("source") or "") for item in items if item.get("source")})
        hints.append(
            {
                "kind": kind,
                "count": len(items),
                "severity_counts": dict(Counter(str(item.get("severity")) for item in items)),
                "sample_sources": sources[:12],
                "sample_targets": targets[:12],
                "planner_instruction": "Prioritize concrete patch plans that correct the cited source/target pairs without touching generated output, SQLite, provider settings or Blender runtime.",
            }
        )
    return hints
