#!/usr/bin/env python3
"""Review the earliest WAV-analysis entrypoint scripts.

This is a deterministic AI-helper review layer. It does not modify source files.
It emits notes, attention flags, and suggested future checks for the guardrail
and orchestration pipeline.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_TARGETS = ["analyze_wav.py", "build_track_summary.py"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def parse_ast(text: str) -> tuple[ast.AST | None, str | None]:
    try:
        return ast.parse(text), None
    except SyntaxError as exc:
        return None, f"{exc.msg} at line {exc.lineno}"


def imports(tree: ast.AST | None) -> list[str]:
    if tree is None:
        return []
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return sorted(found)


def functions(tree: ast.AST | None) -> list[dict[str, Any]]:
    if tree is None:
        return []
    out: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append({
                "name": node.name,
                "line_start": int(getattr(node, "lineno", 0)),
                "line_end": int(getattr(node, "end_lineno", getattr(node, "lineno", 0))),
                "has_docstring": bool(ast.get_docstring(node)),
            })
    return sorted(out, key=lambda item: item["line_start"])


def has_argparse(text: str) -> bool:
    return "argparse" in text and "ArgumentParser" in text


def literal_contains(text: str, token: str) -> bool:
    return token in text


def review_file(path: Path, repo: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "score": 0.0,
            "attention_flags": ["entrypoint_missing"],
            "notes": [],
            "future_guardrail_hints": [],
            "suggested_actions": ["Restore or locate the expected WAV-analysis entrypoint."],
        }

    text = read_text(path)
    tree, syntax_error = parse_ast(text)
    imps = imports(tree)
    funcs = functions(tree)
    attention: list[str] = []
    notes: list[str] = []
    hints: list[str] = []
    suggested: list[str] = []
    positives: list[str] = []

    if syntax_error:
        attention.append("syntax_error")
        suggested.append("Fix Python syntax before using this script in the artifact pipeline.")
    else:
        positives.append("python_ast_parse_ok")

    if has_argparse(text):
        positives.append("cli_arguments_present")
    else:
        attention.append("cli_arguments_missing")
        suggested.append("Expose input/output/runtime options through argparse for reproducible runs.")

    if "json.dump" in text:
        positives.append("json_output_present")
    else:
        attention.append("json_output_not_detected")
        suggested.append("Confirm that the script emits machine-readable JSON artifacts.")

    if "schema_version" not in text:
        attention.append("schema_version_not_written")
        hints.append("future_check: require schema_version in first-wave JSON artifacts or add a wrapper-side metadata manifest.")
        suggested.append("Add schema_version to generated summaries or companion manifests without rewriting full analysis data semantics.")

    if "source_analysis_json" in text or "input_wav" in text:
        positives.append("source_provenance_present")
    else:
        attention.append("source_provenance_weak")
        hints.append("future_check: require source path/provenance metadata for downstream AI traceability.")

    if "estimated_tempo_bpm" in text or "tempo" in text:
        positives.append("tempo_metadata_present")
    else:
        attention.append("tempo_metadata_not_detected")

    if path.name == "analyze_wav.py":
        required_tokens = ["librosa.load", "frames", "beats", "analysis_blender_keyframes", "plt.savefig"]
        for token in required_tokens:
            if token in text:
                positives.append(f"required_token_present:{token}")
            else:
                attention.append(f"required_token_missing:{token}")
        if "--skip-music-context" in text:
            positives.append("skip_music_context_flag_present")
        else:
            hints.append("future_check: add or preserve --skip-music-context to keep raw analysis separable from AI context generation.")
        if "--run-ollama-agent" in text:
            positives.append("optional_ai_agent_flag_present")
            notes.append("Optional AI call is behind a flag, which is good for deterministic WAV analysis.")
    elif path.name == "build_track_summary.py":
        required_tokens = ["energy_profile", "source_analysis_json", "duration_sec", "estimated_tempo_bpm", "build_summary"]
        for token in required_tokens:
            if token in text:
                positives.append(f"required_token_present:{token}")
            else:
                attention.append(f"required_token_missing:{token}")
        if "ROOT = Path.home()" in text:
            attention.append("hardcoded_default_project_root")
            suggested.append("Keep defaults for local convenience but prefer CLI paths in automated runs; guardrail should flag hardcoded defaults if reused in generated packages.")

    if "except Exception" in text:
        attention.append("broad_exception_handler_present")
        hints.append("future_check: ensure broad exceptions print useful warnings and do not hide failed artifact generation.")

    if "Path.home()" in text or "C:\\" in text:
        attention.append("local_path_default_present")
        hints.append("future_check: allow CLI override for every local path used by first-wave artifact builders.")

    score = 1.0
    score -= 0.25 if syntax_error else 0.0
    score -= min(0.45, len(attention) * 0.035)
    score += min(0.18, len(positives) * 0.012)
    score = max(0.0, min(1.0, round(score, 4)))

    return {
        "path": path.relative_to(repo).as_posix() if path.is_relative_to(repo) else str(path),
        "exists": True,
        "sha256": sha256_text(text),
        "line_count": len(text.splitlines()),
        "imports": imps,
        "functions": funcs,
        "score": score,
        "positives": sorted(set(positives)),
        "attention_flags": sorted(set(attention)),
        "notes": sorted(set(notes)),
        "future_guardrail_hints": sorted(set(hints)),
        "suggested_actions": sorted(set(suggested)),
    }


def aggregate(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    flags = [flag for item in reviews for flag in item.get("attention_flags", [])]
    hints = [hint for item in reviews for hint in item.get("future_guardrail_hints", [])]
    suggested = [action for item in reviews for action in item.get("suggested_actions", [])]
    avg = round(sum(float(item.get("score", 0.0)) for item in reviews) / len(reviews), 4) if reviews else 0.0
    remediation_requests = []
    for item in reviews:
        for action in item.get("suggested_actions", []):
            remediation_requests.append({
                "action_type": "review_wave_entrypoint",
                "priority": "medium" if item.get("score", 1.0) >= 0.65 else "high",
                "target": item.get("path"),
                "reason": "First-wave WAV artifact entrypoint review produced an attention flag.",
                "instruction": action,
                "suggested_stage": "wave_entrypoint_review",
                "auto_safe": False,
            })
    return {
        "average_score": avg,
        "attention_flag_count": len(flags),
        "unique_attention_flags": sorted(set(flags)),
        "future_guardrail_hints": sorted(set(hints)),
        "suggested_actions": sorted(set(suggested)),
        "remediation_requests": remediation_requests,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Review first-wave WAV artifact generation scripts.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--target", action="append", help="Relative path to a WAV entrypoint script. Can be repeated.")
    parser.add_argument("--output", default="output/ai_pipeline/wave_entrypoint_review.json")
    args = parser.parse_args()

    repo = Path(args.repo_root).resolve()
    target_paths = [repo / item for item in (args.target or DEFAULT_TARGETS)]
    reviews = [review_file(path.resolve(), repo) for path in target_paths]
    report = {
        "schema_version": 1,
        "kind": "wave_entrypoint_review",
        "generated_at": now_iso(),
        "purpose": "Review scripts that produce the earliest WAV-derived artifacts and emit notes/flags for future guardrails.",
        "reviews": reviews,
        "summary": aggregate(reviews),
    }

    out = Path(args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["summary"]["average_score"] >= 0.5 else 2


if __name__ == "__main__":
    raise SystemExit(main())
