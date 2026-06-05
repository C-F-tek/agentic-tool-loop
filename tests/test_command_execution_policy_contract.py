from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.command.execution_policy import evaluate_command_execution_policy


def test_validation_command_inside_repo_allowed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    policy = evaluate_command_execution_policy(
        "python -m pytest",
        cwd=repo,
        repo_root=repo,
    )

    assert policy["schema"] == "command_execution_policy.v1"
    assert policy["allowed"] is True
    assert policy["command_class"] == "validation"
    assert policy["cwd_under_repo"] is True
    assert policy["side_effect_scope"] == "repo_local"
    assert policy["diagnostic_only"] is True
    assert policy["does_not_execute"] is True


def test_validation_command_outside_repo_blocked(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()

    policy = evaluate_command_execution_policy(
        "python -m compileall services",
        cwd=outside,
        repo_root=repo,
    )

    assert policy["allowed"] is False
    assert policy["command_class"] == "validation"
    assert policy["reason"] == "validation command requires cwd under repo root"


def test_write_command_requires_repo_cwd_consent_and_write_approval(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    blocked = evaluate_command_execution_policy(
        "Set-Content a.txt x",
        cwd=repo,
        repo_root=repo,
        approval_mode="safe_write_lab",
        user_consent="",
    )
    allowed = evaluate_command_execution_policy(
        "Set-Content a.txt x",
        cwd=repo,
        repo_root=repo,
        approval_mode="safe_write_lab",
        user_consent="confirm",
    )

    assert blocked["allowed"] is False
    assert blocked["required_consent"] == "confirm command execution"
    assert allowed["allowed"] is True
    assert allowed["side_effect_scope"] == "repo_local_write"


def test_unknown_command_requires_consent_and_repo_cwd(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()

    outside_policy = evaluate_command_execution_policy(
        "custom-tool --do-thing",
        cwd=outside,
        repo_root=repo,
        user_consent="confirm",
    )
    inside_policy = evaluate_command_execution_policy(
        "custom-tool --do-thing",
        cwd=repo,
        repo_root=repo,
        user_consent="confirm",
    )

    assert outside_policy["allowed"] is False
    assert outside_policy["command_class"] == "unknown"
    assert inside_policy["allowed"] is True
    assert inside_policy["side_effect_scope"] == "repo_local_unknown"


def test_readonly_command_outside_repo_referencing_local_user_path_requires_consent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()

    policy = evaluate_command_execution_policy(
        r"Get-Content C:\Users\carmi\secret.txt",
        cwd=outside,
        repo_root=repo,
    )

    assert policy["allowed"] is False
    assert policy["command_class"] == "readonly"
    assert policy["required_consent"] == "confirm readonly command outside repo"


def test_command_execution_policy_is_json_serializable(tmp_path: Path) -> None:
    policy = evaluate_command_execution_policy(
        "git status --short",
        cwd=tmp_path,
        repo_root=tmp_path,
    )

    json.dumps(policy, ensure_ascii=False)
