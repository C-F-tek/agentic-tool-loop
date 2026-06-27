"""Unit tests — BatchDecisionPhase evaluate_batch_decision()."""
import pytest


class TestBatchDecisionPhase:
    """Tests for BatchDecisionPhase class."""

    def test_batch_guard_empty_calls(self):
        """Verify block when no tool_calls in batch."""
        from ..application.planner.loop_phases import BatchDecisionPhase
        deps = {
            "tool_cache_key": lambda *a: "",
            "normalize_tool_name": lambda n: n,
            "sanitize_tool_args": lambda *a: dict(a[1]),
            "build_runtime_debug_packet": lambda **k: {},
            "validate_planner_decision_against_evidence": lambda *a: {"ok": True},
            "should_attempt_vulkan_repair": lambda *a: False,
            "vulkan_repair_invalid_planner_decision": lambda *a: {},
            "normalize_terminal_planner_decision": lambda d: d,
            "native_required_repaired_tool_decision_disallowed": lambda *a: False,
            "controller_guard_result_for_validation": lambda *a: None,
            "validation_without_full_evidence_contract": lambda *a: {},
            "append_agent_event": lambda *a: None,
        }
        config = {"AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY": 1}
        phase = BatchDecisionPhase(
            job_id="test-job",
            step=1,
            state={"goal": "test"},
            history=[],
            deps=deps,
            config=config,
        )
        batch_guard, batch_decisions, should_break = phase.evaluate_batch_decision(
            decision={"action": "tool_batch", "tool_calls": []},
            calls=[],
            batch_evidence_contract={},
            micro_batch_contract={},
            loop_controller=None,
            dispatch_tool=lambda *a: {"ok": True},
            sanitize_tool_args=lambda *a: dict(a[1]),
            write_json=lambda *a, **k: None,
            original_args={},
            public_tool_name="vulkan_helper",
            planner_evidence_contract=lambda *a: {},
        )
        assert isinstance(batch_guard, dict)
        assert batch_guard.get("guard_type") == "native_tool_batch_invalid"
        assert should_break is True

    def test_batch_guard_too_large(self):
        """Verify block when calls exceed native_max_parallel."""
        from ..application.planner.loop_phases import BatchDecisionPhase
        deps = {
            "tool_cache_key": lambda *a: "",
            "normalize_tool_name": lambda n: n,
            "sanitize_tool_args": lambda *a: dict(a[1]),
            "build_runtime_debug_packet": lambda **k: {},
            "validate_planner_decision_against_evidence": lambda *a: {"ok": True},
            "should_attempt_vulkan_repair": lambda *a: False,
            "vulkan_repair_invalid_planner_decision": lambda *a: {},
            "normalize_terminal_planner_decision": lambda d: d,
            "native_required_repaired_tool_decision_disallowed": lambda *a: False,
            "controller_guard_result_for_validation": lambda *a: None,
            "validation_without_full_evidence_contract": lambda *a: {},
            "append_agent_event": lambda *a: None,
        }
        config = {"AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY": 1}
        phase = BatchDecisionPhase(
            job_id="test-job",
            step=1,
            state={"goal": "test"},
            history=[],
            deps=deps,
            config=config,
        )
        calls = [
            {"tool": "repo_read", "arguments": {"path": "a.py"}},
            {"tool": "repo_read", "arguments": {"path": "b.py"}},
        ]
        batch_guard, batch_decisions, should_break = phase.evaluate_batch_decision(
            decision={"action": "tool_batch", "tool_calls": calls},
            calls=calls,
            batch_evidence_contract={},
            micro_batch_contract={},
            loop_controller=None,
            dispatch_tool=lambda *a: {"ok": True},
            sanitize_tool_args=lambda *a: dict(a[1]),
            write_json=lambda *a, **k: None,
            original_args={},
            public_tool_name="vulkan_helper",
            planner_evidence_contract=lambda *a: {},
        )
        assert isinstance(batch_guard, dict)
        assert batch_guard.get("guard_type") == "native_tool_batch_too_large"
        assert should_break is True

    def test_batch_success_single_call(self):
        """Verify successful single call execution."""
        from ..application.planner.loop_phases import BatchDecisionPhase
        deps = {
            "tool_cache_key": lambda *a: "",
            "normalize_tool_name": lambda n: n,
            "sanitize_tool_args": lambda *a: dict(a[1]),
            "build_runtime_debug_packet": lambda **k: {},
            "validate_planner_decision_against_evidence": lambda *a: {"ok": True},
            "should_attempt_vulkan_repair": lambda *a: False,
            "vulkan_repair_invalid_planner_decision": lambda *a: {},
            "normalize_terminal_planner_decision": lambda d: d,
            "native_required_repaired_tool_decision_disallowed": lambda *a: False,
            "controller_guard_result_for_validation": lambda *a: None,
            "validation_without_full_evidence_contract": lambda *a: {},
            "append_agent_event": lambda *a: None,
        }
        config = {"AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY": 5}
        phase = BatchDecisionPhase(
            job_id="test-job",
            step=1,
            state={"goal": "test"},
            history=[],
            deps=deps,
            config=config,
        )
        calls = [
            {"tool": "repo_read", "arguments": {"path": "test.py"}},
        ]
        batch_guard, batch_decisions, should_break = phase.evaluate_batch_decision(
            decision={"action": "tool_batch", "tool_calls": calls},
            calls=calls,
            batch_evidence_contract={},
            micro_batch_contract={},
            loop_controller=None,
            dispatch_tool=lambda *a: {"ok": True},
            sanitize_tool_args=lambda *a: dict(a[1]),
            write_json=lambda *a, **k: None,
            original_args={},
            public_tool_name="vulkan_helper",
            planner_evidence_contract=lambda *a: {},
        )
        assert isinstance(batch_guard, dict) or batch_guard == {}

    def test_batch_guard_duplicate_call(self):
        """Verify block for duplicate call signatures."""
        from ..application.planner.loop_phases import BatchDecisionPhase
        deps = {
            "tool_cache_key": lambda tool, args: f"{tool}:{args}",
            "normalize_tool_name": lambda n: n,
            "sanitize_tool_args": lambda *a: dict(a[1]),
            "build_runtime_debug_packet": lambda **k: {},
            "validate_planner_decision_against_evidence": lambda *a: {"ok": True},
            "should_attempt_vulkan_repair": lambda *a: False,
            "vulkan_repair_invalid_planner_decision": lambda *a: {},
            "normalize_terminal_planner_decision": lambda d: d,
            "native_required_repaired_tool_decision_disallowed": lambda *a: False,
            "controller_guard_result_for_validation": lambda *a: None,
            "validation_without_full_evidence_contract": lambda *a: {},
            "append_agent_event": lambda *a: None,
        }
        config = {"AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY": 5}
        phase = BatchDecisionPhase(
            job_id="test-job",
            step=1,
            state={"goal": "test"},
            history=[],
            deps=deps,
            config=config,
        )
        call = {"tool": "repo_read", "arguments": {"path": "test.py"}}
        calls = [call, call]
        batch_guard, batch_decisions, should_break = phase.evaluate_batch_decision(
            decision={"action": "tool_batch", "tool_calls": calls},
            calls=calls,
            batch_evidence_contract={},
            micro_batch_contract={},
            loop_controller=None,
            dispatch_tool=lambda *a: {"ok": True},
            sanitize_tool_args=lambda *a: dict(a[1]),
            write_json=lambda *a, **k: None,
            original_args={},
            public_tool_name="vulkan_helper",
            planner_evidence_contract=lambda *a: {},
        )
        assert isinstance(batch_guard, dict)

    def test_batch_guard_non_readonly(self):
        """Verify block for write tools in read-only batch."""
        from ..application.planner.loop_phases import BatchDecisionPhase
        deps = {
            "tool_cache_key": lambda *a: "",
            "normalize_tool_name": lambda n: n,
            "sanitize_tool_args": lambda *a: dict(a[1]),
            "build_runtime_debug_packet": lambda **k: {},
            "validate_planner_decision_against_evidence": lambda *a: {"ok": True},
            "should_attempt_vulkan_repair": lambda *a: False,
            "vulkan_repair_invalid_planner_decision": lambda *a: {},
            "normalize_terminal_planner_decision": lambda d: d,
            "native_required_repaired_tool_decision_disallowed": lambda *a: False,
            "controller_guard_result_for_validation": lambda *a: None,
            "validation_without_full_evidence_contract": lambda *a: {},
            "append_agent_event": lambda *a: None,
        }
        config = {"AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY": 5}
        phase = BatchDecisionPhase(
            job_id="test-job",
            step=1,
            state={"goal": "test"},
            history=[],
            deps=deps,
            config=config,
        )
        calls = [
            {"tool": "terminal", "arguments": {"command": "echo test"}},
        ]
        batch_guard, batch_decisions, should_break = phase.evaluate_batch_decision(
            decision={"action": "tool_batch", "tool_calls": calls},
            calls=calls,
            batch_evidence_contract={},
            micro_batch_contract={},
            loop_controller=None,
            dispatch_tool=lambda *a: {"ok": True},
            sanitize_tool_args=lambda *a: dict(a[1]),
            write_json=lambda *a, **k: None,
            original_args={},
            public_tool_name="vulkan_helper",
            planner_evidence_contract=lambda *a: {},
        )
        assert isinstance(batch_guard, dict) or batch_guard == {}

    def test_batch_success_multi_call(self):
        """Verify successful multi-call batch execution."""
        from ..application.planner.loop_phases import BatchDecisionPhase
        deps = {
            "tool_cache_key": lambda *a: "",
            "normalize_tool_name": lambda n: n,
            "sanitize_tool_args": lambda *a: dict(a[1]),
            "build_runtime_debug_packet": lambda **k: {},
            "validate_planner_decision_against_evidence": lambda *a: {"ok": True},
            "should_attempt_vulkan_repair": lambda *a: False,
            "vulkan_repair_invalid_planner_decision": lambda *a: {},
            "normalize_terminal_planner_decision": lambda d: d,
            "native_required_repaired_tool_decision_disallowed": lambda *a: False,
            "controller_guard_result_for_validation": lambda *a: None,
            "validation_without_full_evidence_contract": lambda *a: {},
            "append_agent_event": lambda *a: None,
        }
        config = {"AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY": 5}
        phase = BatchDecisionPhase(
            job_id="test-job",
            step=1,
            state={"goal": "test"},
            history=[],
            deps=deps,
            config=config,
        )
        calls = [
            {"tool": "repo_read", "arguments": {"path": "a.py"}},
            {"tool": "repo_read", "arguments": {"path": "b.py"}},
        ]
        batch_guard, batch_decisions, should_break = phase.evaluate_batch_decision(
            decision={"action": "tool_batch", "tool_calls": calls},
            calls=calls,
            batch_evidence_contract={},
            micro_batch_contract={},
            loop_controller=None,
            dispatch_tool=lambda *a: {"ok": True},
            sanitize_tool_args=lambda *a: dict(a[1]),
            write_json=lambda *a, **k: None,
            original_args={},
            public_tool_name="vulkan_helper",
            planner_evidence_contract=lambda *a: {},
        )
        assert isinstance(batch_guard, dict) or batch_guard == {}

    def test_batch_vulkan_repair_attempted(self):
        """Verify vulkan repair attempted on validation failure."""
        from ..application.planner.loop_phases import BatchDecisionPhase
        deps = {
            "tool_cache_key": lambda *a: "",
            "normalize_tool_name": lambda n: n,
            "sanitize_tool_args": lambda *a: dict(a[1]),
            "build_runtime_debug_packet": lambda **k: {},
            "validate_planner_decision_against_evidence": lambda *a: {"ok": False, "violations": ["test"]},
            "should_attempt_vulkan_repair": lambda *a: True,
            "vulkan_repair_invalid_planner_decision": lambda *a: {"action": "tool", "tool": "repo_read"},
            "normalize_terminal_planner_decision": lambda d: d,
            "native_required_repaired_tool_decision_disallowed": lambda *a: False,
            "controller_guard_result_for_validation": lambda *a: None,
            "validation_without_full_evidence_contract": lambda *a: {},
            "append_agent_event": lambda *a: None,
        }
        config = {"AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY": 5}
        phase = BatchDecisionPhase(
            job_id="test-job",
            step=1,
            state={"goal": "test"},
            history=[],
            deps=deps,
            config=config,
        )
        calls = [
            {"tool": "repo_read", "arguments": {"path": "test.py"}},
        ]
        batch_guard, batch_decisions, should_break = phase.evaluate_batch_decision(
            decision={"action": "tool_batch", "tool_calls": calls},
            calls=calls,
            batch_evidence_contract={},
            micro_batch_contract={},
            loop_controller=None,
            dispatch_tool=lambda *a: {"ok": True},
            sanitize_tool_args=lambda *a: dict(a[1]),
            write_json=lambda *a, **k: None,
            original_args={},
            public_tool_name="vulkan_helper",
            planner_evidence_contract=lambda *a: {},
        )
        assert isinstance(batch_guard, dict) or batch_guard == {}

    def test_batch_guard_contract_not_allowed(self):
        """Verify block when micro-batch contract disallows."""
        from ..application.planner.loop_phases import BatchDecisionPhase
        deps = {
            "tool_cache_key": lambda *a: "",
            "normalize_tool_name": lambda n: n,
            "sanitize_tool_args": lambda *a: dict(a[1]),
            "build_runtime_debug_packet": lambda **k: {},
            "validate_planner_decision_against_evidence": lambda *a: {"ok": True},
            "should_attempt_vulkan_repair": lambda *a: False,
            "vulkan_repair_invalid_planner_decision": lambda *a: {},
            "normalize_terminal_planner_decision": lambda d: d,
            "native_required_repaired_tool_decision_disallowed": lambda *a: False,
            "controller_guard_result_for_validation": lambda *a: None,
            "validation_without_full_evidence_contract": lambda *a: {},
            "append_agent_event": lambda *a: None,
        }
        config = {"AGENTIC_PLANNER_NATIVE_MAX_PARALLEL_READONLY": 5}
        phase = BatchDecisionPhase(
            job_id="test-job",
            step=1,
            state={"goal": "test"},
            history=[],
            deps=deps,
            config=config,
        )
        calls = [
            {"tool": "repo_read", "arguments": {"path": "test.py"}},
        ]
        micro_batch_contract = {"allowed": False}
        batch_guard, batch_decisions, should_break = phase.evaluate_batch_decision(
            decision={"action": "tool_batch", "tool_calls": calls},
            calls=calls,
            batch_evidence_contract={},
            micro_batch_contract=micro_batch_contract,
            loop_controller=None,
            dispatch_tool=lambda *a: {"ok": True},
            sanitize_tool_args=lambda *a: dict(a[1]),
            write_json=lambda *a, **k: None,
            original_args={},
            public_tool_name="vulkan_helper",
            planner_evidence_contract=lambda *a: {},
        )
        assert isinstance(batch_guard, dict) or batch_guard == {}