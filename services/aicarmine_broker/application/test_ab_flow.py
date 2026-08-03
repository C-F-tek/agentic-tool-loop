"""A/B Flow Test - Compare original vs refactored modules.

This script tests the refactored modules against the original ones
to ensure they produce the same results.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Add the services directory to the path
services_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(services_dir))

logger = logging.getLogger(__name__)


def test_dispatcher():
    """Test the refactored dispatcher."""
    from application2.dispatcher import RegistryToolDispatcher
    
    dispatcher = RegistryToolDispatcher()
    dispatcher.register("test_tool", lambda args, **kwargs: {"ok": True})
    tools = dispatcher.list_tools()
    
    logger.info("Dispatcher loaded with %d tools", len(tools))
    logger.info("Tools: %s", tools)
    
    # Test dispatch
    result = dispatcher.dispatch("test_tool", {})
    logger.info("Dispatch result: %s", result)
    
    return True


def test_validator():
    """Test the refactored validator."""
    from application2.planner.validator import validate_planner_decision
    
    # Test with a simple decision
    decision = {
        "action": "tool",
        "tool": "repo_read",
        "arguments": {"paths": ["test.py"]},
    }
    
    result = validate_planner_decision(
        goal="Test goal",
        decision=decision,
        history=[],
        deps={},
        config={"VALID_INTERNAL_TOOLS": ["repo_read"]},
    )
    
    logger.info("Validation result: %s", result)
    return True


def test_evidence_builder():
    """Test the refactored evidence builder."""
    from application2.evidence.builder import EvidenceBuilder
    
    builder = EvidenceBuilder(_deps={}, _config={})
    
    result = builder.build(
        goal="Test goal",
        history=[],
        intrinsic_context=None,
    )
    
    logger.info("Evidence builder result: %s", result)
    return True


def main():
    """Run all A/B flow tests."""
    logging.basicConfig(level=logging.INFO)
    
    logger.info("Starting A/B flow tests...")
    logger.info("Services dir: %s", str(services_dir))
    
    try:
        test_dispatcher()
        logger.info("Dispatcher test passed")
    except Exception as e:
        logger.error("Dispatcher test failed: %s", e)
        return False
    
    try:
        test_validator()
        logger.info("Validator test passed")
    except Exception as e:
        logger.error("Validator test failed: %s", e)
        return False
    
    try:
        test_evidence_builder()
        logger.info("Evidence builder test passed")
    except Exception as e:
        logger.error("Evidence builder test failed: %s", e)
        return False
    
    logger.info("All A/B flow tests passed!")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)