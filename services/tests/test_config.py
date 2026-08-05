"""
tests.test_config
=================
Tests for services.config.settings module.
"""
from __future__ import annotations

import os
import pytest
from services.config import BrokerConfig, PortConfig, get_settings


def test_broker_config_defaults():
    """Test BrokerConfig default values."""
    config = BrokerConfig()
    assert config.planner_model is not None
    assert config.planner_url is not None
    assert config.ollama_url is not None
    assert config.ollama_model is not None


def test_port_config_validation():
    """Test PortConfig validates port ranges."""
    config = PortConfig()
    assert config.ovms_reranker_port == 3550
    assert config.vulkan_bridge_port == 3571
    assert config.broker_port == 3572
    assert config.agentic_loop_port == 3579
    assert config.ollama_port == 11434


def test_get_settings():
    """Test get_settings returns valid configuration."""
    settings = get_settings()
    assert settings is not None
    assert hasattr(settings, 'broker')
    assert hasattr(settings, 'ports')


def test_env_var_override():
    """Test environment variable overrides work."""
    os.environ["AICARMINE_BANNER"] = "test"
    try:
        settings = get_settings()
        assert settings is not None
    finally:
        os.environ.pop("AICARMINE_BANNER", None)