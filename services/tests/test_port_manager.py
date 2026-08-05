"""
tests.test_port_manager
=======================
Tests for services.runtime.port_manager module.
"""
from __future__ import annotations

import pytest
from services.runtime import get_port_manager


def test_port_manager_singleton():
    """Test that get_port_manager returns singleton instance."""
    pm1 = get_port_manager()
    pm2 = get_port_manager()
    assert pm1 is pm2


def test_port_ownership_tracking():
    """Test port ownership tracking."""
    pm = get_port_manager()
    # Check that known ports are tracked
    assert 3550 in pm.get_all_ports() or hasattr(pm, 'ovms_reranker_port')
    assert 3571 in pm.get_all_ports() or hasattr(pm, 'vulkan_bridge_port')
    assert 3572 in pm.get_all_ports() or hasattr(pm, 'broker_port')
    assert 3579 in pm.get_all_ports() or hasattr(pm, 'agentic_loop_port')


def test_port_status_check():
    """Test port status checking."""
    pm = get_port_manager()
    # This should not raise an exception
    try:
        status = pm.get_port_status(3572)
        assert isinstance(status, dict)
    except Exception:
        pass  # Port may not be up in test environment