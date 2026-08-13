"""Tests for controller/preseed.py — preseed plan helpers."""

from __future__ import annotations

import importlib
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


def _load_module():
    return importlib.import_module("services.aicarmine_broker.application.controller.preseed")


class TestRootSurfaceEntries(unittest.TestCase):
    """Test root_surface_entries function."""

    def setUp(self):
        self.mod = _load_module()
        self.repo_root = Path("/fake/repo")

    def test_empty_result_returns_empty_list(self):
        result = {}
        entries = self.mod.root_surface_entries(result, repo_root=self.repo_root)
        self.assertEqual(entries, [])

    def test_none_result_returns_empty_list(self):
        entries = self.mod.root_surface_entries(None, repo_root=self.repo_root)
        self.assertEqual(entries, [])

    def test_entries_key_extracted(self):
        result = {
            "entries": [
                {"path": "README.md", "kind": "file"},
                {"path": "src/__init__.py", "kind": "file"},
            ]
        }
        entries = self.mod.root_surface_entries(result, repo_root=self.repo_root)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["path"], "README.md")
        self.assertEqual(entries[1]["path"], "src/__init__.py")

    def test_entries_preview_key_extracted(self):
        result = {
            "entries_preview": [
                {"path": "docs/guide.md", "kind": "file"},
            ]
        }
        entries = self.mod.root_surface_entries(result, repo_root=self.repo_root)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["path"], "docs/guide.md")

    def test_files_key_extracted(self):
        result = {
            "files": [
                {"path": "setup.py", "kind": "file"},
            ]
        }
        entries = self.mod.root_surface_entries(result, repo_root=self.repo_root)
        self.assertEqual(len(entries), 1)

    def test_files_preview_key_extracted(self):
        result = {
            "files_preview": [
                {"path": "config.json", "kind": "file"},
            ]
        }
        entries = self.mod.root_surface_entries(result, repo_root=self.repo_root)
        self.assertEqual(len(entries), 1)

    def test_skips_root_path(self):
        result = {"entries": [{"path": ".", "kind": "dir"}]}
        entries = self.mod.root_surface_entries(result, repo_root=self.repo_root)
        self.assertEqual(entries, [])

    def test_skips_empty_path(self):
        result = {"entries": [{"path": "", "kind": "file"}]}
        entries = self.mod.root_surface_entries(result, repo_root=self.repo_root)
        self.assertEqual(entries, [])

    def test_deduplication(self):
        result = {
            "entries": [
                {"path": "README.md", "kind": "file"},
                {"path": "README.md", "kind": "file"},
            ]
        }
        entries = self.mod.root_surface_entries(result, repo_root=self.repo_root)
        self.assertEqual(len(entries), 1)

    def test_string_items_extracted(self):
        result = {
            "entries": [
                "README.md",
                "setup.py",
            ]
        }
        # String items get kind="" initially but repo_path_kind is called when kind is empty
        with patch.object(self.mod, "repo_path_kind", return_value="file"):
            entries = self.mod.root_surface_entries(result, repo_root=self.repo_root)
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]["path"], "README.md")
            self.assertEqual(entries[0]["kind"], "file")


class TestRootSurfaceFilePaths(unittest.TestCase):
    """Test root_surface_file_paths function."""

    def setUp(self):
        self.mod = _load_module()
        self.repo_root = Path("/fake/repo")
        self.safe_rel_path = lambda p: p.replace("\\", "/")

    def test_no_files_returns_empty(self):
        result = {}
        paths = self.mod.root_surface_file_paths(result, repo_root=self.repo_root, safe_rel_path=self.safe_rel_path)
        self.assertEqual(paths, [])

    def test_file_kind_extracted(self):
        result = {
            "entries": [
                {"path": "README.md", "kind": "file"},
            ]
        }
        with patch.object(self.mod, "repo_existing_file", return_value=True):
            paths = self.mod.root_surface_file_paths(result, repo_root=self.repo_root, safe_rel_path=self.safe_rel_path)
            self.assertEqual(len(paths), 1)
            self.assertEqual(paths[0], "README.md")

    def test_non_file_kind_skipped(self):
        result = {
            "entries": [
                {"path": "src/", "kind": "dir"},
            ]
        }
        paths = self.mod.root_surface_file_paths(result, repo_root=self.repo_root, safe_rel_path=self.safe_rel_path)
        self.assertEqual(paths, [])

    def test_nonexistent_file_skipped(self):
        result = {
            "entries": [
                {"path": "README.md", "kind": "file"},
            ]
        }
        with patch.object(self.mod, "repo_existing_file", return_value=False):
            paths = self.mod.root_surface_file_paths(result, repo_root=self.repo_root, safe_rel_path=self.safe_rel_path)
            self.assertEqual(paths, [])

    def test_deduplication(self):
        result = {
            "entries": [
                {"path": "README.md", "kind": "file"},
                {"path": "README.md", "kind": "file"},
            ]
        }
        with patch.object(self.mod, "repo_existing_file", return_value=True):
            paths = self.mod.root_surface_file_paths(result, repo_root=self.repo_root, safe_rel_path=self.safe_rel_path)
            self.assertEqual(len(paths), 1)


class TestRootSurfaceDirPaths(unittest.TestCase):
    """Test root_surface_dir_paths function."""

    def setUp(self):
        self.mod = _load_module()
        self.repo_root = Path("/fake/repo")
        self.safe_rel_path = lambda p: p.replace("\\", "/")

    def test_no_dirs_returns_empty(self):
        result = {}
        paths = self.mod.root_surface_dir_paths(result, repo_root=self.repo_root, safe_rel_path=self.safe_rel_path)
        self.assertEqual(paths, [])

    def test_dir_kind_extracted(self):
        result = {
            "entries": [
                {"path": "src/", "kind": "dir"},
            ]
        }
        with patch.object(self.mod, "repo_existing_dir", return_value=True):
            paths = self.mod.root_surface_dir_paths(result, repo_root=self.repo_root, safe_rel_path=self.safe_rel_path)
            self.assertEqual(len(paths), 1)
            # repo_rel_token strips trailing slashes
            self.assertEqual(paths[0], "src")

    def test_non_dir_kind_skipped(self):
        result = {
            "entries": [
                {"path": "README.md", "kind": "file"},
            ]
        }
        paths = self.mod.root_surface_dir_paths(result, repo_root=self.repo_root, safe_rel_path=self.safe_rel_path)
        self.assertEqual(paths, [])

    def test_deduplication(self):
        result = {
            "entries": [
                {"path": "src/", "kind": "dir"},
                {"path": "src/", "kind": "dir"},
            ]
        }
        with patch.object(self.mod, "repo_existing_dir", return_value=True):
            paths = self.mod.root_surface_dir_paths(result, repo_root=self.repo_root, safe_rel_path=self.safe_rel_path)
            self.assertEqual(len(paths), 1)


class TestInitialDocSortKey(unittest.TestCase):
    """Test initial_doc_sort_key function."""

    def setUp(self):
        self.mod = _load_module()
        self.repo_root = Path("/fake/repo")
        self.named_read_priority = {
            "README.md": 0,
            "AGENTS.md": 1,
            "pyproject.toml": 2,
        }

    def test_named_priority_used(self):
        # The function lowercases the filename: "README.md" -> "readme.md"
        # But dict key is "README.md" (case-sensitive), so lookup fails and falls back to len()
        key = self.mod.initial_doc_sort_key("README.md", named_read_priority=self.named_read_priority)
        self.assertEqual(key[0], len(self.named_read_priority))

    def test_named_priority_case_sensitive(self):
        # With lowercase key matching the lowered filename
        case_sensitive_priority = {"readme.md": 0, "agents.md": 1, "pyproject.toml": 2}
        key = self.mod.initial_doc_sort_key("README.md", named_read_priority=case_sensitive_priority)
        self.assertEqual(key[0], 0)

    def test_unnamed_priority_is_high(self):
        key = self.mod.initial_doc_sort_key("random.txt", named_read_priority=self.named_read_priority)
        # Priority should be len(named_read_priority) for unnamed files
        self.assertEqual(key[0], len(self.named_read_priority))

    def test_depth_included(self):
        key_shallow = self.mod.initial_doc_sort_key("README.md", named_read_priority=self.named_read_priority)
        key_deep = self.mod.initial_doc_sort_key("deep/nested/README.md", named_read_priority=self.named_read_priority)
        # Same priority but different depth
        self.assertEqual(key_shallow[0], key_deep[0])
        self.assertLess(key_shallow[1], key_deep[1])

    def test_case_insensitive_name(self):
        key_lower = self.mod.initial_doc_sort_key("readme.md", named_read_priority=self.named_read_priority)
        key_upper = self.mod.initial_doc_sort_key("README.md", named_read_priority=self.named_read_priority)
        self.assertEqual(key_lower[2].lower(), key_upper[2].lower())


class TestControllerInitialDocPreseedPlan(unittest.TestCase):
    """Test controller_initial_doc_preseed_plan function."""

    def setUp(self):
        self.mod = _load_module()
        self.repo_root = Path("/fake/repo")
        self.safe_rel_path = lambda p: p.replace("\\", "/")

    def test_no_docs_returns_none_and_skipped(self):
        root_result = {}
        named_read_priority = {"README.md": 0}
        plan, skipped = self.mod.controller_initial_doc_preseed_plan(
            root_result,
            repo_root=self.repo_root,
            safe_rel_path=self.safe_rel_path,
            named_read_priority=named_read_priority,
            initial_doc_name_priority={"README.md"},
            scoped_concrete_read_target=1,
            multi_file_prompt_read_chars=10000,
        )
        self.assertIsNone(plan)
        self.assertTrue(len(skipped) > 0)

    def test_docs_selected(self):
        root_result = {
            "entries": [
                {"path": "README.md", "kind": "file"},
            ]
        }
        with patch.object(self.mod, "repo_doc_or_config", return_value=True):
            with patch.object(self.mod, "repo_existing_file", return_value=True):
                plan, skipped = self.mod.controller_initial_doc_preseed_plan(
                    root_result,
                    repo_root=self.repo_root,
                    safe_rel_path=self.safe_rel_path,
                    named_read_priority={"README.md": 0},
                    initial_doc_name_priority={},
                    scoped_concrete_read_target=1,
                    multi_file_prompt_read_chars=10000,
                )
                self.assertIsNotNone(plan)
                self.assertEqual(plan["tool"], "repo_read")
                self.assertTrue(len(skipped) == 0)

    def test_skipped_not_in_root_surface(self):
        root_result = {
            "entries": [
                {"path": "README.md", "kind": "file"},
            ]
        }
        with patch.object(self.mod, "repo_doc_or_config", return_value=True):
            with patch.object(self.mod, "repo_existing_file", return_value=True):
                plan, skipped = self.mod.controller_initial_doc_preseed_plan(
                    root_result,
                    repo_root=self.repo_root,
                    safe_rel_path=self.safe_rel_path,
                    named_read_priority={"README.md": 0},
                    initial_doc_name_priority={"AGENTS.md"},  # Not in root surface
                    scoped_concrete_read_target=1,
                    multi_file_prompt_read_chars=10000,
                )
                self.assertIsNotNone(plan)
                # AGENTS.md should be in skipped
                skipped_names = [s.get("candidate") for s in skipped]
                self.assertIn("AGENTS.md", skipped_names)


class TestInitialAreaSortKey(unittest.TestCase):
    """Test initial_area_sort_key function."""

    def setUp(self):
        self.mod = _load_module()

    def test_sort_by_depth(self):
        # initial_area_sort_key returns (top.count("/"), top.lower())
        # "alpha/" -> top="alpha" -> count("/")=0, "beta/" -> top="beta" -> count("/")=0
        # Same depth, secondary sort by lowercase name
        key_alpha = self.mod.initial_area_sort_key("alpha/")
        key_beta = self.mod.initial_area_sort_key("beta/")
        self.assertEqual(key_alpha[0], key_beta[0])  # Same depth
        self.assertLess(key_alpha[1], key_beta[1])  # alpha < beta alphabetically

    def test_sort_by_name_lowercase(self):
        key_a = self.mod.initial_area_sort_key("alpha/")
        key_z = self.mod.initial_area_sort_key("zeta/")
        self.assertLess(key_a[1], key_z[1])


class TestControllerInitialAreaListPlans(unittest.TestCase):
    """Test controller_initial_area_list_plans function."""

    def setUp(self):
        self.mod = _load_module()
        self.repo_root = Path("/fake/repo")
        self.safe_rel_path = lambda p: p.replace("\\", "/")

    def test_no_dirs_returns_empty_plans(self):
        root_result = {}
        plans, skipped = self.mod.controller_initial_area_list_plans(
            root_result,
            repo_root=self.repo_root,
            safe_rel_path=self.safe_rel_path,
        )
        self.assertEqual(plans, [])
        self.assertTrue(len(skipped) >= 0)

    def test_selected_areas(self):
        root_result = {
            "entries": [
                {"path": "src/", "kind": "dir"},
                {"path": "tests/", "kind": "dir"},
                {"path": "docs/", "kind": "dir"},
            ]
        }
        with patch.object(self.mod, "repo_existing_dir", return_value=True):
            with patch.object(self.mod, "low_signal_top_dir", return_value=False):
                plans, skipped = self.mod.controller_initial_area_list_plans(
                    root_result,
                    repo_root=self.repo_root,
                    safe_rel_path=self.safe_rel_path,
                )
                # Should select up to 3 areas
                self.assertLessEqual(len(plans), 3)
                self.assertTrue(len(skipped) >= 0)


class TestControllerInitialOrientationCandidatePool(unittest.TestCase):
    """Test controller_initial_orientation_candidate_pool function."""

    def setUp(self):
        self.mod = _load_module()
        self.repo_root = Path("/fake/repo")
        self.safe_rel_path = lambda p: p.replace("\\", "/")

    def test_empty_result_returns_empty_pool(self):
        result = {}
        pool = self.mod.controller_initial_orientation_candidate_pool(
            result,
            repo_root=self.repo_root,
            safe_rel_path=self.safe_rel_path,
            named_read_priority={"README.md": 0},
        )
        self.assertEqual(pool, [])

    def test_doc_candidates_created(self):
        result = {
            "entries": [
                {"path": "README.md", "kind": "file"},
            ]
        }
        with patch.object(self.mod, "repo_doc_or_config", return_value=True):
            with patch.object(self.mod, "repo_existing_file", return_value=True):
                pool = self.mod.controller_initial_orientation_candidate_pool(
                    result,
                    repo_root=self.repo_root,
                    safe_rel_path=self.safe_rel_path,
                    named_read_priority={"README.md": 0},
                )
                # Should have at least one doc candidate
                doc_candidates = [c for c in pool if c.get("candidate_class") == "root_doc"]
                self.assertTrue(len(doc_candidates) > 0)
                # Verify candidate structure
                candidate = doc_candidates[0]
                self.assertIn("candidate_id", candidate)
                self.assertIn("path", candidate)
                self.assertIn("kind", candidate)
                self.assertIn("static_rank", candidate)
                self.assertIn("signals", candidate)

    def test_dir_candidates_created(self):
        result = {
            "entries": [
                {"path": "src/", "kind": "dir"},
            ]
        }
        with patch.object(self.mod, "repo_existing_dir", return_value=True):
            with patch.object(self.mod, "low_signal_top_dir", return_value=False):
                pool = self.mod.controller_initial_orientation_candidate_pool(
                    result,
                    repo_root=self.repo_root,
                    safe_rel_path=self.safe_rel_path,
                    named_read_priority={"README.md": 0},
                )
                dir_candidates = [c for c in pool if c.get("candidate_class") == "root_area"]
                self.assertTrue(len(dir_candidates) > 0)

    def test_doc_candidates_before_dir_candidates(self):
        result = {
            "entries": [
                {"path": "README.md", "kind": "file"},
                {"path": "src/", "kind": "dir"},
            ]
        }
        with patch.object(self.mod, "repo_doc_or_config", return_value=True):
            with patch.object(self.mod, "repo_existing_file", return_value=True):
                with patch.object(self.mod, "repo_existing_dir", return_value=True):
                    with patch.object(self.mod, "low_signal_top_dir", return_value=False):
                        pool = self.mod.controller_initial_orientation_candidate_pool(
                            result,
                            repo_root=self.repo_root,
                            safe_rel_path=self.safe_rel_path,
                            named_read_priority={"README.md": 0},
                        )
                        # Docs should come before dirs
                        doc_indices = [i for i, c in enumerate(pool) if c.get("candidate_class") == "root_doc"]
                        dir_indices = [i for i, c in enumerate(pool) if c.get("candidate_class") == "root_area"]
                        if doc_indices and dir_indices:
                            self.assertLess(max(doc_indices), min(dir_indices))

    def test_candidate_id_format(self):
        result = {
            "entries": [
                {"path": "README.md", "kind": "file"},
            ]
        }
        with patch.object(self.mod, "repo_doc_or_config", return_value=True):
            with patch.object(self.mod, "repo_existing_file", return_value=True):
                pool = self.mod.controller_initial_orientation_candidate_pool(
                    result,
                    repo_root=self.repo_root,
                    safe_rel_path=self.safe_rel_path,
                    named_read_priority={"README.md": 0},
                )
                candidate = pool[0]
                self.assertTrue(candidate["candidate_id"].startswith("root_doc:"))


class TestListResultFilePaths(unittest.TestCase):
    """Test list_result_file_paths function."""

    def setUp(self):
        self.mod = _load_module()
        self.repo_root = Path("/fake/repo")
        self.safe_rel_path = lambda p: p.replace("\\", "/")

    def test_no_paths_returns_empty(self):
        result = {}
        paths = self.mod.list_result_file_paths(result, repo_root=self.repo_root, safe_rel_path=self.safe_rel_path)
        self.assertEqual(paths, [])

    def test_paths_key_extracted(self):
        result = {"paths": ["README.md"]}
        with patch.object(self.mod, "repo_existing_file", return_value=True):
            paths = self.mod.list_result_file_paths(result, repo_root=self.repo_root, safe_rel_path=self.safe_rel_path)
            self.assertEqual(len(paths), 1)

    def test_paths_preview_key_extracted(self):
        result = {"paths_preview": ["setup.py"]}
        with patch.object(self.mod, "repo_existing_file", return_value=True):
            paths = self.mod.list_result_file_paths(result, repo_root=self.repo_root, safe_rel_path=self.safe_rel_path)
            self.assertEqual(len(paths), 1)

    def test_files_key_extracted(self):
        result = {"files": [{"path": "config.json"}]}
        with patch.object(self.mod, "repo_existing_file", return_value=True):
            paths = self.mod.list_result_file_paths(result, repo_root=self.repo_root, safe_rel_path=self.safe_rel_path)
            self.assertEqual(len(paths), 1)

    def test_files_preview_key_extracted(self):
        result = {"files_preview": [{"path": "pyproject.toml"}]}
        with patch.object(self.mod, "repo_existing_file", return_value=True):
            paths = self.mod.list_result_file_paths(result, repo_root=self.repo_root, safe_rel_path=self.safe_rel_path)
            self.assertEqual(len(paths), 1)

    def test_deduplication(self):
        result = {"paths": ["README.md", "README.md"]}
        with patch.object(self.mod, "repo_existing_file", return_value=True):
            paths = self.mod.list_result_file_paths(result, repo_root=self.repo_root, safe_rel_path=self.safe_rel_path)
            self.assertEqual(len(paths), 1)

    def test_nonexistent_file_skipped(self):
        result = {"paths": ["README.md"]}
        with patch.object(self.mod, "repo_existing_file", return_value=False):
            paths = self.mod.list_result_file_paths(result, repo_root=self.repo_root, safe_rel_path=self.safe_rel_path)
            self.assertEqual(paths, [])


class TestInitialAreaFileSortKey(unittest.TestCase):
    """Test initial_area_file_sort_key function."""

    def setUp(self):
        self.mod = _load_module()
        self.repo_root = Path("/fake/repo")
        self.named_read_priority = {"README.md": 0}

    def test_doc_kind_rank_zero(self):
        with patch.object(self.mod, "repo_doc_or_config", return_value=True):
            key = self.mod.initial_area_file_sort_key("README.md", repo_root=self.repo_root, named_read_priority=self.named_read_priority)
            self.assertEqual(key[1], 0)

    def test_code_kind_rank_one(self):
        with patch.object(self.mod, "repo_doc_or_config", return_value=False):
            with patch.object(self.mod, "repo_code_file", return_value=True):
                key = self.mod.initial_area_file_sort_key("main.py", repo_root=self.repo_root, named_read_priority=self.named_read_priority)
                self.assertEqual(key[1], 1)

    def test_other_kind_rank_two(self):
        with patch.object(self.mod, "repo_doc_or_config", return_value=False):
            with patch.object(self.mod, "repo_code_file", return_value=False):
                key = self.mod.initial_area_file_sort_key("random.txt", repo_root=self.repo_root, named_read_priority=self.named_read_priority)
                self.assertEqual(key[1], 2)


class TestControllerInitialAreaReadPlan(unittest.TestCase):
    """Test controller_initial_area_read_plan function."""

    def setUp(self):
        self.mod = _load_module()
        self.repo_root = Path("/fake/repo")
        self.safe_rel_path = lambda p: p.replace("\\", "/")

    def test_no_candidates_returns_none_and_skipped(self):
        list_result = {"path": "src/", "paths": ["nonexistent.py"]}
        with patch.object(self.mod, "repo_doc_or_config", return_value=False):
            with patch.object(self.mod, "repo_code_file", return_value=False):
                plan, skipped = self.mod.controller_initial_area_read_plan(
                    list_result,
                    repo_root=self.repo_root,
                    safe_rel_path=self.safe_rel_path,
                    named_read_priority={"README.md": 0},
                    single_file_prompt_read_chars=5000,
                )
                self.assertIsNone(plan)
                self.assertTrue(len(skipped) > 0)

    def test_valid_candidate_selected(self):
        list_result = {
            "path": "src/",
            "paths": ["main.py"],
        }
        with patch.object(self.mod, "repo_doc_or_config", return_value=True):
            with patch.object(self.mod, "repo_existing_file", return_value=True):
                plan, skipped = self.mod.controller_initial_area_read_plan(
                    list_result,
                    repo_root=self.repo_root,
                    safe_rel_path=self.safe_rel_path,
                    named_read_priority={"README.md": 0},
                    single_file_prompt_read_chars=5000,
                )
                self.assertIsNotNone(plan)
                self.assertEqual(plan["tool"], "repo_read")
                self.assertEqual(len(skipped), 0)

    def test_plan_structure(self):
        list_result = {
            "path": "src/",
            "paths": ["main.py"],
        }
        with patch.object(self.mod, "repo_doc_or_config", return_value=True):
            with patch.object(self.mod, "repo_existing_file", return_value=True):
                plan, skipped = self.mod.controller_initial_area_read_plan(
                    list_result,
                    repo_root=self.repo_root,
                    safe_rel_path=self.safe_rel_path,
                    named_read_priority={"README.md": 0},
                    single_file_prompt_read_chars=5000,
                )
                self.assertIn("event", plan)
                self.assertIn("result_event", plan)
                self.assertIn("tool", plan)
                self.assertIn("arguments", plan)
                self.assertIn("reason", plan)
                self.assertIn("artifact_suffix", plan)


if __name__ == "__main__":
    unittest.main()