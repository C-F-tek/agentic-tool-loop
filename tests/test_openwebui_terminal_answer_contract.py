from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.public_payload.openwebui_terminal_answer import (  # noqa: E402
    answer_for_openwebui,
    next_action_for_openwebui,
)


def _code_product(result: dict) -> str:
    return str(result.get("code_product_answer") or "")


def _evidence(result: dict) -> str:
    return str(result.get("evidence") or "")


def _partial(result: dict) -> str:
    return str(result.get("partial") or "")


def test_completed_answer_prefers_code_product_with_evidence() -> None:
    answer = answer_for_openwebui(
        "completed",
        "summary",
        {"code_product_answer": "diff text", "evidence": "evidence text"},
        code_product_answer_text=_code_product,
        execution_evidence_digest_text=_evidence,
        partial_product_answer_text=_partial,
    )

    assert answer == "diff text\n\nevidence text"


def test_completed_answer_uses_summary_with_evidence_without_code_product() -> None:
    answer = answer_for_openwebui(
        "completed",
        "summary",
        {"evidence": "evidence text"},
        code_product_answer_text=_code_product,
        execution_evidence_digest_text=_evidence,
        partial_product_answer_text=_partial,
    )

    assert answer == "summary\n\nevidence text"


def test_blocked_answer_includes_partial_raw_diagnostics_and_repair() -> None:
    answer = answer_for_openwebui(
        "blocked_needs_attention",
        "summary",
        {
            "blocked_by": "validator",
            "partial": "partial product",
            "raw_planner_text": "raw text",
            "agent_flow_diagnostics": {
                "last_non_empty_raw_previews": ["a", "b"],
                "deterministic_strip_count": 2,
            },
            "vulkan_repair": {"ok": False, "error": "timeout"},
        },
        code_product_answer_text=_code_product,
        execution_evidence_digest_text=_evidence,
        partial_product_answer_text=_partial,
    )

    assert "Stato=blocked_needs_attention; blocker=validator" in answer
    assert "partial product" in answer
    assert "Raw planner output preview:" in answer
    assert "Recent non-empty planner raw previews:" in answer
    assert "Deterministic strip events occurred" in answer
    assert "Vulkan/GPU0 repair result:" in answer


def test_max_steps_answer_uses_partial_when_available() -> None:
    answer = answer_for_openwebui(
        "max_steps_reached",
        "summary",
        {"partial": "partial product"},
        code_product_answer_text=_code_product,
        execution_evidence_digest_text=_evidence,
        partial_product_answer_text=_partial,
    )

    assert answer.startswith("Il loop agentico interno ha raggiunto il limite")
    assert "partial product" in answer


def test_next_action_for_openwebui_shape_is_stable() -> None:
    action = next_action_for_openwebui("blocked_needs_attention", {"blocked_by": "x"})

    assert action["action"] == "report_blocker_and_use_structured_context_for_diagnosis"
    assert action["blocked_by"] == "x"
    assert "evidence_guide_for_30b" in action["use_fields_in_order"]
    assert "answer_for_30b" not in action["use_fields_in_order"]
    assert "do_not_ignore_evidence_guide_for_30b" in action["do_not"]
    assert "do_not_invent_repo_evidence_not_present_in_tool_context_for_30b" in action["do_not"]
