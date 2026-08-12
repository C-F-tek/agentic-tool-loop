# AI Pipeline Package

## Purpose

`Tools/ai/pipeline/` contains the modular implementation behind the AI artifact pipeline entrypoint:

```text
Tools/ai/run_parallel_artifact_pipeline.py
```

This package is an implementation lane inside the wider unified local-AI workflow. It is not the primary operator entrypoint.

Broad local-AI work starts from:

```text
Tools/workflow/run_unified_local_ai_refactor.ps1
docs/LOCAL_AI_TASKS/unified-local-ai-refactor-launcher.md
```

## Current doctrine

```text
Full0To10 = TUTTO SU TUTTO
quick/balanced/deep/custom = intensity, not scope
pipeline dry-run != full-run proof
400-line policy applies to maintained docs and source files
limitations are backlog to overcome, not reasons to skip available tools
telemetry accompanies evidence and patch plans for completeness
```

## Package role

The package should remain:

```text
provider-agnostic
application-agnostic
import-safe
fixture/dry-run testable
report-oriented
schema-v6 compatible
non-destructive by default
```

It must not directly run Blender, FFmpeg, provider jobs or patch application unless a future explicitly validated lane changes the contract.

## Module map

| Module | Responsibility |
|---|---|
| `defaults.py` | Central constants, defaults and report filenames. |
| `models.py` | Core dataclasses and lane/result/report models. |
| `runner.py` | Low-level serial/parallel command execution helpers. |
| `compat.py` | Compatibility adapters for schema-v6 report dictionaries. |
| `artifact_contracts.py` | Expected artifact names, slugging and planned output calculation. |
| `cli.py` | CLI parser and public flags for the focused pipeline entrypoint. |
| `preflight.py` | Non-invasive input/environment/workstation checks. |
| `steps.py` | Step and command builders. |
| `scheduler.py` | Lane-aware execution schedule policy. |
| `orchestrator.py` | Concrete serial/parallel execution helpers. |
| `schema_report.py` | Schema-v6 report construction and report writing. |
| `guardrail_models.py` | Typed remediation queue/pass-result normalization. |
| `remediation.py` | Guardrail action queue loading and auto-safe remediation pass execution. |
| `refactor_status.py` | Machine-readable refactor status marker. |

## Full-run handoff rule

A pipeline report that influences run-unica evidence, recommendations, patch plans or patch specs must travel with:

```text
launcher manifest
phase_status / phase_reports
runtime tool usage telemetry
runtime/hardware capability manifest
full toolbox telemetry summary
shared AI-to-AI bundle/final summary
CSV/index/discovery/file-line evidence when relevant
```

Dry-run matrix evidence is planned-only. It does not prove provider execution, broker execution, capability availability, source-write state or Full0To10 completion.

## 400-line policy

Maintained source files in this package must stay under 400 lines.

```text
Code/script >400 lines -> compact entrypoint + responsibility-based module/package split.
Markdown >400 lines -> compact index + <file>.md/part-001.md layout.
Existing oversized files -> technical debt to refactor progressively, not blind split targets.
```

Validator:

```text
Tools/validation/check_file_line_limits.py
```

## Safe extension policy

Good additions are:

```text
small focused helpers
schema/report compatibility helpers
fixture builders
validation/report summaries
provider-neutral configuration helpers
telemetry/capability reference plumbing
file-line evidence references when maintainability is in scope
```

Avoid:

```text
broad utility dumping grounds
provider-specific inference in core pipeline modules
Blender/runtime side effects
FFmpeg/media side effects
source writes from model output
changing schema-v6 field meanings without local validation
claiming Full0To10 success from focused pipeline dry-runs
```

## Validation ownership

Focused pipeline validation can target this package directly when pipeline code changes.

Broad local-AI validation and Full0To10 evidence must route through the unified launcher runbook.

## Related docs

```text
docs/AI_PIPELINE_ARCHITECTURE.md
docs/AI_PIPELINE_REFACTOR_STATUS.md
docs/AI_PROVIDER_AGNOSTIC_PIPELINE_GUIDE.md
docs/AI_GUARDRAILS_VALIDATION_GUIDE.md
docs/LOCAL_AI_TASKS/current-code-flow-guide-2026-05-05.md
docs/LOCAL_AI_TASKS/file-line-limit-validator-2026-05-06.md
```
