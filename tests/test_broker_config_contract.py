from __future__ import annotations

import ast
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def test_env_bool_true_values() -> None:
    from aicarmine_broker.config.env_loader import parse_bool

    for value in ("1", "true", "yes", "on", 1, True):
        assert parse_bool(value) is True


def test_env_bool_false_values() -> None:
    from aicarmine_broker.config.env_loader import parse_bool

    for value in ("0", "false", "no", "off", 0, False):
        assert parse_bool(value, default=True) is False


def test_env_int_invalid_raises() -> None:
    from aicarmine_broker.config.env_loader import env_int

    with pytest.raises(ValueError):
        env_int("BAD_INT", 1, {"BAD_INT": "not-int"})


def test_env_float_invalid_raises() -> None:
    from aicarmine_broker.config.env_loader import env_float

    with pytest.raises(ValueError):
        env_float("BAD_FLOAT", 1.0, {"BAD_FLOAT": "not-float"})


def test_broker_config_defaults_match_legacy_constants() -> None:
    from aicarmine_broker import config

    assert config.BROKER_CONFIG.planner_url == config.PLANNER_URL
    assert config.BROKER_CONFIG.planner_model == config.PLANNER_MODEL
    assert config.BROKER_CONFIG.agent_max_steps == config.AGENT_MAX_STEPS
    assert config.BROKER_CONFIG.num_ctx_effective == config.AGENTIC_PLANNER_NUM_CTX


def test_legacy_config_imports_core_runtime_constants() -> None:
    from aicarmine_broker.config import AGENT_MAX_STEPS, LAB_REPO, PLANNER_URL

    assert isinstance(PLANNER_URL, str) and PLANNER_URL
    assert isinstance(AGENT_MAX_STEPS, int) and AGENT_MAX_STEPS > 0
    assert isinstance(LAB_REPO, Path)


def test_config_model_is_frozen() -> None:
    from aicarmine_broker.config.models import load_broker_config_from_env

    cfg = load_broker_config_from_env({})

    with pytest.raises(FrozenInstanceError):
        cfg.planner_url = "http://changed"  # type: ignore[misc]


def test_env_alias_precedence_planner_url() -> None:
    from aicarmine_broker.config.models import load_broker_config_from_env

    cfg = load_broker_config_from_env(
        {
            "AICARMINE_AGENT_PLANNER_URL": "http://primary",
            "AICARMINE_PLANNER_URL": "http://secondary",
        }
    )

    assert cfg.planner_url == "http://primary"


def test_env_alias_precedence_planner_model() -> None:
    from aicarmine_broker.config.models import load_broker_config_from_env

    cfg = load_broker_config_from_env(
        {
            "AICARMINE_AGENT_PLANNER_MODEL": "model-a",
            "AICARMINE_PLANNER_MODEL": "model-b",
            "AICARMINE_OLLAMA_PLANNER_MODEL": "model-c",
        }
    )

    assert cfg.planner_model == "model-a"


def test_num_ctx_cap_applied() -> None:
    from aicarmine_broker.config.models import load_broker_config_from_env

    cfg = load_broker_config_from_env(
        {
            "AICARMINE_AGENTIC_PLANNER_NUM_CTX": "32768",
            "AICARMINE_AGENTIC_PLANNER_NUM_CTX_CAP": "12288",
        }
    )

    assert cfg.num_ctx_requested == 32768
    assert cfg.num_ctx_cap == 12288
    assert cfg.num_ctx_effective == 12288


def test_config_does_not_read_env_outside_env_loader() -> None:
    config_root = ROOT / "services" / "aicarmine_broker" / "config"
    offenders: list[str] = []
    for path in config_root.glob("*.py"):
        if path.name == "env_loader.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "environ":
                offenders.append(path.name)

    assert offenders == []


def test_broker_package_has_no_direct_env_reads_outside_env_loader() -> None:
    broker_root = ROOT / "services" / "aicarmine_broker"
    offenders: list[str] = []
    for path in broker_root.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.endswith("services/aicarmine_broker/config/env_loader.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"}:
                offenders.append(rel)
                break

    assert offenders == []
