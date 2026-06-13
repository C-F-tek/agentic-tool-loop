from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SERVICES_ROOT = Path(__file__).resolve().parent
CODEX_BRIDGE_ROOT = SERVICES_ROOT / "codex_bridge"
for import_root in (SERVICES_ROOT, CODEX_BRIDGE_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from codex_bridge import project_memory_mcp_server  # noqa: E402


def _git_init(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)


@pytest.mark.skipif(shutil.which("git") is None, reason="git executable not available")
def test_project_memory_upsert_requires_confirmation_and_verified_source(tmp_path) -> None:
    _git_init(tmp_path)
    source = tmp_path / "AGENTS.md"
    source.write_text("contract\n", encoding="utf-8")

    denied = project_memory_mcp_server._upsert_verified(
        {
            "scope": "repo",
            "key": "contract.runtime",
            "value": "Read AGENTS before critical edits.",
            "source_type": "file",
            "source_ref": "AGENTS.md",
        },
        tmp_path,
    )

    assert denied["ok"] is False
    assert denied["error"] == "missing_confirm_write"
    assert denied["source_writes_performed"] is False
    assert not (tmp_path / "state" / "project_memory" / "project_memory.sqlite3").exists()

    missing_source = project_memory_mcp_server._upsert_verified(
        {
            "scope": "repo",
            "key": "contract.runtime",
            "value": "Read AGENTS before critical edits.",
            "source_type": "file",
            "source_ref": "missing.md",
            "confirm_write": project_memory_mcp_server.UPSERT_CONFIRM,
        },
        tmp_path,
    )

    assert missing_source["ok"] is False
    assert missing_source["error"] == "source_verification_failed"

    written = project_memory_mcp_server._upsert_verified(
        {
            "scope": "repo",
            "key": "contract.runtime",
            "value": "Read AGENTS before critical edits.",
            "source_type": "file",
            "source_ref": "AGENTS.md",
            "confirm_write": project_memory_mcp_server.UPSERT_CONFIRM,
            "tags": ["contract"],
            "metadata": {"owner": "workspace"},
        },
        tmp_path,
    )

    assert written["ok"] is True
    assert written["changed"] is True
    assert written["source_writes_performed"] is True
    assert written["record"]["source_ref"] == "AGENTS.md"
    assert written["record"]["tags"] == ["contract"]
    assert written["record"]["metadata"] == {"owner": "workspace"}

    found = project_memory_mcp_server._search({"query": "AGENTS"}, tmp_path)
    assert found["ok"] is True
    assert found["count"] == 1
    assert found["records"][0]["key"] == "contract.runtime"


@pytest.mark.skipif(shutil.which("git") is None, reason="git executable not available")
def test_project_memory_conflict_stale_supersede_and_audit(tmp_path) -> None:
    _git_init(tmp_path)
    source = tmp_path / "docs.md"
    source.write_text("evidence\n", encoding="utf-8")
    base_args = {
        "scope": "repo",
        "key": "service.port",
        "value": "Broker listens on 3572.",
        "source_type": "file",
        "source_ref": "docs.md",
        "confirm_write": project_memory_mcp_server.UPSERT_CONFIRM,
    }
    first = project_memory_mcp_server._upsert_verified(base_args, tmp_path)
    assert first["ok"] is True

    conflict = project_memory_mcp_server._upsert_verified(
        {
            **base_args,
            "value": "Broker listens on 9999.",
        },
        tmp_path,
    )
    assert conflict["ok"] is False
    assert conflict["error"] == "active_memory_conflict"

    stale = project_memory_mcp_server._mark_stale(
        {
            "record_id": first["record"]["record_id"],
            "obsolete_reason": "Port changed in verified docs.",
            "source_type": "file",
            "source_ref": "docs.md",
            "confirm_stale": project_memory_mcp_server.STALE_CONFIRM,
        },
        tmp_path,
    )
    assert stale["ok"] is True
    assert stale["record"]["status"] == "stale"

    replacement = project_memory_mcp_server._upsert_verified(
        {
            **base_args,
            "value": "Broker listens on 3572 again.",
        },
        tmp_path,
    )
    assert replacement["ok"] is True

    superseded = project_memory_mcp_server._supersede(
        {
            "record_id": replacement["record"]["record_id"],
            "new_value": "Broker service port is verified before HTTP smoke.",
            "source_type": "file",
            "source_ref": "docs.md",
            "obsolete_reason": "Replaced by more precise operational rule.",
            "confirm_supersede": project_memory_mcp_server.SUPERSEDE_CONFIRM,
        },
        tmp_path,
    )
    assert superseded["ok"] is True
    assert superseded["record"]["value"] == "Broker service port is verified before HTTP smoke."
    assert superseded["superseded_record_id"] == replacement["record"]["record_id"]

    audit = project_memory_mcp_server._audit_sources({"status": "any"}, tmp_path)
    assert audit["ok"] is True
    assert audit["records_checked"] >= 3
    assert audit["broken_source_count"] == 0
