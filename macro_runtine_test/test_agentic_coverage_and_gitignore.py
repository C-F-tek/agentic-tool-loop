from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from importlib import import_module

import pytest


ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "services"
if str(SERVICES) not in sys.path:
    sys.path.insert(0, str(SERVICES))

from aicarmine_broker.application.evidence.final_quality import repo_analysis_final_answer_quality  # noqa: E402
from aicarmine_broker.application.evidence.goal_classifier import goal_requires_code_security_coverage  # noqa: E402

repo_list_files_module = import_module("aicarmine_broker.tools.repo_list_files")
repo_tree_module = import_module("aicarmine_broker.tools.repo_tree")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.mark.skipif(shutil.which("git") is None, reason="git executable not available")
def test_repo_tree_and_list_files_use_gitignore_candidate_surface(monkeypatch, tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    _write(repo / ".gitignore", "ignored_dir/\n*.tmp\n")
    _write(repo / "src" / "app.py", "print('ok')\n")
    _write(repo / "ignored_dir" / "secret.py", "print('ignored')\n")
    _write(repo / "scratch.tmp", "ignored\n")

    monkeypatch.setattr(repo_tree_module, "LAB_REPO", repo)
    monkeypatch.setattr(repo_list_files_module, "LAB_REPO", repo)

    tree = repo_tree_module.repo_tree({"path": ".", "max_depth": 3, "max_files": 20}, tmp_path)
    listed = repo_list_files_module.repo_list_files({"path": ".", "suffix": ".py", "limit": 20}, tmp_path)

    assert tree["ok"] is True
    assert tree["source"] == "git_ls_files_exclude_standard"
    assert tree["gitignore_respected"] is True
    assert tree["truncated"] is False
    tree_paths = {item["path"] for item in tree["entries"]}
    assert "src/app.py" in tree_paths
    assert "ignored_dir/secret.py" not in tree_paths
    assert "scratch.tmp" not in tree_paths

    assert listed["source"] == "git_ls_files_exclude_standard"
    assert listed["paths"] == ["src/app.py"]
    assert listed["gitignore_respected"] is True


def test_security_critique_goal_requires_code_security_coverage() -> None:
    assert goal_requires_code_security_coverage(
        "analizza la repo in cerca di criticità di codice e semantiche"
    )


def test_repo_analysis_final_rejects_absolute_security_verdict_without_code_coverage() -> None:
    final_answer = (
        "NO CRITICITÀ DI SICUREZZA IDENTIFICATE\n\n"
        "Ho letto AGENTS.md README.md docs/README.md pyproject.toml config/allowlist.json "
        "e altri path concreti. Copertura e limiti sono documentati, con workflow, entrypoint "
        "e validazioni descritte. Il repository è intrinsecamente sicuro."
    )
    contract = {
        "file_memory": [
            {"path": "AGENTS.md"},
            {"path": "README.md"},
            {"path": "docs/README.md"},
            {"path": "pyproject.toml"},
            {"path": "config/allowlist.json"},
            {"path": "services/aicarmine_broker/planner.py"},
        ],
        "successful_repo_read_paths": [
            "AGENTS.md",
            "README.md",
            "docs/README.md",
            "pyproject.toml",
            "config/allowlist.json",
            "services/aicarmine_broker/planner.py",
        ],
        "code_security_coverage": {
            "required": True,
            "verdict_allowed": False,
            "allowed_conclusion": "partial_findings_only",
        },
    }

    quality = repo_analysis_final_answer_quality(final_answer, contract)

    assert quality["ok"] is False
    assert "repo_analysis_final_absolute_security_verdict_without_code_coverage" in quality["violations"]
