# Tools/validation

This folder contains lightweight repository validation helpers.

The tools are intentionally non-invasive: they inspect files and write optional reports. They must not rewrite source code, generated scripts, generated JSON artifacts, Blender packages, render outputs or FFmpeg outputs.

## Validation model

Validation is split into deterministic checks:

```text
source/code syntax checks
repository/package structure checks
JSON artifact checks
documentation link checks
execution-plan folder/status checks
AI pipeline smoke checks
NPU pipeline helper smoke and unit tests
AI dry-run matrix case-definition checks
AI dry-run matrix output consistency checks
AI dry-run matrix report contract checks
AI dry-run matrix evidence bundle checks
AI pipeline schema-v6 report contract checks
GitHub evidence bundle contract checks
selective execution plan contract checks
selected semantic chunks contract checks
repository change proposal contract checks
full-context golden proposal contract checks
proposal patch-spec draft contract checks
reviewed patch-spec dry-run contract checks
AI context pack contract checks
validation report contract checks
agent memory policy checks
Blender compatibility smokes
generated-file policy checks
generated Python policy checks
generated artifact path policy checks
```

Validators should remain cheap, reviewable and safe to run locally.

## Common validation report contract

Validation reports should converge toward these root fields:

```text
schema_version
kind
repo_root
passed
errors
warnings, when applicable
```

Rules:

- `schema_version` should be an integer.
- `kind` should identify the validator/report family.
- `repo_root` should be a string.
- `passed` should be a boolean.
- `errors` should be a list.
- `warnings` should be a list when present.
- Adding these fields must be additive and should not remove validator-specific fields.

Meta-validator:

```powershell
python .\Tools\validation\check_validation_report_contract.py --repo-root . --output .\output\validation\validation_report_contract.json
```

Optional stricter mode after more reports are aligned:

```powershell
python .\Tools\validation\check_validation_report_contract.py --repo-root . --require-recommended --output .\output\validation\validation_report_contract.json
```

## Architecture boundary

Generated-file validation is not Blender-only and not WAV/audio-only.

Keep these validation layers separate:

```text
input-domain validators
output-application validators
generated Python script policy adapters
artifact/report contract validators
```

## Available checks

Core repository checks:

```powershell
python .\Tools\validation\check_python_syntax.py --repo-root . --output .\output\validation\python_syntax.json
python .\Tools\validation\check_package_structure.py --repo-root . --output .\output\validation\package_structure.json
python .\Tools\validation\check_json_artifacts.py --repo-root . --output .\output\validation\json_artifacts.json
python .\Tools\validation\check_docs_links.py --repo-root . --output .\output\validation\docs_links.json
python .\Tools\validation\check_execution_plan_status.py --repo-root . --output .\output\validation\execution_plan_status.json
```

AI pipeline, NPU helper, report-contract and memory checks:

```powershell
python .\Tools\validation\check_ai_pipeline_modules.py --repo-root . --output .\output\validation\ai_pipeline_modules.json
python .\Tools\validation\check_npu_pipeline_modules.py --repo-root . --output .\output\validation\npu_pipeline_modules.json
python .\Tools\validation\check_npu_pipeline_helper_tests.py --repo-root . --output .\output\validation\npu_pipeline_helper_tests.json
python .\Tools\validation\check_ai_model_json.py --repo-root . --output .\output\validation\ai_model_json.json
python .\Tools\validation\check_ai_dry_run_matrix_cases.py --repo-root . --output .\output\validation\ai_dry_run_matrix_cases.json
python .\Tools\validation\check_ai_pipeline_report_contract.py --repo-root . --report .\output\ai_pipeline\dry_run_matrix\base\ai_pipeline_dry_run_report.json --require-dry-run --output .\output\validation\ai_pipeline_report_contract.json
python .\Tools\validation\check_ai_dry_run_matrix_contract.py --repo-root . --output .\output\validation\ai_dry_run_matrix_contract.json
python .\Tools\validation\check_ai_dry_run_matrix_outputs.py --repo-root . --output .\output\validation\ai_dry_run_matrix_outputs.json
python .\Tools\validation\check_dry_run_matrix_evidence_bundle.py --repo-root . --evidence .\docs\LOCAL_VALIDATION_EVIDENCE\ai_pipeline_dry_run_matrix_evidence.json --output .\output\validation\dry_run_matrix_evidence_bundle.json
python .\Tools\validation\check_github_evidence_bundle.py --repo-root . --output .\output\validation\github_evidence_bundle.json
python .\Tools\validation\check_selective_execution_plan.py --repo-root . --plan .\output\ai_pipeline\selective_execution_plan.json --output .\output\validation\selective_execution_plan.json
python .\Tools\validation\check_selected_semantic_chunks.py --repo-root . --bundle .\output\ai_context_packs\full_context_golden_selected_chunks.json --output .\output\validation\full_context_golden_selected_chunks_contract.json --evidence-output .\docs\LOCAL_VALIDATION_EVIDENCE\full_context_golden_selected_chunks_evidence.json --markdown-output .\docs\LOCAL_VALIDATION_EVIDENCE\full_context_golden_selected_chunks_evidence.md
python .\Tools\validation\check_repository_change_proposals.py --repo-root . --proposal .\output\ai_pipeline\repository_change_proposals.json --output .\output\validation\repository_change_proposals_contract.json
python .\Tools\validation\check_full_context_golden_proposals.py --repo-root . --proposal .\output\ai_pipeline\full_context_golden_proposals.json --output .\output\validation\full_context_golden_proposals_contract.json --min-proposals 6
python .\Tools\validation\check_patch_spec_drafts.py --repo-root . --manifest .\output\patch_specs\proposal_patch_specs_manifest.json --output .\output\validation\patch_spec_drafts.json
python .\Tools\validation\check_reviewed_patch_specs.py --repo-root . --manifest .\output\patch_specs\reviewed_patch_spec_manifest.json --output .\output\validation\reviewed_patch_specs.json
python .\Tools\validation\check_ai_context_pack_contract.py --repo-root . --pack .\output\ai_context_packs\project_self_improvement.json --evidence .\docs\LOCAL_VALIDATION_EVIDENCE\project_self_improvement_context_pack_evidence.json --output .\output\validation\ai_context_pack_contract.json
python .\Tools\validation\check_validation_report_contract.py --repo-root . --output .\output\validation\validation_report_contract.json
python .\Tools\validation\check_refactor_status_consistency.py --repo-root . --output .\output\validation\refactor_status_consistency.json
python .\Tools\validation\check_agent_memory_policy.py --repo-root . --output .\output\validation\agent_memory_policy.json
```

Blender and generated-file checks:

```powershell
python .\Tools\validation\check_blender_shared_compat_smoke.py --repo-root . --output .\output\validation\blender_shared_compat_smoke.json
python .\Tools\validation\check_generated_python_policy.py --repo-root . --output .\output\validation\generated_python_policy.json
python .\Tools\validation\check_generated_artifact_path_policy.py --repo-root . --output .\output\validation\generated_artifact_path_policy.json
python .\Tools\validation\check_generated_blender_script_policy.py --repo-root . --output .\output\validation\generated_blender_script_policy.json
```

## AI workload report quality gate

The AI workload report quality gate validates already-generated AI workload
reports before packet/proposal builders use them as advisory context.

Canonical contract:

```text
docs/AI_WORKLOAD_REPORT_QUALITY_GATE.md
```

Validator:

```powershell
python .\Toolsalidation\check_ai_workload_report_quality.py --repo-root . --output .\outputalidationi_workload_report_quality.json
```

Core report kind and policy:

```text
ai_workload_report_quality
usable_text_lanes_only_for_advisory_context
```

The validator is report-only and must keep:

```text
provider_execution_performed=false
source_writes_performed=false
```

NPU review metadata can be emitted without provider loading:

```powershell
python .\Tools
pu
un_npu_review.py --metadata-only --metadata-out .\outputalidation
pu_review_metadata.json
```

The `npu_review_metadata` sidecar records advisory role and quality-gate status.
Metadata-only mode must keep provider execution disabled.

## Tool map

| Tool | Role | Heavy workloads |
|---|---|---|
| `check_python_syntax.py` | Compiles Python files without importing project modules. | No |
| `check_package_structure.py` | Reports package-level structure and warnings under `Scripting/`. | No |
| `check_json_artifacts.py` | Checks JSON parseability; accepts UTF-8 with or without BOM and skips very large files by default. | No |
| `check_docs_links.py` | Validates repository-local Markdown links and ignores external URLs. | No |
| `check_execution_plan_status.py` | Ensures terminal execution plans are not left under `docs/EXECUTION_PLANS/active/`. | No |
| `check_ai_pipeline_modules.py` | Imports modular AI pipeline code and validates representative planning/report helpers. | No |
| `check_npu_pipeline_modules.py` | Imports app-agnostic NPU pipeline helpers and validates representative contract, provider-planning and boundary helpers. | No |
| `check_npu_pipeline_helper_tests.py` | Runs deterministic `unittest` coverage for app-agnostic NPU helper modules and emits a JSON validation report. | No |
| `test_npu_pipeline_helpers.py` | Unit test module used by `check_npu_pipeline_helper_tests.py`. | No |
| `check_ai_model_json.py` | Validates deterministic parsing of JSON-like model output and legacy wrapper behavior. | No |
| `check_ai_dry_run_matrix_cases.py` | Validates dry-run matrix case definitions without executing the matrix. | No |
| `check_ai_dry_run_matrix_outputs.py` | Validates generated dry-run matrix outputs against per-case reports. | No |
| `check_ai_dry_run_matrix_contract.py` | Validates the machine-readable dry-run matrix report contract. | No |
| `check_dry_run_matrix_evidence_bundle.py` | Validates compact Git-trackable dry-run matrix evidence bundles. | No |
| `check_ai_pipeline_report_contract.py` | Validates one schema-v6 AI pipeline report, including dry-run-only semantics when requested. | No |
| `check_github_evidence_bundle.py` | Validates Git-trackable AI/provider evidence bundle shape and decision fields without reading ignored `output/` contents. | No |
| `check_selective_execution_plan.py` | Validates report-only selective execution plan recommendations, local-only command sets and patch-spec candidate boundaries. | No |
| `check_selected_semantic_chunks.py` | Validates selected semantic chunk bundles and can emit compact selected-chunks evidence. | No |
| `check_repository_change_proposals.py` | Validates manual-review repository proposal reports and their code/Markdown/JSON suggestion descriptors. | No |
| `check_full_context_golden_proposals.py` | Validates semantic coverage of full-context golden proposal families beyond the generic repository proposal schema. | No |
| `check_patch_spec_drafts.py` | Validates proposal-derived draft patch specs under `output/patch_specs/` and rejects queued or concrete replacements. | No |
| `check_reviewed_patch_specs.py` | Validates reviewed patch specs and reruns dry-run without writing source files. | No |
| `check_ai_context_pack_contract.py` | Validates AI context packs and compact context-pack evidence without executing providers. | No |
| `check_validation_report_contract.py` | Validates generated reports in `output/validation/` for common root fields. | No |
| `check_refactor_status_consistency.py` | Checks that AI pipeline status markers and docs agree. | No |
| `check_agent_memory_policy.py` | Checks generic memory retention and promotion guardrails. | No |
| `check_blender_shared_compat_smoke.py` | Imports shared Blender compatibility helpers; performs no render. | No render |
| `check_generated_python_policy.py` | Validates generic generated Python syntax and hazard policy. | No |
| `check_generated_artifact_path_policy.py` | Validates generated artifact destination paths. | No |
| `check_generated_blender_script_policy.py` | Validates generated Blender Python scripts before execution. | No |

## Selective execution plan validation

The selective planner reads compact context/evidence artifacts and recommends the next validators plus candidate patch specs. It remains report-only.

Build and validate:

```powershell
python .\Tools\ai\build_selective_execution_plan.py --repo-root . --output .\output\ai_pipeline\selective_execution_plan.json --markdown-output .\output\ai_pipeline\selective_execution_plan.md
python .\Tools\validation\check_selective_execution_plan.py --repo-root . --plan .\output\ai_pipeline\selective_execution_plan.json --output .\output\validation\selective_execution_plan.json
```

The validator checks:

```text
kind == selective_execution_plan
apply_mode == report_only
provider_execution_performed == false
patch_application_performed == false
recommended validators are command-bearing
recommended patch specs remain manual_review_only
local-only GPU/NPU evidence commands are present
```

This validator does not execute providers, run validators from the plan, apply patches, run Blender or write source targets.

## Selected semantic chunks validation

Selected semantic chunks are bounded focused-context bundles generated from the semantic chunk index. They are safe context inputs, not source patches.

Validate a selected chunk bundle and optionally emit compact evidence:

```powershell
python .\Tools\validation\check_selected_semantic_chunks.py --repo-root . --bundle .\output\ai_context_packs\full_context_golden_selected_chunks.json --output .\output\validation\full_context_golden_selected_chunks_contract.json --evidence-output .\docs\LOCAL_VALIDATION_EVIDENCE\full_context_golden_selected_chunks_evidence.json --markdown-output .\docs\LOCAL_VALIDATION_EVIDENCE\full_context_golden_selected_chunks_evidence.md --max-total-chars 32000
```

The validator checks:

```text
kind == semantic_code_chunk_selection
source_writes_performed == false
provider_execution_performed == false
selected_count > 0
selected_count <= max_chunks
total_selected_chars stays within budget
chunk ids are unique
paths and line ranges are concrete
```

## Full-context golden proposal validation

The generic proposal validator checks schema shape. The full-context golden proposal validator adds semantic coverage requirements for the current golden path.

Run after generating deterministic full-context proposals:

```powershell
python .\Tools\ai\build_full_context_golden_proposals.py --repo-root . --source-report .\output\local_ai_runs\<run>\pipeline\full_context_golden_local_ai_context_proposals.json --output .\output\ai_pipeline\full_context_golden_proposals.json --markdown-output .\output\ai_pipeline\full_context_golden_proposals.md
python .\Tools\validation\check_repository_change_proposals.py --repo-root . --proposal .\output\ai_pipeline\full_context_golden_proposals.json --output .\output\validation\full_context_golden_repository_proposals_contract.json
python .\Tools\validation\check_full_context_golden_proposals.py --repo-root . --proposal .\output\ai_pipeline\full_context_golden_proposals.json --output .\output\validation\full_context_golden_proposals_contract.json --min-proposals 6
```

Required proposal families:

```text
P1 adapter manifest validator
P2 reusable enrichment-plan helper
P3 full-context golden path docs contract
P4 optional wrapper preset flag
P5 selected-chunks evidence standard validation block
P6 NPU knowledge-broker / context-oracle prototype
```

## Execution plan status validation

Completed plans must live under:

```text
docs/EXECUTION_PLANS/completed/
```

Active plans must not have top-level status `completed`, `abandoned` or `wont_fix`.

Run:

```powershell
python .\Tools\validation\check_execution_plan_status.py --repo-root . --output .\output\validation\execution_plan_status.json
```

This check exists because completed plans left under `active/` confuse future AI task selection.

## GitHub evidence bundle validation

Compact evidence bundles under `docs/LOCAL_VALIDATION_EVIDENCE/` let GitHub-only agents review local AI/provider validation without needing ignored `output/` trees.

Run:

```powershell
python .\Tools\validation\check_github_evidence_bundle.py --repo-root . --output .\output\validation\github_evidence_bundle.json
```

The validator checks:

```text
kind == github_validation_evidence_bundle
schema_version == 1
decision fields for Ollama/GPU primary advisory, NPU exclusion and provider execution
per-report summary fields: path, exists, json_ok, kind, passed, summary
```

Missing provider-specific optional fields are warnings, not blocking errors, so older evidence bundles remain readable while newer bundles can add richer diagnostic decisions such as `npu_decode_smoke_passed`.

Other compact evidence kinds may also live under `docs/LOCAL_VALIDATION_EVIDENCE/`; this validator only checks `kind == github_validation_evidence_bundle` unless explicit `--bundle` paths are supplied.

## Repository change proposal validation

Repository proposal reports are generated suggestion artifacts. They may describe future code, Markdown, JSON, PowerShell or workflow changes, but they must remain manual-review-only.

Run after generating proposals:

```powershell
python .\Tools\validation\check_repository_change_proposals.py --repo-root . --proposal .\output\ai_pipeline\repository_change_proposals.json --output .\output\validation\repository_change_proposals_contract.json
```

The validator checks:

```text
kind == repository_change_proposals
apply_mode == manual_review_only
proposal patch sketches, validation commands and stop conditions are present
suggestion_outputs describe target file kind and write policy
forbidden runtime/generated-index/full-analysis targets are not proposed
```

This validator does not execute providers, apply patches, run Blender or write suggestion targets.

## Proposal patch-spec draft validation

Proposal-derived patch specs turn validated repository proposals into reviewable patch-spec shells. They are written under ignored `output/patch_specs/`, contain target-file operations, and intentionally contain no replacements.

Generate drafts from a proposal report:

```powershell
python .\Tools\ai\build_patch_specs_from_proposals.py --repo-root . --proposal .\output\ai_pipeline\repository_change_proposals.json --output-dir output\patch_specs --basename proposal_patch_specs
```

Validate the draft manifest:

```powershell
python .\Tools\validation\check_patch_spec_drafts.py --repo-root . --manifest .\output\patch_specs\proposal_patch_specs_manifest.json --output .\output\validation\patch_spec_drafts.json
```

The validator checks:

```text
kind == proposal_patch_spec_manifest / proposal_patch_spec_draft
apply_mode == manual_review_only
draft_status == needs_concrete_replacements
provider_execution_performed == false
operations target existing concrete files
replacements are empty while the spec is a draft
drafts are not stored under patch_specs/inbox/
```

This validator does not execute providers, apply patch specs, run Blender or write source targets.

## Reviewed patch-spec validation

Reviewed patch specs are produced from a draft plus an explicit replacement plan. They still live under ignored `output/patch_specs/`, remain manual-review-only and are not copied to `patch_specs/inbox/` automatically.

Promote the fixture draft with dry-run:

```powershell
python .\Tools\ai\promote_patch_spec_draft.py --repo-root . --draft .\Tools\ai\fixtures\patch_spec_review_draft.json --replacement-plan .\Tools\ai\fixtures\patch_spec_review_replacement_plan.json --output-dir output\patch_specs --basename reviewed_patch_spec_fixture
```

Validate the reviewed spec:

```powershell
python .\Tools\validation\check_reviewed_patch_specs.py --repo-root . --manifest .\output\patch_specs\reviewed_patch_spec_fixture_manifest.json --output .\output\validation\reviewed_patch_specs.json
```

## AI context-pack validation

AI context packs collect bounded task-scoped repository context, validation commands and stop conditions for human/AI continuation. Full packs live under ignored `output/ai_context_packs/`; compact evidence can be committed under `docs/LOCAL_VALIDATION_EVIDENCE/`.

Build the default self-improvement prototype:

```powershell
python .\Tools\ai\build_ai_context_pack.py --repo-root . --profile project_self_improvement
```

Validate the pack and compact evidence:

```powershell
python .\Tools\validation\check_ai_context_pack_contract.py --repo-root . --pack .\output\ai_context_packs\project_self_improvement.json --evidence .\docs\LOCAL_VALIDATION_EVIDENCE\project_self_improvement_context_pack_evidence.json --output .\output\validation\ai_context_pack_contract.json
```

The validator checks:

```text
kind == ai_context_pack / ai_context_pack_evidence
apply_mode == context_only
provider_execution_performed == false
required files are included
forbidden source/generated/runtime paths are blocked
validation commands and stop conditions are present
```

The validator checks:

```text
kind == reviewed_patch_spec_manifest / reviewed_patch_spec
apply_mode == manual_review_only
review_status == dry_run_passed
provider_execution_performed == false
operations target existing concrete files
replacements are present and structurally valid
reviewed specs are not stored under patch_specs/inbox/
dry-run still passes at validation time
```

This validator does not execute providers, apply patch specs, run Blender or write source targets.

## NPU pipeline helper validation

Focused import/contract smoke:

```powershell
python .\Tools\validation\check_npu_pipeline_modules.py --repo-root . --output .\output\validation\npu_pipeline_modules.json
```

Focused unit-test report:

```powershell
python .\Tools\validation\check_npu_pipeline_helper_tests.py --repo-root . --output .\output\validation\npu_pipeline_helper_tests.json
```

Direct unittest mode, useful while debugging locally:

```powershell
python .\Tools\validation\test_npu_pipeline_helpers.py
```

These tests must remain provider-free and runtime-free. They may use temporary directories, but they must not invoke Blender, NPU, GPU, Ollama, FFmpeg or modify project source files.

## Post-validation AI work packet

After local validation and index regeneration, a local advisory work packet can be generated for ChatGPT/Codex:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\Tools\workflow\run_post_validation_ai_packet.ps1
```

The default output path is only a convenience, not an architectural binding:

```text
output/ai_pipeline/repository_update_suggestions.json
output/ai_pipeline/repository_update_suggestions.md
output/ai_pipeline/repository_update_suggestions_manifest.json
```

Profiles:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\Tools\workflow\run_post_validation_ai_packet.ps1 -Profile core
powershell.exe -ExecutionPolicy Bypass -File .\Tools\workflow\run_post_validation_ai_packet.ps1 -Profile npu
powershell.exe -ExecutionPolicy Bypass -File .\Tools\workflow\run_post_validation_ai_packet.ps1 -Profile docs
```

Custom output name/location:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\Tools\workflow\run_post_validation_ai_packet.ps1 -Profile npu -OutputDir output/ai_packets -Basename npu_after_tests
```

Extra context and report inputs:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\Tools\workflow\run_post_validation_ai_packet.ps1 `
  -ContextFile docs/PROJECT_STATUS_POINT.md `
  -ContextFile Tools/npu/run_dual_ai_pipeline.py `
  -ReportFile output/validation/npu_pipeline_modules.json
```

Optional local Ollama drafting:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\Tools\workflow\run_post_validation_ai_packet.ps1 -UseOllama
```

The packet is advisory only. It must not auto-apply edits. Use it as broader local context for the next AI task after tests.

## Generated Python and Blender script policy

The generated-file policy has layered components:

```text
Tools/validation/generated_file_policy.py
Tools/validation/generated_python_policy.py
Tools/validation/check_generated_python_policy.py
Tools/validation/check_generated_blender_script_policy.py
```

Generic Python policy rules:

```text
python_syntax_error              error
warn_python_eval_exec            warning
warn_os_system                   warning
warn_subprocess_shell_true       warning
```

Blender adapter rules:

```text
requires_bpy_import              error
forbid_musgrave_node             error
forbid_open_mainfile             error
forbid_quit_blender              error
warn_save_as_mainfile            warning
```

The Blender adapter protects against the known Blender 5.x failure:

```text
ShaderNodeTexMusgrave undefined
```

## Generated artifact path policy

Generated artifact destination validation answers only:

```text
May a generated artifact be written to this repository path?
```

Default safe destinations are intentionally narrow and reviewable:

```text
output/
indexAI/
patch_specs/inbox/
patch_specs/applied/
Scripting/v61b/hotpatch/
Tools/npu/npu_code_chunks/
Tools/npu/npu_code_context.md
Tools/npu/npu_code_index.md
Tools/npu/npu_code_manifest.json
```

Explicit generated artifact destination validation:

```powershell
python .\Tools\validation\check_generated_artifact_path_policy.py --repo-root . --path .\output\ai_pipeline\dry_run_matrix_report.json --output .\output\validation\generated_artifact_path_policy.json
```

Artifact report validation:

```powershell
python .\Tools\validation\check_generated_artifact_path_policy.py --repo-root . --artifact-report .\output\ai_pipeline\dry_run_matrix_report.json --output .\output\validation\generated_artifact_path_policy.json
```

## AI pipeline dry-run matrix

Static case-definition validator:

```powershell
python .\Tools\validation\check_ai_dry_run_matrix_cases.py --repo-root . --output .\output\validation\ai_dry_run_matrix_cases.json
```

Dry-run matrix:

```powershell
python .\Tools\ai\run_pipeline_dry_run_matrix.py --repo-root . --continue-on-error --matrix-workers 8 --repeat-cases 1
```

Stress mode for the workstation:

```powershell
python .\Tools\ai\run_pipeline_dry_run_matrix.py --repo-root . --continue-on-error --matrix-workers 12 --repeat-cases 2
```

Expected matrix output:

```text
output/ai_pipeline/dry_run_matrix_report.json
output/ai_pipeline/dry_run_matrix_report.md
```

Post-run validators:

```powershell
python .\Tools\validation\check_ai_pipeline_report_contract.py --repo-root . --report .\output\ai_pipeline\dry_run_matrix\base\ai_pipeline_dry_run_report.json --require-dry-run --output .\output\validation\ai_pipeline_report_contract.json
python .\Tools\validation\check_ai_dry_run_matrix_contract.py --repo-root . --output .\output\validation\ai_dry_run_matrix_contract.json
python .\Tools\validation\check_ai_dry_run_matrix_outputs.py --repo-root . --output .\output\validation\ai_dry_run_matrix_outputs.json
python .\Tools\validation\check_generated_artifact_path_policy.py --repo-root . --artifact-report .\output\ai_pipeline\dry_run_matrix_report.json --output .\output\validation\generated_artifact_path_policy_from_matrix.json
```

Compact evidence bundle for GitHub review:

```powershell
python .\Tools\ai\build_dry_run_matrix_evidence_bundle.py --repo-root . --basename ai_pipeline_dry_run_matrix_evidence
python .\Tools\validation\check_dry_run_matrix_evidence_bundle.py --repo-root . --evidence .\docs\LOCAL_VALIDATION_EVIDENCE\ai_pipeline_dry_run_matrix_evidence.json --output .\output\validation\dry_run_matrix_evidence_bundle.json
```

The evidence bundle verifies that the generated matrix was dry-run-only, every per-case report was present, all steps were planned-only, matrix-level parallelism was used when reported, and no provider execution proof is implied.

## Standard local validation block

Use the PowerShell runner for the full local batch:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\Tools\workflow\run_local_validation_after_refactor.ps1 -SkipPull -ContinueOnError -MatrixWorkers 12 -RepeatCases 2
```

Manual core block:

```powershell
python .\Tools\validation\check_python_syntax.py --repo-root . --output .\output\validation\python_syntax.json
python .\Tools\validation\check_ai_model_json.py --repo-root . --output .\output\validation\ai_model_json.json
python .\Tools\validation\check_ai_pipeline_modules.py --repo-root . --output .\output\validation\ai_pipeline_modules.json
python .\Tools\validation\check_npu_pipeline_modules.py --repo-root . --output .\output\validation\npu_pipeline_modules.json
python .\Tools\validation\check_npu_pipeline_helper_tests.py --repo-root . --output .\output\validation\npu_pipeline_helper_tests.json
python .\Tools\validation\check_execution_plan_status.py --repo-root . --output .\output\validation\execution_plan_status.json
python .\Tools\validation\check_ai_dry_run_matrix_cases.py --repo-root . --output .\output\validation\ai_dry_run_matrix_cases.json
python .\Tools\validation\check_generated_python_policy.py --repo-root . --output .\output\validation\generated_python_policy.json
python .\Tools\validation\check_generated_artifact_path_policy.py --repo-root . --output .\output\validation\generated_artifact_path_policy.json
python .\Tools\validation\check_generated_blender_script_policy.py --repo-root . --output .\output\validation\generated_blender_script_policy.json
python .\Tools\validation\check_refactor_status_consistency.py --repo-root . --output .\output\validation\refactor_status_consistency.json
python .\Tools\validation\check_docs_links.py --repo-root . --output .\output\validation\docs_links.json
python .\Tools\validation\check_agent_memory_policy.py --repo-root . --output .\output\validation\agent_memory_policy.json
python .\Tools\validation\check_blender_shared_compat_smoke.py --repo-root . --output .\output\validation\blender_shared_compat_smoke.json
python .\Tools\ai\run_pipeline_dry_run_matrix.py --repo-root . --continue-on-error --matrix-workers 8 --repeat-cases 1
python .\Tools\validation\check_ai_pipeline_report_contract.py --repo-root . --report .\output\ai_pipeline\dry_run_matrix\base\ai_pipeline_dry_run_report.json --require-dry-run --output .\output\validation\ai_pipeline_report_contract.json
python .\Tools\validation\check_ai_dry_run_matrix_contract.py --repo-root . --output .\output\validation\ai_dry_run_matrix_contract.json
python .\Tools\validation\check_ai_dry_run_matrix_outputs.py --repo-root . --output .\output\validation\ai_dry_run_matrix_outputs.json
python .\Tools\validation\check_generated_artifact_path_policy.py --repo-root . --artifact-report .\output\ai_pipeline\dry_run_matrix_report.json --output .\output\validation\generated_artifact_path_policy_from_matrix.json
python .\Tools\ai\build_dry_run_matrix_evidence_bundle.py --repo-root . --basename ai_pipeline_dry_run_matrix_evidence
python .\Tools\validation\check_dry_run_matrix_evidence_bundle.py --repo-root . --evidence .\docs\LOCAL_VALIDATION_EVIDENCE\ai_pipeline_dry_run_matrix_evidence.json --output .\output\validation\dry_run_matrix_evidence_bundle.json
python .\Tools\ai\build_selective_execution_plan.py --repo-root . --output .\output\ai_pipeline\selective_execution_plan.json --markdown-output .\output\ai_pipeline\selective_execution_plan.md
python .\Tools\validation\check_selective_execution_plan.py --repo-root . --plan .\output\ai_pipeline\selective_execution_plan.json --output .\output\validation\selective_execution_plan.json
python .\Tools\validation\check_package_structure.py --repo-root . --output .\output\validation\package_structure.json
python .\Tools\validation\check_json_artifacts.py --repo-root . --output .\output\validation\json_artifacts.json
python .\Tools\validation\check_github_evidence_bundle.py --repo-root . --output .\output\validation\github_evidence_bundle.json
python .\Tools\validation\check_repository_change_proposals.py --repo-root . --proposal .\output\ai_pipeline\repository_change_proposals.json --output .\output\validation\repository_change_proposals_contract.json
python .\Tools\validation\check_patch_spec_drafts.py --repo-root . --manifest .\output\patch_specs\proposal_patch_specs_manifest.json --output .\output\validation\patch_spec_drafts.json
python .\Tools\validation\check_reviewed_patch_specs.py --repo-root . --manifest .\output\patch_specs\reviewed_patch_spec_manifest.json --output .\output\validation\reviewed_patch_specs.json
python .\Tools\validation\check_validation_report_contract.py --repo-root . --output .\output\validation\validation_report_contract.json
python .\Tools\npu\build_project_ai_index.py
python .\Tools\npu\build_npu_code_context.py
```

If only generated index files changed after this block, commit them as:

```powershell
git add Tools/npu/npu_code_context.md `
        Tools/npu/npu_code_index.md `
        Tools/npu/npu_code_manifest.json `
        indexAI/project_code_index.md `
        indexAI/project_code_manifest.json

git commit -m "chore: regenerate ai and npu indexes"
git push origin master
```

## Agent review patch-plan full validation

The agent-review documentation patch-plan lane has a canonical wrapper:

```powershell
python .\Tools\validation\run_agent_review_patch_plan_full_validation.py `
  --repo-root . `
  --orchestrator .\output\ai_pipeline\agent_gpu_npu_parallel_orchestrator_live.json `
  --evidence .\output\ai_pipeline\agent_review_evidence_sufficiency.json `
  --min-patch-plans 12 `
  --expect-fallback `
  --bundle-basename agent_review_doc_patch_plan_evidence `
  --output .\output\validation\agent_review_patch_plan_full_validation.json `
  --markdown-output .\output\validation\agent_review_patch_plan_full_validation.md
```

The wrapper runs:

```text
run_agent_review_patch_plan_smoke.py
check_docs_links.py
check_python_syntax.py
check_validation_report_contract.py
build_github_evidence_bundle.py
check_github_evidence_bundle.py
git diff --check
git status --short
```

Expected tracked evidence:

```text
docs/LOCAL_VALIDATION_EVIDENCE/agent_review_doc_patch_plan_evidence.json
docs/LOCAL_VALIDATION_EVIDENCE/agent_review_doc_patch_plan_evidence.md
```

This lane is provider-free, patch-runner-free and documentation-only. Long reports remain under ignored output/**; GitHub review uses only the compact task-scoped evidence bundle.

<!-- IA-CARMINE:PATCH-PLAN-APPLICATION:START -->

## IA-Carmine patch-plan application notes

This managed block was generated from `output/patch_specs/agent_review_patch_plan.json`.
It records the manual-review patch-plan decisions for this file without applying runtime/provider changes.

### `det_doc_doc_003` — `doc_doc`

- Source: `gpu_recommendation`
- Status: `ready_for_manual_review`
- Risk: `low`
- Target file: `Tools/validation/README.md`
- Manual review required: `True`
- Rationale: contract doc exists and missing terms are explicit
- Strategy: Add a compact cross-reference for `code_contract_drift`, `docs_contract_drift`. Link or summarize the canonical source instead of duplicating large contract sections.
- Validation commands:
  - `python Tools/validation/check_python_syntax.py --repo-root . --output output/validation/python_syntax.json`
  - `python Tools/validation/check_validation_report_contract.py --repo-root . --output output/validation/validation_report_contract.json`
  - `git diff --check`
  - `git status --short`
- Stop conditions:
  - Stop if the missing terms are already present after refreshing master.
  - Stop if the edit would duplicate large generated artifacts.
  - Stop if the patch would touch output/**, generated indexes, SQLite, full analysis JSON, provider settings or Blender runtime.

<!-- IA-CARMINE:PATCH-PLAN-APPLICATION:END -->

<!-- IA-CARMINE:AGENT-REVIEW-PATCH-PLAN:BEGIN id=det_doc_doc_003:tools-validation-readme.md -->

### IA-Carmine agent-review patch note

This managed note records an evidence-backed manual-review patch plan. It is intentionally compact and idempotent.

- Plan id: `det_doc_doc_003`
- Area: `doc_doc`
- Source: `gpu_recommendation`
- Risk: `low`
- Target: `Tools/validation/README.md`
- Rationale: contract doc exists and missing terms are explicit
- Strategy: Add a compact cross-reference for `code_contract_drift`, `docs_contract_drift`. Link or summarize the canonical source instead of duplicating large contract sections.
- Validation commands:
  - `python Tools/validation/check_python_syntax.py --repo-root . --output output/validation/python_syntax.json`
  - `python Tools/validation/check_validation_report_contract.py --repo-root . --output output/validation/validation_report_contract.json`
  - `git diff --check`
  - `git status --short`
- Stop conditions:
  - Stop if the missing terms are already present after refreshing master.
  - Stop if the edit would duplicate large generated artifacts.
  - Stop if the patch would touch output/**, generated indexes, SQLite, full analysis JSON, provider settings or Blender runtime.

<!-- IA-CARMINE:AGENT-REVIEW-PATCH-PLAN:END id=det_doc_doc_003:tools-validation-readme.md -->
