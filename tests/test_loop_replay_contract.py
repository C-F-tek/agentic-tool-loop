from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))


from aicarmine_broker.application.replay import replay_loop_job  # noqa: E402


def _write_job(root: Path, *, history: list[dict], goal: str = "read README.md") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "tool-results").mkdir()
    (root / "planner-stream").mkdir()
    (root / "job.json").write_text(
        json.dumps({"job_id": "job-test", "goal": goal, "history": history}),
        encoding="utf-8",
    )
    (root / "events.ndjson").write_text(
        json.dumps({"event_type": "planner_decision"}) + "\n",
        encoding="utf-8",
    )
    (root / "tool-results" / "step-001-repo_read.json").write_text(
        json.dumps({"ok": True, "tool": "repo_read"}),
        encoding="utf-8",
    )
    (root / "planner-stream" / "step-001.txt").write_text("{}", encoding="utf-8")


def _evidence_contract() -> dict:
    return {
        "candidate_next_actions": [
            {
                "tool": "repo_read",
                "arguments": {"paths": ["README.md"]},
                "action_id": "readme",
            }
        ],
        "validator_admissible_repo_read_paths": ["README.md"],
        "evidence_coverage": {
            "schema": "evidence_coverage_score.v1",
            "coverage_score": 0.5,
            "diagnostic_only": True,
        },
    }


def test_loop_replay_loads_job_history(tmp_path: Path) -> None:
    _write_job(tmp_path, history=[{"step": 1, "decision": {"action": "tool", "tool": "repo_read"}}])

    report = replay_loop_job(
        job_root=tmp_path,
        evidence_builder=lambda goal, history: _evidence_contract(),
        validator=lambda goal, decision, history: {"ok": True, "violations": []},
    )

    assert report["schema"] == "loop_replay_report.v1"
    assert report["diagnostic_only"] is True
    assert report["job_id"] == "job-test"
    assert report["history_events"] == 1
    assert report["event_count"] == 1
    assert report["tool_result_file_count"] == 1
    assert report["planner_stream_file_count"] == 1


def test_loop_replay_recomputes_evidence_contract(tmp_path: Path) -> None:
    calls: list[tuple[str, int]] = []

    def evidence_builder(goal: str, history: list[dict]) -> dict:
        calls.append((goal, len(history)))
        return _evidence_contract()

    _write_job(tmp_path, history=[{"step": 1, "decision": {"action": "tool", "tool": "repo_read"}}])

    report = replay_loop_job(
        job_root=tmp_path,
        evidence_builder=evidence_builder,
        validator=lambda goal, decision, history: {"ok": True, "violations": []},
    )

    assert calls == [("read README.md", 1)]
    assert report["candidate_actions_recomputed"][0]["action_id"] == "readme"
    assert report["evidence_coverage"]["schema"] == "evidence_coverage_score.v1"


def test_loop_replay_detects_repeated_invalid_decision(tmp_path: Path) -> None:
    rejected = {
        "tool": "controller_guard",
        "violations": ["repo_read_already_successful:README.md"],
        "rejected_decision": {"action": "tool", "tool": "repo_read", "arguments": {"path": "README.md"}},
    }
    history = [
        {"step": 1, "tool_result": rejected},
        {"step": 2, "tool_result": rejected},
    ]
    _write_job(tmp_path, history=history)

    report = replay_loop_job(
        job_root=tmp_path,
        evidence_builder=lambda goal, history: _evidence_contract(),
        validator=lambda goal, decision, history: {"ok": True, "violations": []},
    )

    assert report["suspected_loop"] is True
    assert report["first_divergence"]["kind"] == "repeated_invalid_decision"
    assert report["repeated_invalid_decisions"][0]["count"] == 2


def test_loop_replay_counts_rejections_from_events_ndjson(tmp_path: Path) -> None:
    _write_job(tmp_path, history=[])
    rejected = {
        "event_type": "planner_decision_rejected",
        "step": 4,
        "payload": {
            "tool": "controller_guard",
            "guard_type": "planner_decision_validation",
            "summary": "planner_decision_validation_failed: planner_final_required_empty_output",
            "violations": ["planner_final_required_empty_output"],
            "rejected_decision": {"action": "block"},
        },
    }
    (tmp_path / "events.ndjson").write_text(json.dumps(rejected) + "\n", encoding="utf-8")

    report = replay_loop_job(
        job_root=tmp_path,
        evidence_builder=lambda goal, history: _evidence_contract(),
        validator=lambda goal, decision, history: {"ok": True, "violations": []},
    )

    assert report["validator_rejections"] == 1
    assert report["validator_rejections_preview"][0]["source"] == "events_ndjson"
    assert report["validator_rejections_preview"][0]["violations"] == [
        "planner_final_required_empty_output"
    ]


def test_loop_replay_detects_candidate_validator_mismatch(tmp_path: Path) -> None:
    _write_job(tmp_path, history=[])

    report = replay_loop_job(
        job_root=tmp_path,
        evidence_builder=lambda goal, history: {
            "candidate_next_actions": [
                {
                    "tool": "repo_read",
                    "arguments": {"paths": ["missing.py"]},
                    "action_id": "missing",
                }
            ],
            "validator_admissible_repo_read_paths": [],
        },
        validator=lambda goal, decision, history: {"ok": True, "violations": []},
    )

    assert report["first_divergence"]["kind"] == "candidate_validator_mismatch"
    assert report["candidate_validator_mismatches"][0]["path"] == "missing.py"


def test_loop_replay_report_is_json_serializable(tmp_path: Path) -> None:
    _write_job(tmp_path, history=[{"step": 1, "decision": {"action": "final", "final_answer": "x"}}])

    report = replay_loop_job(
        job_root=tmp_path,
        evidence_builder=lambda goal, history: _evidence_contract(),
        validator=lambda goal, decision, history: {"ok": False, "violations": ["final_not_allowed"]},
    )

    assert report["validator_results_recomputed"][0]["ok"] is False
    json.dumps(report)


def test_loop_replay_target_coverage_ignores_controller_preseed_only(tmp_path: Path) -> None:
    _write_job(
        tmp_path,
        history=[
            {
                "step": 0,
                "decision": {"action": "controller_preseed", "tool": "repo_read"},
                "tool_result": {"tool": "repo_read", "ok": True, "controller_preseed": True},
            }
        ],
    )

    report = replay_loop_job(
        job_root=tmp_path,
        target_tool="repo_read",
        evidence_builder=lambda goal, history: _evidence_contract(),
        validator=lambda goal, decision, history: {"ok": True, "violations": []},
    )

    assert report["target_tool_coverage"]["covered"] is False
    assert report["target_tool_coverage"]["reason"] == "target_tool_not_attempted_after_planner"


def test_loop_replay_target_coverage_requires_planner_turn_attempt(tmp_path: Path) -> None:
    _write_job(
        tmp_path,
        history=[
            {
                "step": 1,
                "decision": {"action": "tool", "tool": "repo_read"},
                "tool_result": {"tool": "repo_read", "ok": True},
            }
        ],
    )

    report = replay_loop_job(
        job_root=tmp_path,
        target_tool="repo_read",
        evidence_builder=lambda goal, history: _evidence_contract(),
        validator=lambda goal, decision, history: {"ok": True, "violations": []},
    )

    assert report["target_tool_coverage"]["covered"] is True
    assert report["target_tool_coverage"]["matched_step"] == 1
    assert report["target_tool_coverage"]["matched_kind"] == "decision"


def test_loop_replay_target_coverage_uses_events_when_history_is_empty(tmp_path: Path) -> None:
    _write_job(tmp_path, history=[])
    events = [
        {
            "event_type": "planner_decision",
            "step": 1,
            "payload": {"action": "tool", "tool": "repo_read", "arguments": {"path": "README.md"}},
        },
        {
            "event_type": "tool_start",
            "step": 1,
            "payload": {"tool": "repo_read", "arguments": {"path": "README.md"}},
        },
        {
            "event_type": "tool_result",
            "step": 1,
            "payload": {"tool": "repo_read", "ok": True},
        },
    ]
    (tmp_path / "events.ndjson").write_text(
        "\n".join(json.dumps(row) for row in events) + "\n",
        encoding="utf-8",
    )

    report = replay_loop_job(
        job_root=tmp_path,
        target_tool="repo_read",
        evidence_builder=lambda goal, history: _evidence_contract(),
        validator=lambda goal, decision, history: {"ok": True, "violations": []},
    )

    coverage = report["target_tool_coverage"]
    assert coverage["covered"] is True
    assert coverage["matched_source"] == "events_ndjson"
    assert coverage["matched_step"] == 1
    assert coverage["matched_kind"] == "planner_decision_event"


def test_loop_replay_full_loop_audit_uses_persisted_runtime_artifacts(tmp_path: Path) -> None:
    _write_job(
        tmp_path,
        history=[
            {
                "step": 1,
                "decision": {"action": "tool", "tool": "repo_read"},
                "tool_result": {"tool": "repo_read", "ok": True},
            }
        ],
    )
    job = {
        "job_id": "job-test",
        "goal": "read README.md",
        "public_tool_name": "vulkan_helper",
        "request_payload": {
            "tool_name": "vulkan_helper",
            "bridge_public_tool_x": "vulkan_helper",
        },
        "original_args": {},
        "history": [
            {
                "step": 1,
                "decision": {"action": "tool", "tool": "repo_read"},
                "tool_result": {"tool": "repo_read", "ok": True},
            }
        ],
    }
    (tmp_path / "job.json").write_text(json.dumps(job), encoding="utf-8")
    events = [
        {"event_type": "job_queued"},
        {"event_type": "agentic_loop_started"},
        {"event_type": "planner_request_started"},
        {"event_type": "planner_decision"},
        {"event_type": "tool_result"},
    ]
    (tmp_path / "events.ndjson").write_text(
        "\n".join(json.dumps(row) for row in events) + "\n",
        encoding="utf-8",
    )
    prompt_dir = tmp_path / "planner-prompts"
    prompt_dir.mkdir()
    (prompt_dir / "step-001-planner-payload.json").write_text(
        json.dumps(
            {
                "planner_payload": {
                    "messages": [{"role": "user", "content": "payload"}],
                    "tools": [{"type": "function", "function": {"name": "repo_read"}}],
                },
                "user_payload": {
                    "explicit_request_context": {
                        "target_internal_tool": "repo_read",
                        "target_arguments": {"path": "README.md"},
                    },
                    "prompt_pack_contract": {
                        "native_tools_schema_accounted_in_budget": True,
                        "native_tools_schema_chars": 100,
                    },
                    "evidence_contract": {},
                    "available_tools": [],
                    "required_working_set": {},
                },
            }
        ),
        encoding="utf-8",
    )

    report = replay_loop_job(
        job_root=tmp_path,
        target_tool="repo_read",
        require_full_loop=True,
        evidence_builder=lambda goal, history: _evidence_contract(),
        validator=lambda goal, decision, history: {"ok": True, "violations": []},
    )

    audit = report["runtime_loop_artifact_audit"]
    assert audit["schema"] == "runtime_loop_artifact_audit.v1"
    assert audit["ok"] is True
    assert audit["planner_prompt"]["target_tool_in_native_schema"] is True


def test_loop_replay_full_loop_accepts_typed_guard_without_tool_result_file(tmp_path: Path) -> None:
    _write_job(tmp_path, history=[])
    for artifact in (tmp_path / "tool-results").glob("*.json"):
        artifact.unlink()
    job = {
        "job_id": "job-test",
        "goal": "run repo_ast_grep_dry_run",
        "public_tool_name": "vulkan_helper",
        "request_payload": {
            "tool_name": "vulkan_helper",
            "bridge_public_tool_x": "vulkan_helper",
        },
        "original_args": {},
        "history": [],
    }
    (tmp_path / "job.json").write_text(json.dumps(job), encoding="utf-8")
    events = [
        {"event_type": "job_queued"},
        {"event_type": "agentic_loop_started"},
        {"event_type": "planner_request_started"},
        {
            "event_type": "planner_decision_rejected",
            "step": 1,
            "payload": {
                "tool": "controller_guard",
                "summary": "planner_decision_validation_failed: repo_ast_grep_dry_run_missing_pattern_or_rewrite",
                "violations": ["repo_ast_grep_dry_run_missing_pattern_or_rewrite"],
                "rejected_decision": {"action": "tool", "tool": "repo_ast_grep_dry_run"},
            },
        },
    ]
    (tmp_path / "events.ndjson").write_text(
        "\n".join(json.dumps(row) for row in events) + "\n",
        encoding="utf-8",
    )
    prompt_dir = tmp_path / "planner-prompts"
    prompt_dir.mkdir(exist_ok=True)
    (prompt_dir / "step-001-planner-payload.json").write_text(
        json.dumps(
            {
                "planner_payload": {
                    "messages": [{"role": "user", "content": "payload"}],
                    "tools": [{"type": "function", "function": {"name": "repo_ast_grep_dry_run"}}],
                },
                "user_payload": {
                    "explicit_request_context": {
                        "target_internal_tool": "repo_ast_grep_dry_run",
                        "target_arguments": {"path": "a.py", "pattern": "def $F($$$A): $$$B"},
                    },
                    "prompt_pack_contract": {
                        "native_tools_schema_accounted_in_budget": True,
                        "native_tools_schema_chars": 100,
                    },
                    "evidence_contract": {},
                    "available_tools": [],
                    "required_working_set": {},
                },
            }
        ),
        encoding="utf-8",
    )
    stream_dir = tmp_path / "planner-stream"
    stream_dir.mkdir(exist_ok=True)
    (stream_dir / "step-001.jsonl").write_text("{}", encoding="utf-8")

    report = replay_loop_job(
        job_root=tmp_path,
        target_tool="repo_ast_grep_dry_run",
        require_full_loop=True,
        evidence_builder=lambda goal, history: _evidence_contract(),
        validator=lambda goal, decision, history: {"ok": False, "violations": []},
    )

    audit = report["runtime_loop_artifact_audit"]
    assert audit["ok"] is True
    assert audit["tool_result_file_count"] == 0
    assert audit["target_tool_coverage"]["matched_kind"] == "typed_guard_event"
