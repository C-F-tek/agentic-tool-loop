from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

SERVICES_ROOT = Path(__file__).resolve().parent
CODEX_BRIDGE_ROOT = SERVICES_ROOT / "codex_bridge"
for import_root in (SERVICES_ROOT, CODEX_BRIDGE_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from codex_bridge import sqlite_readonly_mcp_server  # noqa: E402


def _create_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE demo (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO demo (name) VALUES ('alpha'), ('beta')")


def test_sqlite_readonly_query_allows_bounded_select(tmp_path) -> None:
    db = tmp_path / "demo.sqlite3"
    _create_db(db)

    result = sqlite_readonly_mcp_server._query(
        {
            "db": str(db),
            "sql": "SELECT id, name FROM demo ORDER BY id",
            "row_limit": 1,
        },
        tmp_path,
    )

    assert result["ok"] is True
    assert result["read_only"] is True
    assert result["only_select"] is True
    assert result["columns"] == ["id", "name"]
    assert result["rows"] == [{"id": 1, "name": "alpha"}]
    assert result["truncated"] is True


def test_sqlite_readonly_rejects_write_sql(tmp_path) -> None:
    db = tmp_path / "demo.sqlite3"
    _create_db(db)

    result = sqlite_readonly_mcp_server._query(
        {
            "db": str(db),
            "sql": "UPDATE demo SET name = 'changed'",
        },
        tmp_path,
    )

    assert result["ok"] is False
    assert result["error"] == "only_select_or_with_allowed"


def test_sqlite_readonly_rejects_db_outside_allowlist(tmp_path) -> None:
    db = tmp_path.parent / "outside.sqlite3"
    _create_db(db)

    result = sqlite_readonly_mcp_server._query(
        {
            "db": str(db),
            "sql": "SELECT 1",
        },
        tmp_path,
    )

    assert result["ok"] is False
    assert result["error"] == "db_path_not_allowlisted"
