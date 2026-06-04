from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="replace")


def test_repo_tools_docstring_declares_facade() -> None:
    text = _read("services/aicarmine_broker/repo_tools.py")

    assert "Compatibility facade for deterministic local repository tools." in text
    assert "Do not add new tool behavior here." in text
    assert "All deterministic local repository tools executed by the 3572 dispatcher" not in text
    assert "run_ps`` is the only subprocess boundary" not in text


def test_tool_dispatch_docstring_declares_facade() -> None:
    text = _read("services/aicarmine_broker/tool_dispatch.py")

    assert "compatibility facade" in text.lower()
    assert "application.tool_dispatcher" in text


def test_module_reference_declares_repo_tools_and_tool_dispatch_facades() -> None:
    text = _read("services/aicarmine_broker/MODULE_REFERENCE.md")

    assert "`repo_tools.py` | Compatibility facade" in text
    assert "`tool_dispatch.py` | Compatibility facade" in text
    assert "application/tool_dispatcher.py" in text


def test_tool_dispatch_facade_has_no_if_table() -> None:
    text = _read("services/aicarmine_broker/tool_dispatch.py")

    forbidden = (
        r"\bif\s+tool\b",
        r"\belif\s+tool\b",
        r"repo_[a-z_]+\(args",
        r"terminal_[a-z_]+\(args",
        r"runtime_sqlite_[a-z_]+\(args",
    )
    for pattern in forbidden:
        assert not re.search(pattern, text), pattern
