#!/usr/bin/env python3
"""Standalone smoke tests for DynamicToolSurfaceController.

Loads dynamic_controller.py directly from filesystem without depending on
the full aicarmine_broker module graph or PYTHONPATH manipulation.
"""

from __future__ import annotations

import os
import sys
import unittest
import importlib.util


def _load_module(name: str, path: str):
    """Load a Python module directly from its file path."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Resolve paths relative to project ROOT (parent of both tools/ and services/)
_here = os.path.dirname(__file__)  # tools/
_project_root = os.path.abspath(os.path.join(_here, ".."))  # c:/Users/someo/agentic-tool-loop

# Build correct paths to the controller module
_ctrl_path = os.path.join(
    _project_root, "services", "aicarmine_broker", "application", "tool_surface", "dynamic_controller.py"
)

# Load the controller module directly
_ctrl_mod = _load_module("dynamic_controller", _ctrl_path)


class TestDynamicToolSurfaceController(unittest.TestCase):
    """Test the DynamicToolSurfaceController suggestion logic."""

    def setUp(self) -> None:
        self.ctrl = _ctrl_mod.DynamicToolSurfaceController()

    # -- suggest_tools ------------------------------------------------------------------

    def test_suggest_tools_empty_history_returns_goal_class(self) -> None:
        contract: dict[str, object] = {
            "semantic_goal_classification": {"class": "analysis_only"},
        }
        suggestions = self.ctrl.suggest_tools(
            goal="analizza services/aicarmine_broker",
            evidence_contract=contract,  # type: ignore
            history=[],
        )
        tool_names = [s["tool"] for s in suggestions]
        # analysis_only maps to repo_status, repo_tree, repo_search
        self.assertTrue(any(t in tool_names for t in ["repo_status", "repo_tree", "repo_search"]))

    def test_suggest_tools_code_product_class(self) -> None:
        contract: dict[str, object] = {
            "semantic_goal_classification": {"class": "code_product_report"},
        }
        suggestions = self.ctrl.suggest_tools(
            goal="genera report da planner.py",
            evidence_contract=contract,  # type: ignore
            history=[],
        )
        tool_names = [s["tool"] for s in suggestions]
        self.assertTrue(any(t in tool_names for t in ["repo_read", "repo_list_files", "planner_scratchpad_write"]))

    # -- _suggest_from_read_history ---------------------------------------------------

    def test_suggest_from_python_file(self) -> None:
        history: list[dict[str, object]] = [
            {
                "tool_result": {
                    "ok": True,
                    "tool": "repo_read",
                    "path": "services/aicarmine_broker/planner.py",
                },
            },
        ]
        suggestions = self.ctrl._suggest_from_read_history(history)
        tool_names = [s["tool"] for s in suggestions]
        self.assertIn("repo_ruff_check", tool_names)
        self.assertIn("repo_pyright_check", tool_names)

    def test_suggest_from_shell_script(self) -> None:
        history: list[dict[str, object]] = [
            {
                "tool_result": {
                    "ok": True,
                    "tool": "repo_read",
                    "path": "scripts/deploy.sh",
                },
            },
        ]
        suggestions = self.ctrl._suggest_from_read_history(history)
        tool_names = [s["tool"] for s in suggestions]
        self.assertIn("repo_shellcheck", tool_names)

    def test_suggest_from_go_file(self) -> None:
        history: list[dict[str, object]] = [
            {
                "tool_result": {
                    "ok": True,
                    "tool": "repo_read",
                    "path": "pkg/controller.go",
                },
            },
        ]
        suggestions = self.ctrl._suggest_from_read_history(history)
        tool_names = [s["tool"] for s in suggestions]
        self.assertIn("repo_command", tool_names)

    def test_suggest_from_rs_file(self) -> None:
        history: list[dict[str, object]] = [
            {
                "tool_result": {
                    "ok": True,
                    "tool": "repo_read",
                    "path": "src/main.rs",
                },
            },
        ]
        suggestions = self.ctrl._suggest_from_read_history(history)
        tool_names = [s["tool"] for s in suggestions]
        self.assertIn("repo_command", tool_names)

    def test_suggest_from_js_file(self) -> None:
        history: list[dict[str, object]] = [
            {
                "tool_result": {
                    "ok": True,
                    "tool": "repo_read",
                    "path": "app/index.js",
                },
            },
        ]
        suggestions = self.ctrl._suggest_from_read_history(history)
        tool_names = [s["tool"] for s in suggestions]
        self.assertIn("repo_semgrep_scan", tool_names)

    # -- _check_final_preconditions ---------------------------------------------------

    def test_check_final_ready_all_pass(self) -> None:
        contract: dict[str, object] = {
            "coverage_satisfied": True,
            "missing_owner_paths": [],
            "required_next_tool_call": {},
            "finalization_contract": {"final_allowed": True},
            "final_rewrite_latch": "",
        }
        ready, reasons = self.ctrl._check_final_preconditions(
            goal="test", evidence_contract=contract  # type: ignore
        )
        self.assertTrue(ready)
        self.assertEqual(reasons, [])

    def test_check_final_not_ready_coverage_fails(self) -> None:
        contract: dict[str, object] = {
            "coverage_satisfied": False,
            "missing_owner_paths": ["unread/file.py"],
            "required_next_tool_call": {"validated": True, "tool": "repo_read"},
            "finalization_contract": {"final_allowed": False},
            "final_rewrite_latch": "rewrite_required",
        }
        ready, reasons = self.ctrl._check_final_preconditions(
            goal="test", evidence_contract=contract  # type: ignore
        )
        self.assertFalse(ready)
        # Should have at least 4 failure reasons
        self.assertGreater(len(reasons), 3)

    # -- _extract_successful_read_paths -----------------------------------------------

    def test_extract_reads_from_history(self) -> None:
        history: list[dict[str, object]] = [
            {
                "tool_result": {
                    "ok": True,
                    "tool": "repo_read",
                    "path": "services/aicarmine_broker/planner.py",
                },
            },
            {
                "tool_result": {
                    "ok": True,
                    "tool": "repo_read",
                    "path": "services/aicarmine_broker/config/models.py",
                },
            },
            {
                "tool_result": {
                    "ok": False,  # Failed read should be ignored
                    "tool": "repo_read",
                    "path": "nonexistent/file.py",
                },
            },
        ]
        paths = self.ctrl._extract_successful_read_paths(history)
        self.assertEqual(len(paths), 2)
        self.assertIn("services/aicarmine_broker/planner.py", paths)
        self.assertIn("services/aicarmine_broker/config/models.py", paths)

    # -- _dedupe_and_sort -------------------------------------------------------------

    def test_dedupe_keeps_highest_score(self) -> None:
        suggestions: list[dict[str, object]] = [
            {"tool": "repo_ruff_check", "score": 50},
            {"tool": "repo_ruff_check", "score": 85},
            {"tool": "repo_pyright_check", "score": 75},
        ]
        result = self.ctrl._dedupe_and_sort(suggestions)
        ruff_entry = next((s for s in result if s["tool"] == "repo_ruff_check"), None)
        self.assertIsNotNone(ruff_entry)
        self.assertEqual(ruff_entry["score"], 85)  # Kept highest score
        self.assertEqual(len(result), 2)  # Only unique tools remain


if __name__ == "__main__":
    unittest.main(verbosity=True)
