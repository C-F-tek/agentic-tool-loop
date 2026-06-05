from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def test_runtime_compat_facades_do_not_use_globals_update() -> None:
    for rel in (
        "services/aicarmine_vulkan_bridge_server.py",
        "services/aicarmine_codex_mcp_server.py",
        "services/aicarmine_codex_ollama_responses_bridge.py",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "globals(" not in text
        assert "globals().update" not in text


def test_vulkan_bridge_compat_facade_exposes_app() -> None:
    compat = importlib.import_module("aicarmine_vulkan_bridge_server")
    implementation = importlib.import_module("vulkan_bridge.app")

    assert compat.__all__ == ["app"]
    assert compat.app is implementation.app


def test_codex_mcp_compat_facade_exposes_main() -> None:
    compat = importlib.import_module("aicarmine_codex_mcp_server")
    implementation = importlib.import_module("codex_bridge.mcp_server")

    assert compat.__all__ == ["main"]
    assert compat.main is implementation.main


def test_codex_ollama_responses_compat_facade_exposes_app() -> None:
    compat = importlib.import_module("aicarmine_codex_ollama_responses_bridge")
    implementation = importlib.import_module("codex_bridge.ollama_responses_bridge")

    assert compat.__all__ == ["app"]
    assert compat.app is implementation.app
