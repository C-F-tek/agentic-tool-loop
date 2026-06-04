from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.goal_classifier import (  # noqa: E402
    final_answer_is_action_plan_without_code_product,
    goal_requests_apply,
    goal_requests_code_product,
    input_error_goal,
    semantic_goal_classification,
    semantic_goal_text,
)
from aicarmine_broker.planner import semantic_goal_classification as planner_goal_classification  # noqa: E402


def test_goal_text_extracts_user_request_from_tool_envelope() -> None:
    assert semantic_goal_text('{"function":"vulkan_helper","request":"analizza la repo"}') == "analizza la repo"


def test_goal_text_marks_tool_envelope_without_request_as_input_error() -> None:
    text = semantic_goal_text('{"function":"vulkan_helper","operation_id":"x"}')
    assert input_error_goal(text)
    assert "MISSING_USER_REQUEST" in text


def test_report_only_diff_is_code_product_not_apply() -> None:
    goal = "Generate a detailed complete unified diff. Do not apply the patch; report-only."
    assert goal_requests_code_product(goal)
    assert not goal_requests_apply(goal)


def test_explicit_apply_is_apply_write() -> None:
    goal = "Apply the patch and fix the failing validation"
    assert goal_requests_apply(goal)
    classification = semantic_goal_classification(goal)
    assert classification["class"] == "apply_write"
    assert not classification["must_produce_code_product"]


def test_concrete_refactor_proposal_requires_code_product() -> None:
    goal = "Analizza IA_CARMINE e proponi refactor concreto"
    classification = semantic_goal_classification(goal)
    assert classification["class"] == "code_product_report"
    assert classification["must_produce_code_product"]


def test_repo_analysis_signal_is_injected_by_planner_wrapper() -> None:
    classification = planner_goal_classification("analizza la repo e descrivimi il funzionamento")
    assert classification["class"] == "analysis_only"
    assert classification["requested_deliverable"] == "repository analysis"


def test_action_plan_without_diff_is_detected() -> None:
    text = "Recommendations:\n- Start with repo_tools cleanup.\n\nNext steps:\n- Review modules."
    assert final_answer_is_action_plan_without_code_product(text)
    assert not final_answer_is_action_plan_without_code_product("```diff\n@@ -1 +1\n-a\n+b\n```")
