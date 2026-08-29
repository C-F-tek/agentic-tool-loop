#!/usr/bin/env python3
"""Verify the base-tools-invariant across ToolSurfacePolicy.tools_for_turn().

Per ogni scenario, la lista risultante DEVE contenere SEMPRE i core agentic
discovery tools (repo_read, repo_list_files, repo_tree, repo_search).

Questo test verifica l'invariant dei base tools sempre presenti nella lista
finale di tools_for_turn(), indipendentemente dal contenuto di
dynamic_tool_suggestions.
"""

from __future__ import annotations

import os
import sys
import unittest


# ---------------------------------------------------------------------------
# Path resolution – aggiungere al Python path i directory necessari perché gli
# imports relativi in turn_surface_policy.py funzionino correttamente.
# ---------------------------------------------------------------------------
_here = os.path.dirname(__file__)  # tools/
_project_root = os.path.abspath(os.path.join(_here, ".."))  # c:/Users/someo/agentic-tool-loop

# Aggiungere services/ al PYTHONPATH per permettere gli imports relativi
_services_path = os.path.join(_project_root, "services")
if _services_path not in sys.path:
    sys.path.insert(0, _services_path)

# Importare il policy module come parte del package aicarmine_broker.application.tool_surface
from aicarmine_broker.application.tool_surface.turn_surface_policy import (  # noqa: E402
    ToolSurfacePolicy as _ToolSurfacePolicy,
)


class TestBaseToolsInvariant(unittest.TestCase):
    """Verify that core agentic discovery tools are ALWAYS present in tools_for_turn()."""

    def setUp(self) -> None:
        self.policy = _ToolSurfacePolicy(order_tool_names=lambda names: sorted(names))

    # -- Core invariant tests ---------------------------------------------------------

    def test_base_tools_always_present_empty_contract(self) -> None:
        """Con un contract vuoto, i base tools devono esserci."""
        result = self.policy.tools_for_turn(
            goal="test obiettivo generico",
            evidence_contract={},  # type: ignore
            intrinsic_context={},  # type: ignore
        )
        for tool in ("repo_read", "repo_list_files", "repo_tree", "repo_search"):
            self.assertIn(tool, result, f"{tool} mancante nel risultato con contract vuoto")

    def test_base_tools_always_present_with_dynamic_suggestions_only(self) -> None:
        """Anche quando dynamic_tool_suggestions contiene SOLO tool specifici (niente base),
        questi DEVONO essere aggiunti MA I BASE TOOLS DESSONO RESTARE."""
        contract: dict[str, object] = {
            "semantic_goal_classification": {"class": "analysis_only"},
            "coverage_satisfied": True,  # Evita early return coverage_required
            "dynamic_tool_suggestions": {
                "schema": "planner_dynamic_tool_suggestion.v1",
                "tools": ["repo_ruff_check", "repo_pyright_check"],
                "details": [
                    {"tool": "repo_ruff_check", "score": 85},
                    {"tool": "repo_pyright_check", "score": 75},
                ],
                "reason": "Dynamic suggestion based on loop state",
            },
        }
        result = self.policy.tools_for_turn(
            goal="analizza services/aicarmine_broker/planner.py",
            evidence_contract=contract,  # type: ignore
            intrinsic_context={},  # type: ignore
        )
        # Base tools invariant: devono esserci SEMPRE
        for tool in ("repo_read", "repo_list_files", "repo_tree", "repo_search"):
            self.assertIn(tool, result, f"{tool} mancante con dynamic suggestions attive")

    def test_base_tools_always_present_with_high_score_dynamic(self) -> None:
        """Con dynamic suggestions ad alto score (>=60), i base tools restano."""
        contract: dict[str, object] = {
            "semantic_goal_classification": {"class": "code_product_report"},
            "coverage_satisfied": True,  # Evita early return coverage_required
            "dynamic_tool_suggestions": {
                "schema": "planner_dynamic_tool_suggestion.v1",
                "tools": ["repo_semgrep_scan"],
                "details": [
                    {"tool": "repo_semgrep_scan", "score": 90},
                ],
                "reason": "Security analysis suggested",
            },
        }
        result = self.policy.tools_for_turn(
            goal="analisi di sicurezza su app/index.js",
            evidence_contract=contract,  # type: ignore
            intrinsic_context={},  # type: ignore
        )
        # repo_semgrep_scan DEVE essere presente (alto score + keyword security nel goal)
        self.assertIn("repo_semgrep_scan", result)
        # Base tools invariant: devono esserci SEMPRE
        for tool in ("repo_read", "repo_list_files", "repo_tree", "repo_search"):
            self.assertIn(tool, result, f"{tool} mancante con security scan suggerito")

    def test_base_tools_always_present_with_low_score_dynamic(self) -> None:
        """Con dynamic suggestions a basso score (<60), dovrebbero essere filtrate MA
        i base tools devono comunque esserci."""
        contract: dict[str, object] = {
            "semantic_goal_classification": {"class": "analysis_only"},
            "coverage_satisfied": True,  # Evita early return coverage_required
            "dynamic_tool_suggestions": {
                "schema": "planner_dynamic_tool_suggestion.v1",
                "tools": ["repo_ruff_check"],
                "details": [
                    {"tool": "repo_ruff_check", "score": 45},  # < 60 threshold
                ],
                "reason": "Low-score suggestion",
            },
        }
        result = self.policy.tools_for_turn(
            goal="analizza codice Python",
            evidence_contract=contract,  # type: ignore
            intrinsic_context={},  # type: ignore
        )
        # repo_ruff_check NON dovrebbe esserci (score < 60)
        # Ma i base tools DESSONO esserci SEMPRE
        for tool in ("repo_read", "repo_list_files", "repo_tree", "repo_search"):
            self.assertIn(tool, result, f"{tool} mancante con low-score dynamic")

    def test_base_tools_always_present_with_empty_dynamic(self) -> None:
        """Con dynamic_tool_suggestions vuoto o senza details, i base tools restano."""
        contract: dict[str, object] = {
            "semantic_goal_classification": {"class": "analysis_only"},
            "coverage_satisfied": True,  # Evita early return coverage_required
            "dynamic_tool_suggestions": {
                "schema": "planner_dynamic_tool_suggestion.v1",
                "tools": [],
                "details": [],
                "reason": "No suggestions available",
            },
        }
        result = self.policy.tools_for_turn(
            goal="test obiettivo generico",
            evidence_contract=contract,  # type: ignore
            intrinsic_context={},  # type: ignore
        )
        for tool in ("repo_read", "repo_list_files", "repo_tree", "repo_search"):
            self.assertIn(tool, result, f"{tool} mancante con dynamic vuota")

    def test_base_tools_always_present_no_dynamic_field(self) -> None:
        """Quando il contract NON contiene dynamic_tool_suggestions (caso legacy),
        i base tools devono esserci come prima."""
        contract: dict[str, object] = {
            "semantic_goal_classification": {"class": "code_product_report"},
            "coverage_satisfied": True,  # Evita early return coverage_required
            # NIENTE dynamic_tool_suggestions — caso legacy puro
        }
        result = self.policy.tools_for_turn(
            goal="genera report da planner.py",
            evidence_contract=contract,  # type: ignore
            intrinsic_context={},  # type: ignore
        )
        for tool in ("repo_read", "repo_list_files", "repo_tree", "repo_search"):
            self.assertIn(tool, result, f"{tool} mancante senza campo dynamic")

    def test_base_tools_invariant_with_candidate_actions(self) -> None:
        """Con candidate_next_actions nel contract, i base tools restano."""
        contract: dict[str, object] = {
            "semantic_goal_classification": {"class": "analysis_only"},
            "coverage_satisfied": True,  # Evita early return coverage_required
            "candidate_next_actions": [
                {"tool": "repo_ruff_check", "args": {"path": "planner.py"}},
                {"tool": "repo_pyright_check", "args": {"path": "config/models.py"}},
            ],
            "dynamic_tool_suggestions": {
                "schema": "planner_dynamic_tool_suggestion.v1",
                "tools": ["repo_semgrep_scan"],
                "details": [{"tool": "repo_semgrep_scan", "score": 70}],
            },
        }
        result = self.policy.tools_for_turn(
            goal="analizza e verifica codice Python",
            evidence_contract=contract,  # type: ignore
            intrinsic_context={},  # type: ignore
        )
        for tool in ("repo_read", "repo_list_files", "repo_tree", "repo_search"):
            self.assertIn(tool, result, f"{tool} mancante con candidate actions + dynamic")

    def test_base_tools_invariant_with_keyword_expansion(self) -> None:
        """Con keyword expansion (security → semgrep), i base tools restano."""
        contract: dict[str, object] = {
            "semantic_goal_classification": {"class": "analysis_only"},
            "coverage_satisfied": True,  # Evita early return coverage_required
            "dynamic_tool_suggestions": {
                "schema": "planner_dynamic_tool_suggestion.v1",
                "tools": [],
                "details": [],
            },
        }
        result = self.policy.tools_for_turn(
            goal="analisi di sicurezza e vulnerability su repository",
            evidence_contract=contract,  # type: ignore
            intrinsic_context={},  # type: ignore
        )
        # Keyword expansion dovrebbe aggiungere repo_semgrep_scan
        self.assertIn("repo_semgrep_scan", result)
        # Base tools invariant: devono esserci SEMPRE
        for tool in ("repo_read", "repo_list_files", "repo_tree", "repo_search"):
            self.assertIn(tool, result, f"{tool} mancante con keyword security expansion")


if __name__ == "__main__":
    unittest.main(verbosity=True)
