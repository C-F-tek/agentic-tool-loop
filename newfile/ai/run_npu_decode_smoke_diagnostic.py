#!/usr/bin/env python3
"""Run or plan an explicit NPU/OpenVINO decode smoke diagnostic.

Default mode is report-only and does not execute providers. Real NPU execution is
performed only when ``--run-npu`` is explicitly passed. Outputs are validation
reports and optional packet files only; no Blender runtime, legacy output or full
analysis JSON is touched.
"""
from __future__ import annotations

import argparse
import json
import string
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_MODEL_DIR = Path.home() / "blender" / "npu-models" / "Phi-3.5-mini-instruct-int4-cw-ov"
DEFAULT_PROMPT = (
    "Return exactly this Markdown sentence and nothing else:\n"
    "## NPU Decode Smoke\n"
    "The NPU decode smoke test produced readable text.\n"
)
PRINTABLE = set(string.printable)
HEXISH_CHARS = set("0123456789abcdefABCDEF, .\n\r\t")


def _ensure_repo_imports(repo_root: Path) -> None:
    root_text = str(repo_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    npu_text = str(repo_root / "Tools" / "npu")
    if npu_text not in sys.path:
        sys.path.insert(0, npu_text)


def _default_npu_python(repo_root: Path) -> Path:
    _ensure_repo_imports(repo_root)
    try:
        from Tools.npu.npu_runtime import DEFAULT_NPU_PYTHON  # noqa: PLC0415

        return Path(DEFAULT_NPU_PYTHON)
    except Exception:
        return Path(sys.executable)


def text_metrics(text: str) -> dict[str, Any]:
    total = len(text)
    alpha = sum(1 for char in text if char.isalpha())
    digits = sum(1 for char in text if char.isdigit())
    spaces = sum(1 for char in text if char.isspace())
    printable = sum(1 for char in text if char in PRINTABLE or char.isprintable())
    hexish = sum(1 for char in text if char in HEXISH_CHARS)
    words = [word for word in text.replace("`", " ").replace("#", " ").split() if any(ch.isalpha() for ch in word)]
    return {
        "chars": total,
        "alpha_chars": alpha,
        "digit_chars": digits,
        "space_chars": spaces,
        "printable_chars": printable,
        "hexish_chars": hexish,
        "word_count": len(words),
        "alpha_ratio": round(alpha / total, 4) if total else 0.0,
        "digit_ratio": round(digits / total, 4) if total else 0.0,
        "hexish_ratio": round(hexish / total, 4) if total else 0.0,
        "printable_ratio": round(printable / total, 4) if total else 0.0,
    }


def classify_text(text: str) -> tuple[str, list[str], list[str], dict[str, Any]]:
    metrics = text_metrics(text)
    errors: list[str] = []
    warnings: list[str] = []
    if metrics["chars"] < 40:
        errors.append("decode smoke output is too short")
    if metrics["alpha_ratio"] < 0.18:
        errors.append("alphabetic character ratio is too low")
    if metrics["word_count"] < 6:
        errors.append("word count is too low")
    if metrics["hexish_ratio"] > 0.82 and metrics["alpha_ratio"] < 0.28:
        errors.append("output appears numeric/hex-like rather than natural language")
    if metrics["printable_ratio"] < 0.95:
        errors.append("output contains too many non-printable characters")
    if "NPU Decode Smoke" not in text:
        warnings.append("expected smoke heading was not found")
    return ("usable_text" if not errors else "unusable_output", errors, warnings, metrics)


def run_openvino_npu_smoke(
    *,
    python_exe: Path,
    model_dir: Path,
    device: str,
    prompt: str,
    max_new_tokens: int,
    max_prompt_len: int,
    min_response_len: int,
    timeout: float,
) -> tuple[str, str | None, int | None]:
    """Run NPU smoke in the dedicated NPU Python environment."""

    code = r'''
import json
import sys

payload = json.loads(sys.stdin.read())
try:
    import openvino_genai as ov_genai
    pipe = ov_genai.LLMPipeline(
        payload["model_dir"],
        payload["device"],
        MAX_PROMPT_LEN=int(payload["max_prompt_len"]),
        MIN_RESPONSE_LEN=int(payload["min_response_len"]),
    )
    try:
        text = str(pipe.generate(payload["prompt"], max_new_tokens=int(payload["max_new_tokens"]))).strip()
    finally:
        if hasattr(pipe, "close"):
            pipe.close()
    print(json.dumps({"ok": True, "text": text}, ensure_ascii=False))
except Exception as exc:
    print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
    raise
'''
    payload = {
        "model_dir": str(model_dir),
        "device": device,
        "prompt": prompt,
        "max_new_tokens": max_new_tokens,
        "max_prompt_len": max_prompt_len,
        "min_response_len": min_response_len,
    }
    try:
        result = subprocess.run(
            [str(python_exe), "-c", code],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return "", f"{type(exc).__name__}: {exc}", None

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    parsed: dict[str, Any] = {}
    for line in reversed(stdout.splitlines()):
        try:
            candidate = json.loads(line)
        except Exception:
            continue
        if isinstance(candidate, dict):
            parsed = candidate
            break
    if result.returncode != 0:
        return "", str(parsed.get("error") or stderr or stdout or f"exit code {result.returncode}"), result.returncode
    if parsed.get("ok") is True:
        return str(parsed.get("text") or ""), None, result.returncode
    return "", str(parsed.get("error") or stderr or stdout or "unknown NPU decode smoke error"), result.returncode


def build_provider_envelope(
    *,
    repo_root: Path,
    provider: str,
    model: str,
    prompt: str,
    text: str,
    executed: bool,
    error: str | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    _ensure_repo_imports(repo_root)
    from Tools.npu.pipeline.providers import parse_provider_result  # noqa: PLC0415

    raw_result: dict[str, Any] = {"response": text, "error": error, "usage": metadata}
    parsed = parse_provider_result(raw_result, provider=provider, model=model, executed=executed, allow_json=False)
    return parsed.to_dict()


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve()
    _ensure_repo_imports(repo_root)
    model_dir = Path(args.model_dir).expanduser()
    prompt = args.prompt if args.prompt is not None else DEFAULT_PROMPT
    python_exe = Path(args.python_exe).expanduser() if args.python_exe else _default_npu_python(repo_root)

    provider_execution_performed = False
    text = ""
    execution_error: str | None = None
    raw_exit_code: int | None = None
    executed_at: str | None = None

    if args.run_npu:
        provider_execution_performed = True
        executed_at = datetime.now().isoformat(timespec="seconds")
        text, execution_error, raw_exit_code = run_openvino_npu_smoke(
            python_exe=python_exe,
            model_dir=model_dir,
            device=args.device,
            prompt=prompt,
            max_new_tokens=args.max_new_tokens,
            max_prompt_len=args.max_prompt_len,
            min_response_len=args.min_response_len,
            timeout=args.timeout,
        )

    if text:
        classification, quality_errors, quality_warnings, metrics = classify_text(text)
    elif args.run_npu:
        classification, quality_errors, quality_warnings, metrics = (
            "execution_failed",
            [],
            [],
            text_metrics(text),
        )
    else:
        classification, quality_errors, quality_warnings, metrics = (
            "planned_only",
            [],
            ["NPU execution was not requested; run with --run-npu for a real decode smoke."],
            text_metrics(text),
        )
    errors = list(quality_errors)
    warnings = list(quality_warnings)
    if execution_error:
        errors.append(execution_error)

    provider_envelope = build_provider_envelope(
        repo_root=repo_root,
        provider="openvino_npu",
        model=str(model_dir),
        prompt=prompt,
        text=text,
        executed=provider_execution_performed,
        error=execution_error,
        metadata={
            "python_exe": str(python_exe),
            "device": args.device,
            "max_new_tokens": args.max_new_tokens,
            "max_prompt_len": args.max_prompt_len,
            "min_response_len": args.min_response_len,
            "prompt_chars": len(prompt),
            "executed_at": executed_at,
            "raw_exit_code": raw_exit_code,
        },
    )

    return {
        "schema_version": 1,
        "kind": "npu_decode_smoke_diagnostic",
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "provider_execution_performed": provider_execution_performed,
        "mode": "explicit_npu_decode_smoke" if args.run_npu else "planned_report_only",
        "policy": "explicit_provider_execution_only_no_runtime_changes",
        "provider": "openvino_npu",
        "python_exe": str(python_exe),
        "device": args.device,
        "model_dir": str(model_dir),
        "checks": {
            "classification": classification,
            "usable_for_advisory": classification == "usable_text",
            "metrics": metrics,
            "prompt_chars": len(prompt),
            "output_chars": len(text),
            "provider_envelope": provider_envelope,
            "raw_text_output_path": str(Path(args.text_output)) if args.text_output else None,
            "raw_text_preview": text[:500],
            "promotion_gate": "classification == usable_text and provider_execution_performed == true",
        },
        "raw_text": text,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR))
    parser.add_argument("--python-exe", default="", help="Optional dedicated NPU Python executable. Defaults to Tools.npu.npu_runtime.DEFAULT_NPU_PYTHON.")
    parser.add_argument("--device", default="NPU")
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--run-npu", action="store_true", help="Explicitly execute OpenVINO GenAI on NPU.")
    parser.add_argument("--max-new-tokens", type=int, default=96)
    parser.add_argument("--max-prompt-len", type=int, default=1024)
    parser.add_argument("--min-response-len", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--output", default="output/validation/npu_decode_smoke_diagnostic.json")
    parser.add_argument("--text-output", default="output/ai_packets/npu_decode_smoke_output.md")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    _ensure_repo_imports(repo_root)
    from Tools.validation.report_utils import resolve_output_path, write_json_report  # noqa: PLC0415

    report = build_report(args)
    output = resolve_output_path(repo_root, args.output) if args.output else None
    if args.text_output and report["provider_execution_performed"]:
        text_output = resolve_output_path(repo_root, args.text_output)
        text_output.parent.mkdir(parents=True, exist_ok=True)
        text_output.write_text(str(report.get("raw_text") or "") + "\n", encoding="utf-8")
    rendered = write_json_report(report, output)
    print(rendered, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
