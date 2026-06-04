from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def test_bridge_config_defaults_match_app_constants() -> None:
    from vulkan_bridge import app

    assert app.BRIDGE_CONFIG.agent_url == app.AGENT_URL
    assert app.BRIDGE_CONFIG.bridge_timeout_seconds == app.BRIDGE_TIMEOUT_SECONDS
    assert app.BRIDGE_CONFIG.planner_url == app.PLANNER_URL
    assert app.BRIDGE_CONFIG.planner_model == app.PLANNER_MODEL


def test_bridge_config_planner_alias_precedence() -> None:
    from vulkan_bridge.config import load_bridge_config_from_env

    cfg = load_bridge_config_from_env(
        {
            "AICARMINE_AGENT_PLANNER_URL": "http://primary",
            "AICARMINE_PLANNER_URL": "http://secondary",
            "AICARMINE_AGENT_PLANNER_MODEL": "model-a",
            "AICARMINE_PLANNER_MODEL": "model-b",
            "AICARMINE_OLLAMA_PLANNER_MODEL": "model-c",
        }
    )

    assert cfg.planner_url == "http://primary"
    assert cfg.planner_model == "model-a"


def test_bridge_bool_env_false_values() -> None:
    from vulkan_bridge.config import bool_env

    for value in ("0", "false", "no", "off", ""):
        assert bool_env("FLAG", True, {"FLAG": value}) is False
