#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def resolve_repo_root(value: str) -> Path:
    root = Path(value).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="output/validation/npu_tool_request_contract_smoke.json")
    parser.add_argument("--markdown-output", default="output/validation/npu_tool_request_contract_smoke.md")
    args = parser.parse_args()

    repo_root = resolve_repo_root(args.repo_root)
    from Tools.ai.run_npu_gpu_deep_review_auditor import extract_npu_tool_requests_from_text

    sample = "NPU audit result.\n\n```json\n{\n  \"tool_requests\": [\n    {\"id\": \"npu_need_syntax\", \"tool\": \"check_python_syntax\", \"reason\": \"Validate syntax before review\", \"args\": {}},\n    {\"id\": \"npu_bad\", \"tool\": \"free_shell\", \"reason\": \"Should be blocked\", \"args\": {}}\n  ]\n}\n```\n"
    valid, errors = extract_npu_tool_requests_from_text(sample, max_requests=8)
    passed = (
        len(valid) == 1
        and valid[0].get("tool") == "check_python_syntax"
        and len(errors) == 1
        and "not allowlisted" in errors[0]
    )
    report = {
        "schema_version": 1,
        "kind": "npu_tool_request_contract_smoke",
        "repo_root": str(repo_root),
        "passed": passed,
        "errors": [] if passed else ["NPU tool request extraction contract failed"],
        "warnings": errors,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "npu_tool_request_count": len(valid),
        "invalid_tool_request_count": len(errors),
        "valid_tool_requests": valid,
        "invalid_tool_request_errors": errors,
        "guardrails": {
            "npu_executes_tools_directly": False,
            "broker_execution_required": True,
            "allowlist_enforced": True,
            "provider_execution_performed": False,
            "patch_application_performed": False,
            "persistent_memory_write_performed": False,
        },
    }
    output = (repo_root / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
    markdown = (repo_root / args.markdown_output).resolve() if not Path(args.markdown_output).is_absolute() else Path(args.markdown_output)
    write_json(output, report)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(
        "# NPU Tool Request Contract Smoke\n\n"
        f"- passed: `{passed}`\n"
        f"- npu_tool_request_count: `{len(valid)}`\n"
        f"- invalid_tool_request_count: `{len(errors)}`\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "passed": passed,
        "output": str(output),
        "markdown": str(markdown),
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "sqlite_write_performed": False,
        "persistent_memory_write_performed": False,
        "npu_tool_request_count": len(valid),
        "invalid_tool_request_count": len(errors),
    }, indent=2, ensure_ascii=False))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
