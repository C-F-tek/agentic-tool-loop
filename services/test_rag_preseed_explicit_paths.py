from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

SERVICES_ROOT = Path(__file__).resolve().parent
if str(SERVICES_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICES_ROOT))

from aicarmine_broker.application.controller import rag_preseed  # noqa: E402


def _write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_files_db(db: Path, paths: list[str]) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    try:
        conn.execute("CREATE TABLE files(path TEXT PRIMARY KEY)")
        for path in paths:
            conn.execute("INSERT INTO files(path) VALUES (?)", (path,))
        conn.commit()
    finally:
        conn.close()


def test_preplanner_goal_class_ignores_negated_write_terms() -> None:
    goal = (
        "Analizza il nuovo client MCP. Leggi AGENTS.md e "
        "services/codex_bridge/agentic_loop_client_mcp_server.py. Non modificare file."
    )

    assert rag_preseed._preplanner_goal_class(goal) == "repo_analysis"
    assert rag_preseed._preplanner_goal_class("procedi con le fix e applica patch") == "apply_write"


def test_query_plan_semantic_intent_can_enrich_goal_class() -> None:
    goal = "Fammi capire il sistema di configurazione runtime e quali owner sono piu' rischiosi."

    query_plan = rag_preseed._sanitize_preplanner_query_plan(
        {
            "semantic_intent": {
                "class": "analysis_only",
                "read_only": True,
                "write_requested": False,
                "apply_requested": False,
                "requires_code_security_coverage": True,
                "rationale": "The request asks for read-only risk discovery.",
            },
            "queries": [
                {
                    "query": "runtime configuration owner validation settings",
                    "purpose": "find concrete code owners",
                }
            ],
        },
        goal=goal,
    )

    assert query_plan["ok"] is True
    assert query_plan["goal_class"] == "code_security_analysis"
    assert query_plan["semantic_intent"]["source"] == "planner_query_plan"
    assert query_plan["semantic_intent"]["accepted"] is True


def test_query_plan_semantic_intent_downgrades_unsafe_apply_from_negated_constraints() -> None:
    goal = (
        "Esegui una discovery read-only sul loop agentico. Non applicare patch, "
        "non scrivere file, non usare repo_apply_patch."
    )

    query_plan = rag_preseed._sanitize_preplanner_query_plan(
        {
            "semantic_intent": {
                "class": "apply_write",
                "read_only": True,
                "write_requested": False,
                "apply_requested": False,
                "rationale": "Incorrectly followed the patch word.",
            },
            "queries": [{"query": "agentic loop controller validation", "purpose": "find owners"}],
        },
        goal=goal,
    )

    assert query_plan["goal_class"] != "apply_write"
    assert query_plan["semantic_intent"]["accepted"] is False
    assert "planner_apply_write_without_positive_goal_evidence_downgraded" in query_plan["semantic_intent"]["guardrails"]


def test_query_plan_semantic_intent_accepts_report_only_code_product() -> None:
    goal = "Prepara un piano di modifica dettagliato per pkg/example.py senza toccare i file."

    query_plan = rag_preseed._sanitize_preplanner_query_plan(
        {
            "semantic_intent": {
                "class": "code_product_report",
                "read_only": True,
                "write_requested": False,
                "apply_requested": False,
                "rationale": "The user asks for a report/proposal, not execution.",
            },
            "queries": [{"query": "pkg/example.py change plan anchors", "purpose": "find target file"}],
        },
        goal=goal,
    )

    assert query_plan["goal_class"] == "code_product_report"
    assert query_plan["semantic_intent"]["accepted"] is True


def test_query_plan_semantic_intent_is_not_overridden_by_single_action_words() -> None:
    conceptual_apply_goal = (
        "Applica lo stesso concetto di lettura read-only al controller del loop: "
        "cerca i file owner e restituisci solo evidenze, senza modificare file."
    )
    conceptual_apply_plan = rag_preseed._sanitize_preplanner_query_plan(
        {
            "semantic_intent": {
                "class": "analysis_only",
                "read_only": True,
                "write_requested": False,
                "apply_requested": False,
                "requires_code_security_coverage": True,
                "rationale": "Apply is used as conceptual transfer, not file mutation.",
            },
            "queries": [{"query": "loop controller owner read evidence", "purpose": "find owners"}],
        },
        goal=conceptual_apply_goal,
    )

    assert conceptual_apply_plan["goal_class"] == "code_security_analysis"
    assert conceptual_apply_plan["semantic_intent"]["accepted"] is True
    assert "planner_read_only_intent_overrode_static_apply_fallback" in conceptual_apply_plan["semantic_intent"]["guardrails"]

    report_goal = "Scrivi solo un report sui rischi di services/aicarmine_broker/planner.py, non modificare file."
    report_plan = rag_preseed._sanitize_preplanner_query_plan(
        {
            "semantic_intent": {
                "class": "repo_analysis",
                "read_only": True,
                "write_requested": False,
                "apply_requested": False,
                "rationale": "Writing is the chat/report output, not repository mutation.",
            },
            "queries": [{"query": "services/aicarmine_broker/planner.py risk report", "purpose": "find target"}],
        },
        goal=report_goal,
    )

    assert report_plan["goal_class"] == "repo_analysis"
    assert report_plan["semantic_intent"]["accepted"] is True
    assert "planner_read_only_intent_overrode_static_apply_fallback" in report_plan["semantic_intent"]["guardrails"]


def test_preplanner_prompt_instructs_semantic_audit_search_contract() -> None:
    captured_payloads: list[dict[str, Any]] = []
    goal = (
        "Verifica nel codice le incongruenze semantiche e il rischio di regressione "
        "portato da funzioni logiche ripetute localmente invece che ereditate. "
        "Read-only, nessuna patch."
    )

    def fake_post_json(_url: str, payload: dict[str, Any], _timeout: int) -> dict[str, Any]:
        captured_payloads.append(payload)
        return {
            "message": {
                "content": json.dumps({
                    "semantic_intent": {
                        "class": "repo_analysis",
                        "read_only": True,
                        "write_requested": False,
                        "apply_requested": False,
                        "code_product_requested": False,
                        "requires_code_security_coverage": False,
                        "rationale": "The goal asks for read-only semantic drift analysis.",
                    },
                    "queries": [
                        {
                            "query": "planner loop validator tool_surface prompt public_payload owner",
                            "purpose": "find current owner modules before comparing wrappers",
                            "target_kind": "owner_source",
                        }
                    ],
                })
            }
        }

    query_plan = rag_preseed.controller_preplanner_rag_query_plan(
        goal,
        post_json=fake_post_json,
        planner_url="http://127.0.0.1:11434/api/chat",
        planner_model="smoke",
        keep_alive="0",
        num_ctx=262144,
        timeout=5,
    )

    assert query_plan["ok"] is True
    assert query_plan["queries"][0]["target_kind"] == "owner_source"
    request_payload = json.loads(captured_payloads[0]["messages"][1]["content"])
    constraints = request_payload["constraints"]
    assert request_payload["static_hint_is_not_authoritative"] is True
    assert "semantic_audit_search_contract" in constraints
    assert "strategy_by_semantic_intent" in constraints
    assert "validator/controller/tool-surface/prompt/public-payload owner modules" in (
        constraints["strategy_by_semantic_intent"]["repo_analysis"]
    )
    assert "README/AGENTS as the only evidence" in (
        constraints["semantic_audit_search_contract"]["invalid_primary_targets"]
    )


def test_preseed_prioritizes_explicit_db_paths_before_ranked(monkeypatch, tmp_path: Path) -> None:
    explicit_paths = [
        "AGENTS.md",
        "services/codex_bridge/agentic_loop_client_mcp_server.py",
        "services/codex_bridge/MODULE_REFERENCE.md",
    ]
    ranked_path = "services/codex_bridge/local_subagent_mcp_server.py"
    for path in [*explicit_paths, ranked_path]:
        _write(tmp_path / path)
    db = tmp_path / "state" / "controller_rag.sqlite3"
    _make_files_db(db, [*explicit_paths, ranked_path])

    class FakeIndexer:
        DEFAULT_SUFFIXES = {".py", ".md"}
        MAX_FILE_BYTES_DEFAULT = 2_000_000
        CHUNK_LINES_DEFAULT = 180
        CHUNK_CHARS_DEFAULT = 12000
        SOURCE_GIT_DEFAULT = "git"
        MODE_DELTA = "delta"

        @staticmethod
        def build_index(**_kwargs: Any) -> dict[str, Any]:
            return {"ok": True, "files_reindexed": 0}

    monkeypatch.setenv("AICARMINE_CONTROLLER_RAG_DB", str(db))
    monkeypatch.setattr(rag_preseed, "_load_codex_rag_indexer", lambda: FakeIndexer)
    monkeypatch.setattr(
        rag_preseed,
        "_ranked_paths_from_codex_rag",
        lambda **_kwargs: (
            [{"path": ranked_path, "rank_score": -99, "path_policy_score": -99}],
            {"status": "ready", "selected_paths": [ranked_path]},
            [],
        ),
    )

    goal = (
        "Analizza il nuovo client MCP agentic-loop dedicato Codex. Leggi i file reali pertinenti, "
        "in particolare AGENTS.md, services/codex_bridge/agentic_loop_client_mcp_server.py e "
        "services/codex_bridge/MODULE_REFERENCE.md. Non modificare file."
    )
    query_plan = {
        "queries": [
            {
                "query": "services/codex_bridge/agentic_loop_client_mcp_server.py capability guardrail risk",
                "purpose": "read core implementation",
            },
            {
                "query": "services/codex_bridge/MODULE_REFERENCE.md codex bridge interface specs",
                "purpose": "verify module contracts",
            },
        ]
    }

    plan, report, skipped = rag_preseed.controller_preplanner_rag_preseed_plan(
        goal,
        {"controller_rag_query_plan": query_plan},
        repo_root=tmp_path,
        safe_rel_path=lambda value: value,
        named_read_priority={},
        generic_readable_suffixes=(".py", ".md"),
        multi_file_prompt_read_chars=32768,
    )

    assert skipped == []
    assert plan is not None
    assert report["literal_target_paths"] == explicit_paths
    assert plan["arguments"]["paths"][:3] == explicit_paths
    assert plan["arguments"]["paths"][3] == ranked_path
    assert plan["preplanner_rag"]["literal_target_paths"] == explicit_paths
