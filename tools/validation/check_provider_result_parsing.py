#!/usr/bin/env python3
"""Validate app-agnostic provider result parsing/reporting helpers."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from report_utils import resolve_output_path, write_json_report


def check_provider_result_parsing(repo_root: Path) -> dict[str, object]:
    root_text = str(repo_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)

    from Tools.npu.pipeline import build_provider_result_report, parse_provider_result  # noqa: PLC0415

    samples = [
        ("ollama", {"response": '{"ok": true}', "eval_count": 8, "prompt_eval_count": 3}, True),
        ("openai_compatible", {"choices": [{"message": {"content": "plain text"}}], "usage": {"total_tokens": 12}}, False),
        ("npu", {"text": '{"device": "NPU"}', "total_duration": 10}, True),
        ("broken", {"error": "simulated failure", "response": ""}, False),
    ]
    parsed = [
        parse_provider_result(raw, provider=provider, model="smoke-model", executed=False, allow_json=allow_json)
        for provider, raw, allow_json in samples
    ]
    report = build_provider_result_report(
        provider="mixed_smoke",
        model="smoke-model",
        results=parsed,
        provider_execution_performed=False,
    )

    errors: list[str] = []
    if parsed[0].json_ok is not True:
        errors.append("ollama-style JSON response should parse as JSON")
    if parsed[1].text != "plain text":
        errors.append("OpenAI-compatible message content should normalize to text")
    if parsed[2].parsed_json != {"device": "NPU"}:
        errors.append("NPU text field should parse JSON payload")
    if parsed[3].ok is not False or not parsed[3].error:
        errors.append("provider error payload should produce a failed parsed result")
    if report.get("provider_execution_performed") is not False:
        errors.append("provider result report must not claim provider execution")
    if report.get("result_count") != 4:
        errors.append("provider result report should include four sample results")
    if report.get("json_ok_count") != 2:
        errors.append("provider result report should count two JSON-capable results")

    return {
        "schema_version": 1,
        "kind": "provider_result_parsing",
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": [],
        "checks": {
            "provider_execution_performed": False,
            "sample_count": len(samples),
            "result_report": report,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = check_provider_result_parsing(repo_root)
    output = resolve_output_path(repo_root, args.output) if args.output else None
    text = write_json_report(report, output)
    print(text, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
