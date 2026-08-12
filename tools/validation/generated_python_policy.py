"""Generic policy checks for generated Python scripts.

This module stays independent from input domains and output applications. It
knows about Python syntax and common generated-code hazards, but it does not
know whether a script targets Blender, another DCC application, an automation
runtime or a future app-specific adapter.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Iterable

try:
    from Tools.validation.generated_file_policy import PolicyFinding, PolicyResult, PolicyRule, evaluate_text
except ImportError:  # Allows direct execution from Tools/validation.
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from Tools.validation.generated_file_policy import PolicyFinding, PolicyResult, PolicyRule, evaluate_text  # type: ignore


GENERIC_GENERATED_PYTHON_RULES: tuple[dict[str, str], ...] = (
    {
        "rule_id": "python_syntax_error",
        "severity": "error",
        "kind": "ast",
        "description": "generated Python must parse before it is handed to an application/runtime adapter",
    },
    {
        "rule_id": "warn_python_eval_exec",
        "severity": "warning",
        "kind": "ast",
        "description": "generated Python should avoid dynamic eval/exec unless explicitly justified",
    },
    {
        "rule_id": "warn_os_system",
        "severity": "warning",
        "kind": "ast",
        "description": "generated Python should avoid os.system() unless explicitly justified",
    },
    {
        "rule_id": "warn_subprocess_shell_true",
        "severity": "warning",
        "kind": "ast",
        "description": "generated Python should avoid subprocess calls with shell=True unless explicitly justified",
    },
)

SUBPROCESS_SHELL_CALLS = {
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "subprocess.Popen",
    "subprocess.run",
}


def generated_python_rule_dicts(extra_rules: Iterable[PolicyRule] = ()) -> list[dict[str, Any]]:
    """Return generic Python policy rule metadata plus adapter text rules."""
    return [*GENERIC_GENERATED_PYTHON_RULES, *[rule.__dict__ for rule in extra_rules]]


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    """Build a best-effort map for common imported call aliases."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split(".")[0]] = item.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for item in node.names:
                aliases[item.asname or item.name] = f"{node.module}.{item.name}"
    return aliases


def _call_name(node: ast.AST, aliases: dict[str, str]) -> str | None:
    """Resolve a simple function call name, including common import aliases."""
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value, aliases)
        if parent:
            return f"{parent}.{node.attr}"
    return None


def _is_true_literal(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _line_message(base: str, node: ast.AST) -> str:
    line = getattr(node, "lineno", None)
    if line is None:
        return base
    return f"{base} on line {line}"


def _ast_findings(tree: ast.AST) -> list[PolicyFinding]:
    aliases = _import_aliases(tree)
    findings: list[PolicyFinding] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        call_name = _call_name(node.func, aliases)
        if call_name in {"eval", "exec"}:
            findings.append(
                PolicyFinding(
                    rule_id="warn_python_eval_exec",
                    severity="warning",
                    message=_line_message(f"Generated Python calls {call_name}()", node),
                )
            )
            continue

        if call_name == "os.system":
            findings.append(
                PolicyFinding(
                    rule_id="warn_os_system",
                    severity="warning",
                    message=_line_message("Generated Python calls os.system()", node),
                )
            )
            continue

        if call_name in SUBPROCESS_SHELL_CALLS:
            for keyword in node.keywords:
                if keyword.arg == "shell" and _is_true_literal(keyword.value):
                    findings.append(
                        PolicyFinding(
                            rule_id="warn_subprocess_shell_true",
                            severity="warning",
                            message=_line_message(f"Generated Python calls {call_name}(..., shell=True)", node),
                        )
                    )
                    break

    return findings


def evaluate_python_text(
    label: str,
    text: str,
    extra_rules: Iterable[PolicyRule] = (),
) -> PolicyResult:
    """Evaluate generated Python text with generic and adapter-specific rules."""
    adapter_rules = tuple(extra_rules)
    findings = list(evaluate_text(label, text, adapter_rules).findings)

    try:
        tree = ast.parse(text, filename=label)
    except SyntaxError as exc:
        message = f"Generated Python syntax error: {exc.msg}"
        if exc.lineno is not None:
            message = f"{message} on line {exc.lineno}"
        findings.append(PolicyFinding(rule_id="python_syntax_error", severity="error", message=message))
        return PolicyResult(label=label, passed=False, findings=findings)

    findings.extend(_ast_findings(tree))
    return PolicyResult(
        label=label,
        passed=not any(item.severity == "error" for item in findings),
        findings=findings,
    )


def evaluate_python_paths(
    paths: Iterable[Path],
    extra_rules: Iterable[PolicyRule] = (),
) -> list[PolicyResult]:
    """Evaluate existing generated Python files with generic and adapter rules."""
    results: list[PolicyResult] = []
    adapter_rules = tuple(extra_rules)
    for path in paths:
        resolved = path.resolve()
        if not resolved.exists():
            results.append(
                PolicyResult(
                    label=str(path),
                    passed=False,
                    findings=[
                        PolicyFinding(
                            rule_id="file_missing",
                            severity="error",
                            message=f"File not found: {resolved}",
                        )
                    ],
                )
            )
            continue
        text = resolved.read_text(encoding="utf-8", errors="replace")
        results.append(evaluate_python_text(str(path), text, adapter_rules))
    return results
