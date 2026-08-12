#!/usr/bin/env python3
"""Unit tests for app-agnostic NPU pipeline helpers.

These tests intentionally avoid Blender, NPU, GPU, Ollama, FFmpeg and filesystem
writes outside a temporary directory.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Tools.npu.pipeline import (  # noqa: E402
    COMMON_VALIDATION_REPORT_KEYS,
    DEFAULT_ALLOWED_ARTIFACT_PREFIXES,
    DualPipelinePaths,
    MigrationReadinessCheck,
    NpuPipelineConfig,
    PlannedArtifactWrite,
    ProviderRequest,
    RuntimeOutputManifestEntry,
    build_context_bundle,
    build_creative_scene_prompt_payload,
    build_default_stage_plan,
    build_helper_boundary_report,
    build_implementation_retry_payload,
    build_merge_prompt_payload,
    build_migration_readiness_report,
    build_runtime_output_manifest,
    build_validation_report,
    compact_segments_for_prompt,
    compare_json_readers,
    compare_optional_json_readers,
    compare_text_readers,
    context_bundle_metrics,
    default_runtime_wiring_readiness,
    dual_ai_legacy_runtime_output_paths,
    helper_boundary_passed,
    is_allowed_legacy_runtime_output_path,
    is_allowed_generated_artifact_path,
    normalize_provider_preflight_report,
    planned_provider_result,
    read_json,
    read_json_object,
    read_optional_json,
    read_optional_json_object,
    read_text,
    runtime_output_manifest_passed,
    sample_implementation_draft_fixture,
    sample_music_context_fixture,
    sample_provider_request_fixture,
    stage_plan_report,
    summarize_music_context,
    validate_generated_artifact_paths,
    validate_implementation_draft_contract,
    validate_json_object,
    validate_legacy_runtime_output_paths,
    validate_planned_artifact_writes,
    validate_provider_request,
    validation_report_has_common_keys,
    write_json,
    write_json_object,
    write_planned_artifact,
)


class NpuPipelineHelperTests(unittest.TestCase):
    def sample_music_context(self) -> dict[str, object]:
        return sample_music_context_fixture()

    def test_config_paths_are_data_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = DualPipelinePaths(repo_root=root, track_stem="Track A")
            config = NpuPipelineConfig.from_repo_root(root, track_stem="Track A")
            self.assertEqual(paths.output_dir, root / "output")
            self.assertEqual(paths.tools_dir, root / "Tools" / "npu")
            self.assertEqual(config.paths.track_stem, "Track A")
            self.assertEqual(config.allowed_artifact_prefixes, DEFAULT_ALLOWED_ARTIFACT_PREFIXES)

    def test_fixtures_match_contracts(self) -> None:
        music_context = sample_music_context_fixture()
        draft = sample_implementation_draft_fixture()
        provider_payload = sample_provider_request_fixture()
        self.assertEqual(len(music_context["segments"]), 2)
        self.assertTrue(validate_implementation_draft_contract(draft)["ok"])
        provider_request = ProviderRequest(**provider_payload)
        self.assertTrue(validate_provider_request(provider_request)["ok"])
        self.assertFalse(provider_request.metadata["executed"])

    def test_io_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            json_path = root / "nested" / "data.json"
            write_json_object(json_path, {"ok": True})
            self.assertEqual(read_json_object(json_path), {"ok": True})
            self.assertEqual(read_json(json_path), {"ok": True})
            self.assertIn('"ok"', read_text(json_path))
            self.assertEqual(read_optional_json_object(root / "missing.json"), {})
            self.assertEqual(read_optional_json(root / "missing.json"), {})
            alias_path = root / "nested" / "alias.json"
            write_json(alias_path, {"alias": True})
            self.assertEqual(json.loads(alias_path.read_text(encoding="utf-8")), {"alias": True})
            bad_path = root / "bad.json"
            bad_path.write_text("not json", encoding="utf-8")
            self.assertEqual(read_optional_json_object(bad_path), {})

    def test_legacy_compat_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            json_path = root / "data.json"
            write_json_object(json_path, {"b": 2, "a": 1})
            text_path = root / "text.txt"
            text_path.write_text("hello", encoding="utf-8")
            self.assertTrue(compare_json_readers(json_path, read_json_object, read_json)["ok"])
            self.assertTrue(compare_optional_json_readers(json_path, read_optional_json_object, read_optional_json)["ok"])
            self.assertTrue(compare_text_readers(text_path, read_text, read_text)["ok"])

    def test_artifact_path_policy(self) -> None:
        self.assertTrue(is_allowed_generated_artifact_path("indexAI/scene_scripts/a.py"))
        self.assertTrue(is_allowed_generated_artifact_path("indexAI/patch_library/a.json"))
        self.assertFalse(is_allowed_generated_artifact_path("output/a.json"))
        self.assertFalse(is_allowed_generated_artifact_path("../outside.json"))
        report = validate_generated_artifact_paths(
            ["indexAI/scene_scripts/a.py", "output/a.json"],
            allowed_prefixes=DEFAULT_ALLOWED_ARTIFACT_PREFIXES,
        )
        self.assertFalse(report["ok"])
        self.assertEqual(report["invalid_paths"], ["output/a.json"])

    def test_legacy_runtime_output_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowed = dual_ai_legacy_runtime_output_paths("Track A")
            self.assertIn("Tools/npu/npu_preflight_report.json", allowed)
            self.assertTrue(
                is_allowed_legacy_runtime_output_path(
                    root / "Tools" / "npu" / "npu_preflight_report.json",
                    repo_root=root,
                    track_stem="Track A",
                )
            )
            report = validate_legacy_runtime_output_paths(
                [
                    root / "output" / "Track A_dual_ai_scene_plan.json",
                    "Tools/npu/not_allowed.md",
                ],
                repo_root=root,
                track_stem="Track A",
            )
            self.assertFalse(report["ok"])
            self.assertEqual(report["invalid_paths"], ["Tools/npu/not_allowed.md"])

    def test_artifact_writer_validates_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            planned = PlannedArtifactWrite(
                repo_relative_path="indexAI/scene_scripts/generated.py",
                kind="script",
                content="print('ok')\n",
            )
            report = validate_planned_artifact_writes(
                [planned],
                allowed_prefixes=DEFAULT_ALLOWED_ARTIFACT_PREFIXES,
            )
            self.assertTrue(report["ok"])
            written = write_planned_artifact(root, planned, allowed_prefixes=DEFAULT_ALLOWED_ARTIFACT_PREFIXES)
            self.assertEqual(written.read_text(encoding="utf-8"), "print('ok')\n")

            with self.assertRaises(ValueError):
                write_planned_artifact(
                    root,
                    PlannedArtifactWrite("output/blocked.json", "json", {"blocked": True}),
                    allowed_prefixes=DEFAULT_ALLOWED_ARTIFACT_PREFIXES,
                )

    def test_context_and_prompt_payload_helpers(self) -> None:
        music_context = self.sample_music_context()
        compact = compact_segments_for_prompt(music_context)
        self.assertEqual(len(compact), 2)
        self.assertEqual(len(compact[0]["top_events"]), 6)
        summary = summarize_music_context(music_context)
        self.assertEqual(summary["segment_count"], 2)
        bundle = build_context_bundle(
            music_context=music_context,
            project_index="p" * 500,
            npu_notes="n" * 300,
            max_project_index_chars=50,
            max_npu_notes_chars=40,
        )
        metrics = context_bundle_metrics(bundle)
        self.assertEqual(metrics["slice_count"], 2)
        self.assertEqual(metrics["clipped_chars"], 90)
        creative = build_creative_scene_prompt_payload(
            music_context,
            npu_notes="npu notes",
            project_index="project index",
        )
        merge = build_merge_prompt_payload(
            music_context,
            npu_notes="npu notes",
            project_index="project index",
            creative={"creative": True},
            technical={"technical": True},
        )
        retry = build_implementation_retry_payload(
            {"plan": True},
            preferred_existing_files=["Scripting/v61b/materials.py"],
            allowed_new_prefixes=DEFAULT_ALLOWED_ARTIFACT_PREFIXES,
            validation={"issues": ["x"]},
        )
        self.assertEqual(len(creative["segments"]), 2)
        self.assertEqual(merge["ollama_technical"], {"technical": True})
        self.assertTrue(retry["previous_response_was_invalid"])

    def test_validator_contracts_are_permissive(self) -> None:
        object_report = validate_json_object({"future": True}, label="future")
        self.assertTrue(object_report["ok"])
        draft_report = validate_implementation_draft_contract(sample_implementation_draft_fixture())
        self.assertTrue(draft_report["ok"])
        missing_report = validate_implementation_draft_contract({})
        self.assertFalse(missing_report["ok"])
        self.assertTrue(missing_report["issues"])

    def test_common_validation_report_helpers(self) -> None:
        report = build_validation_report(
            kind="npu_test_report",
            repo_root=REPO_ROOT,
            passed=True,
            checks={"sample": True},
        )
        self.assertEqual(tuple(COMMON_VALIDATION_REPORT_KEYS), tuple(COMMON_VALIDATION_REPORT_KEYS))
        self.assertTrue(validation_report_has_common_keys(report))
        self.assertTrue(report["passed"])
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["warnings"], [])
        self.assertEqual(report["checks"], {"sample": True})
        self.assertFalse(validation_report_has_common_keys({"passed": True}))

    def test_runtime_output_manifest_helpers_are_observability_only(self) -> None:
        allowed_entry = RuntimeOutputManifestEntry(
            path="output/Track_dual_ai_scene_plan.json",
            kind="scene_plan",
            policy_source="legacy_runtime_output_policy",
            allowed=True,
            legacy=True,
            generated=False,
            provider_execution_performed=False,
        )
        blocked_entry = RuntimeOutputManifestEntry(
            path="Tools/npu/unknown.md",
            kind="notes",
            policy_source="legacy_runtime_output_policy",
            allowed=False,
            reason="not in exact legacy output allowlist",
        )
        allowed_manifest = build_runtime_output_manifest(
            repo_root=REPO_ROOT,
            entries=[allowed_entry],
            provider_execution_performed=False,
        )
        blocked_manifest = build_runtime_output_manifest(
            repo_root=REPO_ROOT,
            entries=[allowed_entry, blocked_entry],
            provider_execution_performed=False,
        )
        self.assertTrue(runtime_output_manifest_passed(allowed_manifest))
        self.assertFalse(runtime_output_manifest_passed(blocked_manifest))
        self.assertEqual(blocked_manifest["blocked_count"], 1)
        self.assertFalse(blocked_manifest["provider_execution_performed"])
        self.assertIn("blocked runtime output", blocked_manifest["errors"][0])

    def test_provider_descriptors_are_planned_only(self) -> None:
        request = ProviderRequest(provider="ollama", model="model", prompt="hello", max_tokens=32)
        validation = validate_provider_request(request)
        result = planned_provider_result(request)
        self.assertTrue(validation["ok"])
        self.assertTrue(result.ok)
        self.assertFalse(result.metadata["executed"])
        self.assertEqual(result.text, "")

        invalid = planned_provider_result(ProviderRequest(provider="", model="", prompt="", max_tokens=0))
        self.assertFalse(invalid.ok)
        self.assertIn("provider is required", invalid.error or "")

    def test_provider_preflight_normalization_is_non_executing(self) -> None:
        report = normalize_provider_preflight_report(
            {
                "schema_version": 2,
                "ready": True,
                "mode": "npu_ready",
                "python_starts": True,
                "openvino_import": True,
                "openvino_genai_import": True,
                "openvino_available_devices": ["CPU", "NPU"],
                "npu_device_available": True,
                "recommended_workers": 4,
                "errors": [],
                "warnings": ["sample"],
            },
            provider="openvino_npu",
            model="model",
            executable="python.exe",
            model_dir="models/model",
        )
        self.assertEqual(report["kind"], "provider_preflight")
        self.assertTrue(report["ready"])
        self.assertFalse(report["provider_execution_performed"])
        self.assertEqual(report["runtime"]["recommended_workers"], 4)

    def test_runner_stage_plan_and_boundary_report(self) -> None:
        stages = build_default_stage_plan(include_provider_stages=False)
        report = stage_plan_report(stages)
        self.assertEqual(report["stage_count"], 5)
        self.assertEqual(report["enabled_stage_count"], 4)
        boundary = build_helper_boundary_report(
            package_name="Tools.npu.pipeline",
            modules=["config", "io_utils"],
            checks={"syntax": True, "imports": True},
        )
        self.assertTrue(helper_boundary_passed(boundary))
        failed = build_helper_boundary_report(
            package_name="Tools.npu.pipeline",
            modules=["config"],
            checks={"syntax": False},
        )
        self.assertFalse(helper_boundary_passed(failed))

    def test_migration_readiness_blocks_runtime_by_default(self) -> None:
        readiness = default_runtime_wiring_readiness(
            local_validation_passed=True,
            indexes_regenerated=True,
        )
        self.assertFalse(readiness["allowed_to_modify_runtime"])
        self.assertFalse(readiness["ready"])
        report = build_migration_readiness_report(
            target_file="Tools/npu/run_dual_ai_pipeline.py",
            checks=[MigrationReadinessCheck("local_validation_passed", True, "green")],
            allowed_to_modify_runtime=True,
        )
        self.assertTrue(report["ready"])
        blocked = build_migration_readiness_report(
            target_file="Tools/npu/run_dual_ai_pipeline.py",
            checks=[MigrationReadinessCheck("local_validation_passed", False, "red")],
            allowed_to_modify_runtime=True,
        )
        self.assertFalse(blocked["ready"])
        self.assertEqual(blocked["failed_count"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
