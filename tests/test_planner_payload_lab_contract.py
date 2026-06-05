from __future__ import annotations

import json
import importlib.util
import sys
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


def _load_planner_lab_module() -> ModuleType:
    source_path = ROOT / "services" / "aicarmine_broker" / "application" / "public_payload" / "planner_lab.py"
    spec = importlib.util.spec_from_file_location("planner_lab_contract_probe", source_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


planner_lab = _load_planner_lab_module()
build_payload_redundancy_audit = planner_lab.build_payload_redundancy_audit
build_planner_lab_apply_tool_call = planner_lab.build_planner_lab_apply_tool_call
build_planner_lab_compose_request = planner_lab.build_planner_lab_compose_request
build_planner_payload_lab = planner_lab.build_planner_payload_lab
parse_planner_lab_compose_response = planner_lab.parse_planner_lab_compose_response


def _terminal_response() -> dict:
    return {
        "ok": True,
        "status": "completed",
        "evidence_guide_for_30b": "evidence guide",
        "payload_index_for_30b": {
            "concrete_results": [
                {"payload_type": "old_text_new_text", "field": "tool_context_for_30b.artifacts[0].artifact"}
            ]
        },
        "priority_evidence_for_30b": {
            "items": [
                {
                    "kind": "code_edit_proposal",
                    "target_file": "pkg/a.py",
                    "old_text": "old",
                    "new_text": "new",
                }
            ]
        },
        "tool_context_for_30b": json.dumps(
            {
                "artifacts": [
                    {
                        "tool": "repo_propose_code_edit",
                        "artifact": {
                            "kind": "code_edit_proposal",
                            "target_file": "pkg/a.py",
                            "edit_kind": "structured_edit",
                            "old_text": "old",
                            "new_text": "new",
                            "manual_review_required": True,
                            "source_writes_performed": False,
                            "patch_application_performed": False,
                        },
                    }
                ]
            }
        ),
    }


def test_planner_payload_lab_uses_operator_selected_limits() -> None:
    ia_payload = {
        "ok": True,
        "job": {"job_id": "job-lab", "status": "completed", "goal": "job-lab"},
        "steps": [
            {"step": 1, "planner_decision": {"action": "tool", "tool": "repo_read"}},
            {"step": 2, "planner_decision": {"action": "tool", "tool": "repo_propose_code_edit"}},
        ],
    }

    result = build_planner_payload_lab(
        job_id="job-lab",
        ia_view_payload=ia_payload,
        terminal_response=_terminal_response(),
        summary_text_chars=1200,
        step_summary_limit=1,
        code_product_limit=1,
    )

    assert result["schema"] == "planner_payload_lab.v1"
    assert result["operator_limits"] == {
        "summary_text_chars": 1200,
        "step_summary_limit": 1,
        "code_product_limit": 1,
    }
    assert result["chat_turn"]["schema"] == "planner_lab_chat_turn.v1"
    assert result["chat_turn"]["user_message"] == "job-lab"
    assert result["chat_turn"]["assistant_message"] == "evidence guide"
    assert result["chat_turn"]["thinking_step_summary"] == result["thinking_step_summary"]
    assert len(result["step_summaries"]) == 1
    assert len(result["code_products"]) == 1
    assert result["payload_readiness"]["apply_supported_candidates"] == 1
    assert result["code_products"][0]["apply_tool_call"]["tool"] == "repo_apply_patch"
    assert result["redundancy_audit"]["ok"] is True
    assert result["redundancy_audit"]["single_global_guide_field"] == "evidence_guide_for_30b"


def test_planner_payload_lab_redundancy_audit_flags_duplicate_aliases() -> None:
    audit = build_payload_redundancy_audit(
        openwebui_payload={
            "evidence_guide_for_30b": "guide",
            "answer_for_30b": "guide",
            "message_for_30b": "guide",
            "summary_for_30b": "guide",
            "content": "guide",
        },
        tool_context={
            "answer_for_30b": "guide",
            "artifact": {"content": "real artifact content"},
        },
        evidence_guide="guide",
    )

    assert audit["ok"] is False
    assert audit["duplicated_top_level_aliases"] == [
        "answer_for_30b",
        "message_for_30b",
        "summary_for_30b",
        "content",
    ]
    assert audit["tool_context_root_aliases"] == ["answer_for_30b"]
    assert "top_level_duplicate_narrative_aliases" in audit["violations"]
    assert "tool_context_root_narrative_aliases" in audit["violations"]


def test_planner_payload_lab_redundancy_audit_allows_nested_artifact_content() -> None:
    audit = build_payload_redundancy_audit(
        openwebui_payload={"evidence_guide_for_30b": "guide"},
        tool_context={"artifact": {"content": "real artifact content"}},
        evidence_guide="guide",
    )

    assert audit["ok"] is True
    assert audit["tool_context_root_aliases"] == []
    assert audit["duplicated_top_level_aliases"] == []


def test_planner_payload_lab_does_not_claim_unified_diff_is_directly_apply_supported() -> None:
    terminal = _terminal_response()
    terminal["tool_context_for_30b"] = {
        "artifacts": [
            {
                "artifact": {
                    "kind": "code_edit_proposal",
                    "target_file": "pkg/a.py",
                    "edit_kind": "unified_diff",
                    "unified_diff": "--- a/pkg/a.py\n+++ b/pkg/a.py\n@@\n-old\n+new\n",
                }
            }
        ]
    }
    terminal["priority_evidence_for_30b"] = {
        "items": [{"target_file": "pkg/a.py", "unified_diff": "--- a/pkg/a.py\n+++ b/pkg/a.py\n"}]
    }

    result = build_planner_payload_lab(
        job_id="job-lab",
        ia_view_payload={"ok": True, "job": {"job_id": "job-lab"}, "steps": []},
        terminal_response=terminal,
    )

    candidate = result["code_products"][0]
    assert candidate["has_unified_diff"] is True
    assert candidate["apply_supported"] is False
    assert candidate["apply_block_reason"] == "unified_diff_present_but_repo_apply_patch_requires_exact_old_text_new_text"


def test_planner_lab_apply_requires_confirm_and_exact_old_new_payload() -> None:
    ia_payload = {"ok": True, "job": {"job_id": "job-lab"}, "steps": []}
    terminal = _terminal_response()
    lab_payload = build_planner_payload_lab(
        job_id="job-lab",
        ia_view_payload=ia_payload,
        terminal_response=terminal,
    )
    candidate = lab_payload["code_products"][0]

    blocked = build_planner_lab_apply_tool_call(
        lab_payload,
        candidate_id=candidate["candidate_id"],
        confirm_apply=False,
    )
    assert blocked["ok"] is False
    assert blocked["error"] == "apply_requires_confirm_apply_true"

    applied = build_planner_lab_apply_tool_call(
        lab_payload,
        candidate_id=candidate["candidate_id"],
        confirm_apply=True,
    )
    assert applied["ok"] is True
    assert applied["apply_tool"] == "repo_apply_patch"
    assert applied["arguments"]["path"] == "pkg/a.py"


def test_planner_lab_compose_request_uses_ollama_structured_output_schema() -> None:
    lab_payload = build_planner_payload_lab(
        job_id="job-lab",
        ia_view_payload={"ok": True, "job": {"job_id": "job-lab", "goal": "describe repo"}, "steps": []},
        terminal_response=_terminal_response(),
    )

    request = build_planner_lab_compose_request(
        lab_payload,
        model="qwen3-coder:30b",
        user_instruction="descrivi dettagliatamente",
        conversation=[
            {"role": "operator", "content": "prima domanda"},
            {"role": "assistant", "content": "prima risposta"},
        ],
        think=True,
        max_payload_chars=12000,
    )

    assert request["model"] == "qwen3-coder:30b"
    assert request["stream"] is False
    assert request["think"] is True
    assert "tools" not in request
    assert request["format"]["type"] == "object"
    assert "answer_markdown" in request["format"]["required"]
    assert len(request["messages"]) == 2
    assert "Do not call tools" in request["messages"][0]["content"]
    assert "guided_conversation_tail" in request["messages"][1]["content"]
    assert "prima domanda" in request["messages"][1]["content"]
    assert "openwebui_bound_payload_window" in request["messages"][1]["content"]


def test_planner_lab_compose_response_parses_structured_answer() -> None:
    response = {
        "message": {
            "thinking": "checking payload",
            "content": json.dumps(
                {
                    "answer_markdown": "answer",
                    "payload_assessment": {
                        "sufficient": True,
                        "reason": "payload has evidence",
                        "used_fields": ["evidence_guide_for_30b"],
                    },
                    "missing_payload": [],
                    "code_products": [],
                    "apply_readiness": {"can_apply_any": False, "reason": "no candidates"},
                    "follow_up_questions": [],
                }
            ),
        }
    }

    parsed = parse_planner_lab_compose_response(response)

    assert parsed["ok"] is True
    assert parsed["structured_answer"]["answer_markdown"] == "answer"
    assert parsed["thinking"] == "checking payload"


def test_planner_lab_routes_are_hidden_from_openapi_by_source_contract() -> None:
    app_source = (ROOT / "services" / "aicarmine_broker" / "app.py").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert '@app.get("/planner-lab", include_in_schema=False)' in app_source
    assert '@app.post("/planner-lab/start", include_in_schema=False)' in app_source
    assert 'planner-lab.json", include_in_schema=False)' in app_source
    assert 'planner-lab/apply", include_in_schema=False)' in app_source
    assert 'planner-lab/compose", include_in_schema=False)' in app_source


def test_planner_lab_html_renders_chat_and_thinking_surface() -> None:
    html_source = (ROOT / "services" / "aicarmine_broker" / "job_planner_lab.py").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "Chat + Thinking Step Summary" in html_source
    assert "Operator-only 3572 chat + thinking-step-summary console" in html_source
    assert "30B top-level surface" in html_source
    assert "Redundancy audit JSON" in html_source
    assert "renderChatTurn" in html_source
    assert "renderTopLevelSurface" in html_source
    assert "thinking_step_summary" in html_source
    assert "OpenWebUI-bound assistant payload" in html_source
    assert "repo_apply_patch tool call" in html_source
    assert "copyApplyToolCall" in html_source
    assert "Apply exact old/new patch" in html_source
    assert "Start + wait for payload" in html_source
    assert "composeFromPayload" in html_source
    assert "Guided payload conversation" in html_source
    assert "Ask payload composer (wait)" in html_source
    assert "guidedConversation" in html_source
    assert "renderGuidedConversation" in html_source
    assert "thinking trace / raw result" in html_source
