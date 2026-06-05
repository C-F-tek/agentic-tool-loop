from __future__ import annotations

import re
import ast
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
    assert "application.tool_surface.dispatcher" in text


def test_module_reference_declares_repo_tools_and_tool_dispatch_facades() -> None:
    text = _read("services/aicarmine_broker/MODULE_REFERENCE.md")

    assert "`repo_tools.py` | Compatibility facade" in text
    assert "`tool_dispatch.py` | Compatibility facade" in text
    assert "application/tool_surface/dispatcher.py" in text
    assert "`application/job/worker.py` | Background job worker" in text
    assert "`dispatcher.py` | Compatibility facade" not in text


def test_broker_dispatcher_shim_is_removed() -> None:
    assert not (ROOT / "services/aicarmine_broker/dispatcher.py").exists()
    for path in (ROOT / "services/aicarmine_broker").glob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        assert "aicarmine_broker.dispatcher" not in text, str(path)
        assert "from .dispatcher import" not in text, str(path)


def test_agent_entry_worker_logic_is_extracted() -> None:
    text = _read("services/aicarmine_broker/agent_entry.py")

    assert "from .application.job.worker import AgentJobWorker" in text
    assert "from .application.job.lifecycle import AgentJobLifecycle" in text
    assert "from .application.job.action_router import AgentJobActionRouter" in text
    assert "from .application.job.selector_runner import SelectorRunner" in text
    assert "def build_job_worker" in text
    assert "def build_job_lifecycle" in text
    assert "def build_job_action_router" in text
    assert "def build_selector_runner" in text
    forbidden = (
        "threading.Thread",
        "time.time()",
        "uuid.uuid4()",
        "traceback.format_exception",
        "error.txt",
        "final.json",
        "final.md",
        "run_agentic_planner_job(job_id)",
        "dispatcher_artifact",
        "select_internal_tool(public_tool_name=",
        "state['status'] = 'cancel_requested'",
        "raw_job_action",
    )
    for pattern in forbidden:
        assert pattern not in text, pattern


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


def test_repo_tools_is_facade_only() -> None:
    path = ROOT / "services/aicarmine_broker/repo_tools.py"
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    function_names = {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert function_names == {"run_ps", "compact"}
    forbidden = (
        r"subprocess\.run",
        r"shutil\.which",
        r"def\s+repo_",
        r"def\s+terminal_",
        r"def\s+_run_argv",
        r"def\s+_resolve",
    )
    for pattern in forbidden:
        assert not re.search(pattern, text), pattern


def test_job_store_delegates_sqlite_primitives() -> None:
    text = _read("services/aicarmine_broker/job_store.py")

    assert "from .infrastructure.job_sqlite_store import AgentJobSQLiteStore" in text
    assert "import sqlite3" not in text
    assert "sqlite3.connect" not in text
