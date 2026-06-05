from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_codex_mcp_server_does_not_import_broker_registry_at_module_import() -> None:
    source_path = ROOT / "services" / "codex_bridge" / "mcp_server.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    top_level_imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and str(node.module or "") == "aicarmine_broker.tool_registry"
    ]

    assert top_level_imports == []


def test_codex_mcp_server_runtime_import_does_not_import_aicarmine_broker() -> None:
    source_path = ROOT / "services" / "codex_bridge" / "mcp_server.py"
    saved = {
        name: module
        for name, module in list(sys.modules.items())
        if name.startswith("aicarmine_broker")
    }
    for name in saved:
        sys.modules.pop(name, None)
    try:
        spec = importlib.util.spec_from_file_location("mcp_server_lazy_probe", source_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert not any(name.startswith("aicarmine_broker") for name in sys.modules)
    finally:
        for name in list(sys.modules):
            if name.startswith("aicarmine_broker"):
                sys.modules.pop(name, None)
        sys.modules.update(saved)


def test_codex_mcp_registry_loader_handles_import_failure(monkeypatch) -> None:
    sys.path.insert(0, str(ROOT / "services"))
    from codex_bridge import mcp_server

    monkeypatch.setitem(sys.modules, "aicarmine_broker.tool_registry", None)

    assert mcp_server._load_broker_registry_capability_map() is None


def test_codex_mcp_registry_loader_loads_lazily() -> None:
    sys.path.insert(0, str(ROOT / "services"))
    from codex_bridge import mcp_server

    loader = mcp_server._load_broker_registry_capability_map()

    assert callable(loader)
