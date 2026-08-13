"""Tests for evidence/audit_guidance.py — shared guidance for semantic audits."""

from __future__ import annotations

import importlib
import unittest


def _load_module():
    return importlib.import_module("services.aicarmine_broker.application.evidence.audit_guidance")


class TestGoalRequestsSemanticAudit(unittest.TestCase):
    """Test goal_requests_semantic_audit function."""

    def setUp(self):
        self.mod = _load_module()

    def test_audit_term_triggers(self):
        self.assertTrue(self.mod.goal_requests_semantic_audit("perform an audit of the codebase"))

    def test_duplicate_term_triggers(self):
        self.assertTrue(self.mod.goal_requests_semantic_audit("check for duplicate functions"))

    def test_drift_term_triggers(self):
        self.assertTrue(self.mod.goal_requests_semantic_audit("analyze layer drift in the codebase"))

    def test_no_issue_does_not_trigger(self):
        self.assertFalse(self.mod.goal_requests_semantic_audit("just write a new feature"))

    def test_empty_goal_does_not_trigger(self):
        self.assertFalse(self.mod.goal_requests_semantic_audit(""))

    def test_none_goal_does_not_trigger(self):
        self.assertFalse(self.mod.goal_requests_semantic_audit(None))

    def test_italian_terms_trigger(self):
        self.assertTrue(self.mod.goal_requests_semantic_audit("analizza a fondo il codice"))
        self.assertTrue(self.mod.goal_requests_semantic_audit("analisi approfondita dei rischi"))

    def test_speculative_terms_do_not_trigger(self):
        # Speculative terms are not in AUDIT_TRIGGER_TERMS
        self.assertFalse(self.mod.goal_requests_semantic_audit("probabilmente non ci sono problemi"))


class TestAuditOwnerTargets(unittest.TestCase):
    """Test audit_owner_targets function."""

    def setUp(self):
        self.mod = _load_module()

    def test_returns_tuple(self):
        result = self.mod.audit_owner_targets()
        self.assertIsInstance(result, tuple)

    def test_returns_same_as_constant(self):
        result = self.mod.audit_owner_targets()
        self.assertEqual(result, self.mod.AUDIT_OWNER_TARGETS)

    def test_structure_valid(self):
        result = self.mod.audit_owner_targets()
        for item in result:
            self.assertEqual(len(item), 2)
            aliases, paths = item
            self.assertIsInstance(aliases, tuple)
            self.assertIsInstance(paths, tuple)
            for alias in aliases:
                self.assertIsInstance(alias, str)
            for path in paths:
                self.assertIsInstance(path, str)


class TestAuditGuidanceForGoal(unittest.TestCase):
    """Test audit_guidance_for_goal function."""

    def setUp(self):
        self.mod = _load_module()

    def test_requested_true_for_audit(self):
        guidance = self.mod.audit_guidance_for_goal("perform a semantic audit")
        self.assertTrue(guidance["requested"])
        self.assertEqual(guidance["schema"], "semantic_audit_guidance.v1")

    def test_requested_false_for_normal(self):
        guidance = self.mod.audit_guidance_for_goal("write a new function")
        self.assertFalse(guidance["requested"])

    def test_trigger_terms_present(self):
        guidance = self.mod.audit_guidance_for_goal("audit")
        self.assertIn("trigger_terms", guidance)
        self.assertIsInstance(guidance["trigger_terms"], list)

    def test_owner_target_families_present(self):
        guidance = self.mod.audit_guidance_for_goal("audit")
        self.assertIn("owner_target_families", guidance)
        self.assertIsInstance(guidance["owner_target_families"], list)
        for family in guidance["owner_target_families"]:
            self.assertIn("aliases", family)
            self.assertIn("paths", family)

    def test_preplanner_rule_present(self):
        guidance = self.mod.audit_guidance_for_goal("audit")
        self.assertIn("preplanner_rule", guidance)
        self.assertIsInstance(guidance["preplanner_rule"], str)

    def test_judge_rule_present(self):
        guidance = self.mod.audit_guidance_for_goal("audit")
        self.assertIn("judge_rule", guidance)
        self.assertIsInstance(guidance["judge_rule"], str)

    def test_none_goal(self):
        guidance = self.mod.audit_guidance_for_goal(None)
        self.assertFalse(guidance["requested"])


class TestRoleGuidanceForGoal(unittest.TestCase):
    """Test role_guidance_for_goal function."""

    def setUp(self):
        self.mod = _load_module()

    def test_preplanner_role(self):
        guidance = self.mod.role_guidance_for_goal("preplanner", "semantic audit")
        self.assertEqual(guidance["schema"], "agentic_loop_role_guidance.v1")
        self.assertEqual(guidance["role"], "preplanner")
        self.assertIn("rules", guidance)
        self.assertIsInstance(guidance["rules"], list)
        self.assertTrue(len(guidance["rules"]) > 0)

    def test_final_quality_judge_role(self):
        guidance = self.mod.role_guidance_for_goal("final_quality_judge", "judge quality")
        self.assertEqual(guidance["role"], "final_quality_judge")
        self.assertIn("rules", guidance)

    def test_code_product_replan_role(self):
        guidance = self.mod.role_guidance_for_goal("code_product_replan", "replan")
        self.assertEqual(guidance["role"], "code_product_replan")
        self.assertIn("rules", guidance)

    def test_planner_replan_role(self):
        guidance = self.mod.role_guidance_for_goal("planner_replan", "replan")
        self.assertEqual(guidance["role"], "planner_replan")
        self.assertIn("rules", guidance)

    def test_repair_role(self):
        guidance = self.mod.role_guidance_for_goal("repair", "repair")
        self.assertEqual(guidance["role"], "repair")
        self.assertIn("rules", guidance)

    def test_unknown_role_returns_empty_rules(self):
        guidance = self.mod.role_guidance_for_goal("unknown_role", "test")
        self.assertEqual(guidance["role"], "unknown_role")
        self.assertEqual(guidance["rules"], [])

    def test_semantic_audit_present(self):
        guidance = self.mod.role_guidance_for_goal("preplanner", "audit")
        self.assertIn("semantic_audit", guidance)
        self.assertIsInstance(guidance["semantic_audit"], dict)


class TestRoleGuidanceText(unittest.TestCase):
    """Test role_guidance_text function."""

    def setUp(self):
        self.mod = _load_module()

    def test_returns_string(self):
        text = self.mod.role_guidance_text("preplanner", "audit")
        self.assertIsInstance(text, str)

    def test_non_empty_for_known_role(self):
        text = self.mod.role_guidance_text("preplanner", "audit")
        self.assertTrue(len(text) > 0)

    def test_empty_for_unknown_role(self):
        text = self.mod.role_guidance_text("unknown_role", "test")
        self.assertEqual(text, "")


class TestFinalAuditRedFlags(unittest.TestCase):
    """Test final_audit_red_flags function."""

    def setUp(self):
        self.mod = _load_module()

    def test_speculative_terms_detected(self):
        flags = self.mod.final_audit_red_flags("probabilmente non ci sono problemi")
        self.assertIn("speculative_terms", flags)
        self.assertTrue(len(flags["speculative_terms"]) > 0)

    def test_follow_up_invitations_detected(self):
        flags = self.mod.final_audit_red_flags("vuoi che generi un report")
        self.assertIn("follow_up_invitations", flags)
        self.assertTrue(len(flags["follow_up_invitations"]) > 0)

    def test_generic_no_issue_detected(self):
        flags = self.mod.final_audit_red_flags("nessuna duplicazione significativa")
        self.assertIn("generic_no_issue_phrases", flags)
        self.assertTrue(len(flags["generic_no_issue_phrases"]) > 0)

    def test_no_flags_for_clean_answer(self):
        flags = self.mod.final_audit_red_flags("ho verificato tutte le fonti")
        # Clean answer should have empty lists
        for key in flags:
            self.assertEqual(flags[key], [])

    def test_none_input(self):
        flags = self.mod.final_audit_red_flags(None)
        for key in flags:
            self.assertEqual(flags[key], [])

    def test_empty_input(self):
        flags = self.mod.final_audit_red_flags("")
        for key in flags:
            self.assertEqual(flags[key], [])

    def test_all_keys_present(self):
        flags = self.mod.final_audit_red_flags("test")
        self.assertIn("speculative_terms", flags)
        self.assertIn("follow_up_invitations", flags)
        self.assertIn("generic_no_issue_phrases", flags)


class TestPendingReadOrSearchActions(unittest.TestCase):
    """Test pending_read_or_search_actions function."""

    def setUp(self):
        self.mod = _load_module()

    def test_non_mapping_returns_empty(self):
        actions = self.mod.pending_read_or_search_actions("not a mapping")
        self.assertEqual(actions, [])

    def test_none_returns_empty(self):
        actions = self.mod.pending_read_or_search_actions(None)
        self.assertEqual(actions, [])

    def test_empty_mapping_returns_empty(self):
        actions = self.mod.pending_read_or_search_actions({})
        self.assertEqual(actions, [])

    def test_repo_read_action_extracted(self):
        contract = {
            "candidate_next_actions": [
                {"tool": "repo_read", "path": "README.md"},
            ]
        }
        actions = self.mod.pending_read_or_search_actions(contract)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["tool"], "repo_read")

    def test_repo_semantic_search_action_extracted(self):
        contract = {
            "candidate_next_actions": [
                {"tool": "repo_semantic_search", "query": "test"},
            ]
        }
        actions = self.mod.pending_read_or_search_actions(contract)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["tool"], "repo_semantic_search")

    def test_repo_rg_search_action_extracted(self):
        contract = {
            "candidate_next_actions": [
                {"tool": "repo_rg_search", "query": "test"},
            ]
        }
        actions = self.mod.pending_read_or_search_actions(contract)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["tool"], "repo_rg_search")

    def test_repo_search_action_extracted(self):
        contract = {
            "candidate_next_actions": [
                {"tool": "repo_search", "query": "test"},
            ]
        }
        actions = self.mod.pending_read_or_search_actions(contract)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["tool"], "repo_search")

    def test_non_matching_tool_skipped(self):
        contract = {
            "candidate_next_actions": [
                {"tool": "repo_list_files", "path": "src"},
            ]
        }
        actions = self.mod.pending_read_or_search_actions(contract)
        self.assertEqual(actions, [])

    def test_required_next_tool_call_inserted_first(self):
        contract = {
            "required_next_tool_call": {"tool": "repo_read", "path": "README.md"},
            "candidate_next_actions": [
                {"tool": "repo_semantic_search", "query": "test"},
            ]
        }
        actions = self.mod.pending_read_or_search_actions(contract)
        self.assertEqual(len(actions), 2)
        # required_next_tool_call should be inserted at position 0
        self.assertEqual(actions[0]["tool"], "repo_read")
        self.assertEqual(actions[1]["tool"], "repo_semantic_search")

    def test_invalid_item_skipped(self):
        contract = {
            "candidate_next_actions": [
                "not a dict",
                123,
                None,
            ]
        }
        actions = self.mod.pending_read_or_search_actions(contract)
        self.assertEqual(actions, [])


if __name__ == "__main__":
    unittest.main()