from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def test_flat_application_shims_are_removed() -> None:
    legacy_names = [
        "aicarmine_broker.application.planner_loop",
        "aicarmine_broker.application.prompt_pack_builder",
        "aicarmine_broker.application.evidence_builder",
        "aicarmine_broker.application.tool_dispatcher",
    ]

    for legacy_name in legacy_names:
        assert importlib.util.find_spec(legacy_name) is None

    flat_files = [
        path.name
        for path in (ROOT / "services" / "aicarmine_broker" / "application").glob("*.py")
        if path.name != "__init__.py"
    ]
    assert flat_files == []


def test_application_superowners_expose_controlled_public_api() -> None:
    expected = {
        "planner": "run_agentic_planner_job",
        "prompt": "PromptPackBuilder",
        "evidence": "EvidenceBuilder",
        "code_product": "code_product_build_state_parse",
        "public_payload": "OpenWebUIPayloadBuilder",
        "job": "AgentJobLifecycle",
        "controller": "controller_guard_count",
        "tool_surface": "ToolSurfacePolicy",
        "shared": "repo_rel_token",
    }

    for package, public_name in expected.items():
        module = importlib.import_module(f"aicarmine_broker.application.{package}")
        assert public_name in module.__all__
        assert getattr(module, public_name) is not None


def test_planner_loop_history_mutation_uses_state_owner() -> None:
    loop_text = (ROOT / "services" / "aicarmine_broker" / "application" / "planner" / "loop.py").read_text(
        encoding="utf-8",
        errors="replace",
    )
    state_text = (ROOT / "services" / "aicarmine_broker" / "application" / "planner" / "state.py").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "class PlannerLoopState" in state_text
    assert "append_history_row" in state_text
    assert "refresh_history" in state_text
    forbidden = (
        "history.append(",
        'state["history"]',
        'state["history_count"]',
        'state["evidence_contract"]',
    )
    for pattern in forbidden:
        assert pattern not in loop_text, pattern
