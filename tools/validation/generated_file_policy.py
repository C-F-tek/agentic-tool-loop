"""Reusable policy primitives for generated file validation.

The module is intentionally generic. Domain-specific validators, such as a
Blender generated-script policy, should define rules and feed text into this
small policy engine instead of hard-coding unrelated checks everywhere.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal

Severity = Literal["error", "warning"]
RuleKind = Literal["required", "forbidden"]


@dataclass(frozen=True)
class PolicyRule:
    """One generated-file policy rule."""

    rule_id: str
    description: str
    pattern: str
    kind: RuleKind
    severity: Severity = "error"
    flags: int = re.MULTILINE

    def matches(self, text: str) -> bool:
        """Return whether the rule pattern matches the supplied text."""
        return re.search(self.pattern, text, self.flags) is not None


@dataclass
class PolicyFinding:
    """One policy finding."""

    rule_id: str
    severity: Severity
    message: str


@dataclass
class PolicyResult:
    """Policy result for one generated file or text sample."""

    label: str
    passed: bool
    findings: list[PolicyFinding] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.findings if item.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.findings if item.severity == "warning")

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "passed": self.passed,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "findings": [finding.__dict__ for finding in self.findings],
        }


@dataclass(frozen=True)
class PathPolicy:
    """Allowed repository destinations for generated artifacts."""

    allowed_prefixes: tuple[str, ...]
    allowed_exact_paths: tuple[str, ...] = ()


@dataclass
class PathPolicyResult:
    """Path policy result for one generated artifact destination."""

    label: str
    path: str
    repo_relative_path: str | None
    passed: bool
    findings: list[PolicyFinding] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.findings if item.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.findings if item.severity == "warning")

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "path": self.path,
            "repo_relative_path": self.repo_relative_path,
            "passed": self.passed,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "findings": [finding.__dict__ for finding in self.findings],
        }


def evaluate_text(label: str, text: str, rules: Iterable[PolicyRule]) -> PolicyResult:
    """Evaluate generated text against reusable policy rules."""
    findings: list[PolicyFinding] = []
    for rule in rules:
        matched = rule.matches(text)
        violated = (rule.kind == "required" and not matched) or (rule.kind == "forbidden" and matched)
        if not violated:
            continue
        if rule.kind == "required":
            message = f"Required pattern not found: {rule.description}"
        else:
            message = f"Forbidden pattern found: {rule.description}"
        findings.append(PolicyFinding(rule_id=rule.rule_id, severity=rule.severity, message=message))
    passed = not any(item.severity == "error" for item in findings)
    return PolicyResult(label=label, passed=passed, findings=findings)


def evaluate_paths(paths: Iterable[Path], rules: Iterable[PolicyRule]) -> list[PolicyResult]:
    """Evaluate existing files against reusable policy rules."""
    results: list[PolicyResult] = []
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
        results.append(evaluate_text(str(path), text, rules))
    return results


def normalize_policy_path(value: str) -> str:
    """Normalize a repository-relative policy path for cross-platform matching."""
    return value.replace("\\", "/").strip().lstrip("./")


def _matches_exact(relative_path: str, exact_paths: Iterable[str]) -> bool:
    normalized = normalize_policy_path(relative_path).casefold()
    return any(normalized == normalize_policy_path(item).casefold() for item in exact_paths)


def _matches_prefix(relative_path: str, prefixes: Iterable[str]) -> bool:
    normalized = normalize_policy_path(relative_path).casefold()
    for prefix in prefixes:
        candidate = normalize_policy_path(prefix).casefold().rstrip("/")
        if normalized == candidate or normalized.startswith(candidate + "/"):
            return True
    return False


def repo_relative_policy_path(repo_root: Path, artifact_path: Path) -> tuple[Path, str | None]:
    """Resolve an artifact destination and return its repo-relative path when possible."""
    root = repo_root.resolve()
    resolved = (root / artifact_path).resolve() if not artifact_path.is_absolute() else artifact_path.resolve()
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved, None
    return resolved, relative


def evaluate_generated_artifact_path(repo_root: Path, artifact_path: Path, policy: PathPolicy) -> PathPolicyResult:
    """Evaluate one generated artifact destination against a repository path policy."""
    resolved, relative = repo_relative_policy_path(repo_root, artifact_path)
    findings: list[PolicyFinding] = []
    label = str(artifact_path)

    if relative is None:
        findings.append(
            PolicyFinding(
                rule_id="outside_repo",
                severity="error",
                message=f"Generated artifact path resolves outside the repository: {resolved}",
            )
        )
    elif not _matches_exact(relative, policy.allowed_exact_paths) and not _matches_prefix(relative, policy.allowed_prefixes):
        findings.append(
            PolicyFinding(
                rule_id="path_not_allowed",
                severity="error",
                message=f"Generated artifact path is not in an allowed destination: {relative}",
            )
        )

    return PathPolicyResult(
        label=label,
        path=str(resolved),
        repo_relative_path=relative,
        passed=not any(item.severity == "error" for item in findings),
        findings=findings,
    )


def evaluate_generated_artifact_paths(
    repo_root: Path,
    paths: Iterable[Path],
    policy: PathPolicy,
) -> list[PathPolicyResult]:
    """Evaluate generated artifact destinations against a repository path policy."""
    return [evaluate_generated_artifact_path(repo_root, path, policy) for path in paths]
