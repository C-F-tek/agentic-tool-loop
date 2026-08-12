#!/usr/bin/env python3
"""Validate the reusable AI model JSON parser with deterministic samples."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def import_model_json(repo_root: Path) -> dict[str, Any]:
    """Import the parser module after ensuring the repository root is importable."""
    import sys

    root_text = str(repo_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)

    from Tools.ai.model_json import (  # type: ignore
        ModelJsonParseError,
        extract_json_candidate,
        parse_model_json,
        parse_model_json_object,
        repair_common_model_json,
        strip_markdown_json_fence,
    )
    from Tools.npu.ollama_runtime import parse_json_response, strip_json_fence  # type: ignore

    return {
        "ModelJsonParseError": ModelJsonParseError,
        "extract_json_candidate": extract_json_candidate,
        "parse_json_response": parse_json_response,
        "parse_model_json": parse_model_json,
        "parse_model_json_object": parse_model_json_object,
        "repair_common_model_json": repair_common_model_json,
        "strip_json_fence": strip_json_fence,
        "strip_markdown_json_fence": strip_markdown_json_fence,
    }


def run_case(name: str, func: Any, text: str, expected: Any = None, *, expect_error: bool = False) -> dict[str, Any]:
    """Run one parser test case."""
    try:
        value = func(text)
        passed = not expect_error and (value == expected if expected is not None else True)
        return {"name": name, "passed": passed, "value": value, "expected": expected, "expect_error": expect_error}
    except Exception as exc:
        passed = expect_error
        return {"name": name, "passed": passed, "error_type": type(exc).__name__, "error": str(exc), "expect_error": expect_error}


def check_model_json(repo_root: Path) -> dict[str, Any]:
    """Run deterministic checks for model JSON parsing."""
    mod = import_model_json(repo_root)
    parse_model_json = mod["parse_model_json"]
    parse_model_json_object = mod["parse_model_json_object"]
    parse_json_response = mod["parse_json_response"]
    extract_json_candidate = mod["extract_json_candidate"]
    strip_markdown_json_fence = mod["strip_markdown_json_fence"]
    strip_json_fence = mod["strip_json_fence"]
    repair_common_model_json = mod["repair_common_model_json"]

    cases = [
        run_case("plain_object", parse_model_json_object, '{"ok": true}', {"ok": True}),
        run_case("markdown_fenced_object", parse_model_json_object, '```json\n{"ok": true}\n```', {"ok": True}),
        run_case("surrounding_text_object", parse_model_json_object, 'Here is the JSON:\n{"ok": true, "items": [1, 2]}\nDone.', {"ok": True, "items": [1, 2]}),
        run_case("trailing_comma_repair", parse_model_json_object, '{"ok": true,}', {"ok": True}),
        run_case("line_comment_repair", parse_model_json_object, '{\n  // model note\n  "ok": true\n}', {"ok": True}),
        run_case("array_allowed", parse_model_json, '[{"a": 1}, {"a": 2}]', [{"a": 1}, {"a": 2}]),
        run_case("array_rejected_by_object_parser", parse_model_json_object, '[1, 2, 3]', expect_error=True),
        run_case("invalid_text_fails", parse_model_json, 'not json at all', expect_error=True),
        run_case("ollama_parse_json_response_plain", parse_json_response, '{"ok": true}', {"ok": True}),
        run_case("ollama_parse_json_response_fenced", parse_json_response, '```json\n{"ok": true}\n```', {"ok": True}),
        run_case("ollama_parse_json_response_surrounding_text", parse_json_response, 'prefix {"ok": true} suffix', {"ok": True}),
        run_case("ollama_parse_json_response_invalid_raises_jsondecode", parse_json_response, 'not json at all', expect_error=True),
    ]

    direct_checks = {
        "strip_markdown_json_fence": strip_markdown_json_fence('```json\n{"a": 1}\n```') == '{"a": 1}',
        "strip_json_fence_legacy_wrapper": strip_json_fence('```json\n{"a": 1}\n```') == '{"a": 1}',
        "extract_json_candidate": extract_json_candidate('prefix {"a": [1, 2]} suffix') == '{"a": [1, 2]}',
        "repair_common_model_json": repair_common_model_json('{"a": 1,}') == '{"a": 1}',
    }

    errors = [case["name"] for case in cases if not case["passed"]]
    errors.extend(name for name, passed in direct_checks.items() if not passed)

    return {
        "schema_version": 1,
        "kind": "ai_model_json",
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": [],
        "case_count": len(cases),
        "cases": cases,
        "direct_checks": direct_checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = check_model_json(repo_root)
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
