from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git",
    ".runs",
    "__pycache__",
    "openwebui-data",
    "venvs",
    ".venv",
    "npu-models",
}
SKIP_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".bin",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".exr",
    ".blend",
}
MAX_SCAN_BYTES = 2_000_000


@dataclass(frozen=True)
class Replacement:
    pattern: str
    replacement: str
    flags: int = 0


@dataclass(frozen=True)
class Rule:
    name: str
    path: str
    replacements: tuple[Replacement, ...]


RULES: tuple[Rule, ...] = (
    Rule(
        name="macro_runner_drop_expect_tool",
        path="macro_runtine_test/run_loop_payload_completo.ps1",
        replacements=(
            Replacement(r'(?m)^\s*\[string\]\$ExpectTool = "",\r?\n', ""),
            Replacement(
                r'(?s)\r?\nif \(\$ExpectTool\) \{\r?\n'
                r'\s*\$env:LOOP_PAYLOAD_EXPECT_TOOL = \$ExpectTool\r?\n'
                r'\} else \{\r?\n'
                r'\s*Remove-Item Env:LOOP_PAYLOAD_EXPECT_TOOL -ErrorAction SilentlyContinue\r?\n'
                r'\}',
                "",
            ),
            Replacement(r'(?m)^Remove-Item Env:LOOP_PAYLOAD_EXPECT_TOOL -ErrorAction SilentlyContinue\r?\n', ""),
            Replacement(r'(?m)^if \(\$ExpectTool\) \{ Write-Host "ExpectTool: \$ExpectTool" \}\r?\n', ""),
        ),
    ),
    Rule(
        name="macro_readme_drop_expect_tool",
        path="macro_runtine_test/README.md",
        replacements=(
            Replacement(r"`pytest\.ini` limita `testpaths` a `tests services`\.", "`pytest.ini` limita `testpaths` a `services`."),
            Replacement(
                r'(?s)\r?\n```powershell\r?\n'
                r'\.\\macro_runtine_test\\run_loop_payload_completo\.ps1 `\r?\n'
                r'\s+-Request "leggi il file README\.md e usa evidenza inline" `\r?\n'
                r'\s+-ExpectTool repo_read\r?\n'
                r'```\r?\n',
                "\n",
            ),
            Replacement(r'(?m)^`-ExpectTool` non viene passato come dispatch interno e non forza il planner\.\r?\n', ""),
        ),
    ),
    Rule(
        name="macro_test_drop_expected_tool",
        path="macro_runtine_test/test_loop_payload_completo.py",
        replacements=(
            Replacement(r'(?m)^    expect_tool = str\(os\.environ\.get\("LOOP_PAYLOAD_EXPECT_TOOL"\) or ""\)\.strip\(\)\r?\n', ""),
            Replacement(r'(?m)^            "expect_tool": expect_tool,\r?\n', ""),
            Replacement(
                r'(?s)\r?\n        tool_names = set\(preflight\["runtime_tools"\]\)\r?\n'
                r'        if expect_tool and expect_tool not in tool_names:\r?\n'
                r'            raise AssertionError\(f"LOOP_PAYLOAD_EXPECT_TOOL not in dynamic runtime surface: \{expect_tool\}"\)\r?\n',
                "\n",
            ),
            Replacement(r'(?m)^            "expected_tool": expect_tool,\r?\n', ""),
            Replacement(r'(?m)^    target_tool: str,\r?\n', ""),
            Replacement(r'(?m)^        target_tool=target_tool,\r?\n', ""),
            Replacement(r'(?m)^                target_tool=expect_tool,\r?\n', ""),
        ),
    ),
    Rule(
        name="terminal_response_drop_public_duplicate_aliases",
        path="services/aicarmine_broker/application/job/terminal_response.py",
        replacements=(
            Replacement(
                r'(?s)\r?\n    context_alias = \{\r?\n'
                r'        "schema": "agentic_terminal_context_alias\.v1",\r?\n'
                r'        "alias_of": "tool_context_for_30b",\r?\n'
                r'        "same_payload": True,\r?\n'
                r'    \}\r?\n',
                "\n",
            ),
            Replacement(r'(?m)^        "job_ok": status == "completed",\r?\n', ""),
            Replacement(r'(?m)^        "tool_result_for": public_tool,\r?\n', ""),
            Replacement(r'(?m)^        "called_by_30b": public_tool,\r?\n', ""),
            Replacement(r'(?m)^        "agent_context_for_30b": context_alias,\r?\n', ""),
            Replacement(r'(?m)^        "structured_context_for_30b": context_alias,\r?\n', ""),
            Replacement(r'(?m)^        "structured_result_for_30b": context_alias,\r?\n', ""),
        ),
    ),
)


SCAN_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("macro_expect_tool", "macro_runtine_test", r"ExpectTool|LOOP_PAYLOAD_EXPECT_TOOL|expect_tool|expected_tool"),
    ("macro_target_tool_runtime_driver", "macro_runtine_test", r"target_tool\s*[:=]"),
    ("public_context_aliases", "services", r"agent_context_for_30b|structured_context_for_30b|structured_result_for_30b"),
    ("public_duplicate_tool_identity", "services", r"tool_result_for|called_by_30b"),
    ("public_job_ok_duplicate", "services", r"\bjob_ok\b"),
    (
        "bridge_duplicate_materializers",
        "services/vulkan_bridge",
        r"build_materialization_report|_agentic_v9_build_payload_index_for_30b|_agentic_v9_build_external_tool_context_for_30b",
    ),
)


def apply_rule(text: str, rule: Rule) -> tuple[str, list[dict[str, object]]]:
    out = text
    changes: list[dict[str, object]] = []
    for index, replacement in enumerate(rule.replacements):
        out, count = re.subn(
            replacement.pattern,
            replacement.replacement,
            out,
            flags=replacement.flags,
        )
        changes.append({
            "replacement_index": index,
            "count": count,
        })
    return out, changes


def selected_rules(names: Iterable[str]) -> tuple[Rule, ...]:
    wanted = tuple(name for name in names if name)
    if not wanted:
        return RULES
    known = {rule.name for rule in RULES}
    missing = [name for name in wanted if name not in known]
    if missing:
        raise SystemExit(f"unknown rule(s): {', '.join(missing)}")
    return tuple(rule for rule in RULES if rule.name in wanted)


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply explicit mechanical runtime pruning rules.")
    parser.add_argument("--rule", action="append", default=[], help="run only one named rule; repeatable")
    parser.add_argument("--list-rules", action="store_true", help="print rule names and exit")
    args = parser.parse_args()

    if args.list_rules:
        print(json.dumps([rule.name for rule in RULES], ensure_ascii=False, indent=2))
        return 0

    report: dict[str, object] = {
        "schema": "mechanical_runtime_prune_report.v1",
        "mode": "apply",
        "root": str(ROOT),
        "rules": [],
    }
    any_changed = False
    for rule in selected_rules(args.rule):
        path = ROOT / rule.path
        if not path.exists():
            raise SystemExit(f"missing rule target: {path}")
        before = path.read_text(encoding="utf-8", errors="replace")
        after, changes = apply_rule(before, rule)
        changed = before != after
        any_changed = any_changed or changed
        if changed:
            path.write_text(after, encoding="utf-8", newline="")
        report["rules"].append({
            "name": rule.name,
            "path": rule.path,
            "changed": changed,
            "changes": changes,
        })

    report["changed"] = any_changed
    scan_report: list[dict[str, object]] = []
    for name, relative_root, pattern in SCAN_PATTERNS:
        scan_root = ROOT / relative_root
        matches: list[dict[str, object]] = []
        if scan_root.exists():
            paths = [scan_root] if scan_root.is_file() else sorted(scan_root.rglob("*"))
            regex = re.compile(pattern)
            for path in paths:
                if not path.is_file():
                    continue
                if any(part in SKIP_DIRS for part in path.parts):
                    continue
                if path.suffix.lower() in SKIP_SUFFIXES:
                    continue
                try:
                    if path.stat().st_size > MAX_SCAN_BYTES:
                        continue
                except OSError:
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                for line_number, line in enumerate(text.splitlines(), start=1):
                    if regex.search(line):
                        matches.append({
                            "path": str(path.relative_to(ROOT)),
                            "line": line_number,
                            "text": line.strip()[:240],
                        })
        scan_report.append({
            "name": name,
            "root": relative_root,
            "pattern": pattern,
            "count": len(matches),
            "matches": matches[:200],
        })
    report["remaining_pattern_scan"] = scan_report
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
