"""Diagnostic command execution polifrom aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

cy.

This module does not execute commands and does not grant consent. It turns the
existing command classification plus cwd/repo context into an inspectable policy
decision for planner/controller diagnostics.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aicarmine_broker.tools.command_safety import classify_command


SCHEMA = "command_execution_policy.v1"
LOCAL_PATH_MARKERS = ("C:\\Users\\", "C:/Users/", "\\Users\\", "/Users/")


def _as_path(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return Path(text).resolve(strict=False)


def _under_repo(cwd: Path | None, repo_root: Path | None) -> bool:
    if cwd is None or repo_root is None:
        return False
    try:
        cwd.relative_to(repo_root)
    except ValueError:
        return False
    return True


def _has_consent(user_consent: str) -> bool:
    consent = str(user_consent or "").lower()
    return "confirm" in consent or "confermo" in consent


def _has_strong_consent(user_consent: str) -> bool:
    consent = str(user_consent or "").lower()
    return _has_consent(consent) and any(
        token in consent
        for token in ("destructive", "distruttivo", "git reset", "remove-item", "rm", "delete", "elimina")
    )


def _mentions_local_user_path(command: str) -> bool:
    return any(marker.lower() in str(command or "").lower() for marker in LOCAL_PATH_MARKERS)


def _result(
    *,
    command_class: str,
    allowed: bool,
    reason: str,
    cwd_under_repo: bool,
    consent_required: bool,
    side_effect_scope: str,
    env_policy: str = "sanitized",
    required_consent: str = "",
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "allowed": allowed,
        "reason": reason,
        "command_class": command_class,
        "cwd_under_repo": cwd_under_repo,
        "consent_required": consent_required,
        "required_consent": required_consent,
        "env_policy": env_policy,
        "side_effect_scope": side_effect_scope,
        "diagnostic_only": True,
        "does_not_execute": True,
    }


def evaluate_command_execution_policy(
    command: str,
    *,
    command_class: str | None = None,
    cwd: str | Path | None = None,
    repo_root: str | Path | None = None,
    approval_mode: str = "",
    user_consent: str = "",
) -> dict[str, Any]:
    """Return an inspectable policy decision for a command context."""

    classification = classify_command(command)
    cls = str(command_class or classification.command_class)
    cwd_path = _as_path(cwd)
    repo_path = _as_path(repo_root)
    cwd_under_repo = _under_repo(cwd_path, repo_path)
    approval = str(approval_mode or "").lower()
    has_consent = _has_consent(user_consent)
    has_strong_consent = _has_strong_consent(user_consent)

    if cls == "readonly":
        if not cwd_under_repo and _mentions_local_user_path(command):
            return _result(
                command_class=cls,
                allowed=False,
                reason="readonly command outside repo references a local user path",
                cwd_under_repo=cwd_under_repo,
                consent_required=True,
                required_consent="confirm readonly command outside repo",
                side_effect_scope="external_read",
            )
        return _result(
            command_class=cls,
            allowed=True,
            reason="readonly command allowed by diagnostic policy",
            cwd_under_repo=cwd_under_repo,
            consent_required=False,
            side_effect_scope="repo_local" if cwd_under_repo else "external_read",
        )

    if cls == "validation":
        if cwd_under_repo:
            return _result(
                command_class=cls,
                allowed=True,
                reason="validation command inside repo root",
                cwd_under_repo=True,
                consent_required=False,
                side_effect_scope="repo_local",
            )
        return _result(
            command_class=cls,
            allowed=False,
            reason="validation command requires cwd under repo root",
            cwd_under_repo=False,
            consent_required=False,
            side_effect_scope="external",
        )

    if cls == "write":
        allowed = cwd_under_repo and has_consent and approval in {"safe_write_lab", "write", "memory_cleanup"}
        return _result(
            command_class=cls,
            allowed=allowed,
            reason=(
                "write command allowed inside repo with explicit consent and write approval"
                if allowed
                else "write command requires repo cwd, explicit consent and write approval"
            ),
            cwd_under_repo=cwd_under_repo,
            consent_required=True,
            required_consent="confirm command execution",
            side_effect_scope="repo_local_write" if cwd_under_repo else "external_write",
        )

    if cls == "destructive":
        allowed = cwd_under_repo and has_strong_consent and approval in {"safe_write_lab", "destructive"}
        return _result(
            command_class=cls,
            allowed=allowed,
            reason=(
                "destructive command allowed only by strong explicit consent inside repo"
                if allowed
                else "destructive command requires strong explicit consent and repo cwd"
            ),
            cwd_under_repo=cwd_under_repo,
            consent_required=True,
            required_consent="confirm destructive command execution",
            side_effect_scope="repo_local_destructive" if cwd_under_repo else "external_destructive",
        )

    return _result(
        command_class=cls,
        allowed=has_consent and cwd_under_repo,
        reason=(
            "unknown command allowed only with explicit consent inside repo"
            if has_consent and cwd_under_repo
            else "unknown command requires explicit consent and repo cwd"
        ),
        cwd_under_repo=cwd_under_repo,
        consent_required=True,
        required_consent="confirm command execution",
        side_effect_scope="repo_local_unknown" if cwd_under_repo else "external_unknown",
    )
