from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def test_decision_normalizer_embedded_json_single() -> None:
    from aicarmine_broker.application.decision_normalizer import _single_embedded_json_decision

    decision = _single_embedded_json_decision('before {"action":"final","final_answer":"ok"} after')

    assert decision["action"] == "final"
    assert decision["final_answer"] == "ok"
    assert decision["deterministic_strip"]["kind"] == "single_embedded_json_decision"


def test_decision_normalizer_rejects_multiple_json_objects() -> None:
    from aicarmine_broker.application.decision_normalizer import _single_embedded_json_decision

    decision = _single_embedded_json_decision(
        '{"action":"final","final_answer":"a"} {"action":"final","final_answer":"b"}'
    )

    assert decision == {}


def test_decision_normalizer_native_single_tool_call() -> None:
    from aicarmine_broker.application.decision_normalizer import _native_tool_calls_decision

    decision = _native_tool_calls_decision(
        [
            {
                "function": {
                    "name": "repo_read",
                    "arguments": json.dumps({"path": "AGENTS.md"}),
                }
            }
        ],
        raw_text="",
    )

    assert decision["action"] == "tool"
    assert decision["tool"] == "repo_read"
    assert decision["arguments"] == {"path": "AGENTS.md"}
    assert decision["native_tool_call"] is True


def test_final_json_text_allowed_in_native_required_mode() -> None:
    from aicarmine_broker.application.decision_normalizer import normalize_planner_decision

    decision = normalize_planner_decision(
        '{"action":"final","final_answer":"done"}',
        goal="analysis",
        step=1,
        state={},
    )

    assert decision["action"] == "final"
    assert decision["final_answer"] == "done"


def test_final_answer_lines_normalized() -> None:
    from aicarmine_broker.application.decision_normalizer import normalize_planner_decision

    decision = normalize_planner_decision(
        '{"action":"final","final_answer_lines":["a","b"]}',
        goal="analysis",
        step=1,
        state={},
    )

    assert decision["final_answer"] == "a\nb"


def test_content_final_analysis_becomes_final_answer() -> None:
    from aicarmine_broker.application.decision_normalizer import normalize_planner_decision

    decision = normalize_planner_decision(
        '{"action":"final","content":{"final_analysis":"usable answer"}}',
        goal="analysis",
        step=1,
        state={},
    )

    assert decision["final_answer"] == "usable answer"
    assert decision["final_answer_source"] == "content.final_analysis"
