#!/usr/bin/env python3
"""Tool-agnostic artifact domain registry.

The registry describes artifact domains, proposal kinds, evidence kinds, pack
kinds and safety policies without binding the framework to one runtime such as
Blender or one artifact class such as source code.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ArtifactDomain:
    """Declarative policy for one artifact domain."""

    domain: str
    description: str
    proposal_kinds: tuple[str, ...] = ()
    evidence_kinds: tuple[str, ...] = ()
    pack_kinds: tuple[str, ...] = ()
    blocked_target_prefixes: tuple[str, ...] = ()
    blocked_target_suffixes: tuple[str, ...] = ()
    blocked_target_fragments: tuple[str, ...] = ()
    required_guardrails: tuple[str, ...] = (
        "manual_review_required",
        "provider_execution_performed",
        "patch_application_performed",
        "source_writes_performed",
    )
    requires_manual_review: bool = True
    runtime_allowed_by_default: bool = False
    provider_allowed_by_default: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_report_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


COMMON_BLOCKED_PREFIXES = ("output/", "renders/", ".git/")
COMMON_BLOCKED_SUFFIXES = (".db", ".sqlite", ".sqlite3")
COMMON_BLOCKED_FRAGMENTS = ("full_analysis", "analysis_full")


DOMAINS: tuple[ArtifactDomain, ...] = (
    ArtifactDomain(
        domain="code",
        description="Source/config code proposals, validators and code patch artifact packs.",
        proposal_kinds=("agent_review_code_patch_plan", "code_edit_proposal"),
        evidence_kinds=("code_contract_drift", "python_line_count_csv", "analysis_input_bundle", "code_interpreter_report"),
        pack_kinds=("code_patch_artifact_pack",),
        blocked_target_prefixes=COMMON_BLOCKED_PREFIXES + ("indexAI/code_chunks/", "indexAI/project_code_chunks/"),
        blocked_target_suffixes=COMMON_BLOCKED_SUFFIXES,
        blocked_target_fragments=COMMON_BLOCKED_FRAGMENTS,
        notes=("Code proposals may describe edits but must not apply them by default.",),
    ),
    ArtifactDomain(
        domain="docs",
        description="Documentation proposals, links, command hygiene and docs follow-up artifacts.",
        proposal_kinds=("agent_review_patch_plan", "agent_review_code_docs_followup"),
        evidence_kinds=("docs_contract_drift", "docs_links", "markdown_command_hygiene", "analysis_input_bundle"),
        pack_kinds=("github_evidence_bundle",),
        blocked_target_prefixes=COMMON_BLOCKED_PREFIXES,
        blocked_target_suffixes=COMMON_BLOCKED_SUFFIXES,
        blocked_target_fragments=COMMON_BLOCKED_FRAGMENTS,
        notes=("Documentation edits should be narrow and cross-referenced to evidence.",),
    ),
    ArtifactDomain(
        domain="validation",
        description="Validation reports, smoke reports and report-contract checks.",
        evidence_kinds=(
            "validation_report_contract",
            "github_evidence_bundle_validation",
            "agent_review_code_patch_plan_smoke",
            "code_edit_proposal_smoke",
            "analysis_input_bundle",
            "code_interpreter_report",
        ),
        pack_kinds=("github_evidence_bundle",),
        blocked_target_prefixes=COMMON_BLOCKED_PREFIXES,
        blocked_target_suffixes=COMMON_BLOCKED_SUFFIXES,
        blocked_target_fragments=COMMON_BLOCKED_FRAGMENTS,
        notes=("Validation reports may be written to output/** but compact summaries should be bundled for Git.",),
    ),
    ArtifactDomain(
        domain="workflow",
        description="Local workflow/runbook/task orchestration artifacts.",
        proposal_kinds=("workflow_update_plan",),
        evidence_kinds=("agnostic_context_stack_smoke", "core_activation_agnostic_contract", "analysis_input_bundle"),
        pack_kinds=("github_evidence_bundle",),
        blocked_target_prefixes=COMMON_BLOCKED_PREFIXES,
        blocked_target_suffixes=COMMON_BLOCKED_SUFFIXES,
        blocked_target_fragments=COMMON_BLOCKED_FRAGMENTS,
        notes=("Workflow artifacts must keep provider execution and runtime execution explicit.",),
    ),
    ArtifactDomain(
        domain="text",
        description="Plain text analysis, rewrite and prompt-independent text artifact proposals.",
        proposal_kinds=("text_artifact_proposal", "text_rewrite_plan"),
        evidence_kinds=("text_corpus_summary", "text_analysis_summary", "analysis_input_bundle"),
        pack_kinds=("text_artifact_pack",),
        blocked_target_prefixes=COMMON_BLOCKED_PREFIXES,
        blocked_target_suffixes=COMMON_BLOCKED_SUFFIXES,
        blocked_target_fragments=COMMON_BLOCKED_FRAGMENTS,
        notes=("Text is the preferred first non-code domain because validation can stay structural.",),
    ),
    ArtifactDomain(
        domain="audio",
        description="Audio analysis summaries, feature mapping and downstream creative proposals.",
        proposal_kinds=("audio_feature_mapping_plan",),
        evidence_kinds=("audio_analysis_summary", "audio_feature_summary", "analysis_input_bundle"),
        pack_kinds=("audio_artifact_pack",),
        blocked_target_prefixes=COMMON_BLOCKED_PREFIXES,
        blocked_target_suffixes=COMMON_BLOCKED_SUFFIXES,
        blocked_target_fragments=COMMON_BLOCKED_FRAGMENTS,
        notes=("Audio raw/full analysis remains local unless compacted into reviewable evidence.",),
    ),
    ArtifactDomain(
        domain="scene_spec",
        description="Scene specification, render plan and creative mapping proposals.",
        proposal_kinds=("scene_spec_proposal", "render_plan_proposal"),
        evidence_kinds=("scene_spec_summary", "render_plan_summary", "analysis_input_bundle"),
        pack_kinds=("scene_spec_artifact_pack",),
        blocked_target_prefixes=COMMON_BLOCKED_PREFIXES,
        blocked_target_suffixes=COMMON_BLOCKED_SUFFIXES,
        blocked_target_fragments=COMMON_BLOCKED_FRAGMENTS,
        runtime_allowed_by_default=False,
        notes=("Scene specs may describe Blender work but must not execute Blender by default.",),
    ),
    ArtifactDomain(
        domain="provider_result",
        description="LLM/provider outputs captured as explicit evidence reports.",
        proposal_kinds=("provider_result_followup_plan",),
        evidence_kinds=("provider_result_report", "provider_result_summary", "analysis_input_bundle"),
        pack_kinds=("provider_result_artifact_pack",),
        blocked_target_prefixes=COMMON_BLOCKED_PREFIXES,
        blocked_target_suffixes=COMMON_BLOCKED_SUFFIXES,
        blocked_target_fragments=COMMON_BLOCKED_FRAGMENTS,
        provider_allowed_by_default=False,
        notes=("Provider execution must be explicit and reflected in evidence flags.",),
    ),
)


DOMAIN_BY_NAME = {domain.domain: domain for domain in DOMAINS}


def list_domains() -> list[str]:
    """Return registered domain names."""
    return sorted(DOMAIN_BY_NAME)


def get_domain(name: str) -> ArtifactDomain | None:
    """Return one domain policy by name."""
    return DOMAIN_BY_NAME.get(name)


def registry_guardrails() -> dict[str, bool]:
    """Return default registry guardrails."""
    return {
        "manual_review_required_by_default": True,
        "provider_allowed_by_default": False,
        "runtime_allowed_by_default": False,
        "patch_application_allowed_by_default": False,
        "source_writes_allowed_by_default": False,
    }


def registry_report() -> dict[str, Any]:
    """Return a compact registry report."""
    return {
        "schema_version": 1,
        "kind": "artifact_domain_registry",
        "domain_count": len(DOMAINS),
        "domains": [domain.to_report_dict() for domain in DOMAINS],
        "guardrails": registry_guardrails(),
    }


def validate_domain(domain: ArtifactDomain, seen: set[str]) -> tuple[list[str], list[str]]:
    """Validate one domain policy and update the seen-name set."""
    errors: list[str] = []
    warnings: list[str] = []
    if not domain.domain:
        errors.append("domain name cannot be empty")
        return errors, warnings
    if domain.domain in seen:
        errors.append(f"duplicate domain: {domain.domain}")
    seen.add(domain.domain)
    if not domain.description:
        errors.append(f"{domain.domain}: description is required")
    if not domain.requires_manual_review:
        errors.append(f"{domain.domain}: requires_manual_review must remain true")
    if domain.runtime_allowed_by_default:
        errors.append(f"{domain.domain}: runtime_allowed_by_default must remain false")
    if domain.provider_allowed_by_default:
        errors.append(f"{domain.domain}: provider_allowed_by_default must remain false")
    if not (domain.proposal_kinds or domain.evidence_kinds or domain.pack_kinds):
        warnings.append(f"{domain.domain}: no artifact kinds declared")
    for guardrail in domain.required_guardrails:
        if not guardrail.endswith("performed") and guardrail != "manual_review_required":
            warnings.append(f"{domain.domain}: unusual guardrail field `{guardrail}`")
    return errors, warnings


def validate_registry() -> tuple[list[str], list[str]]:
    """Validate the static registry shape."""
    errors: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for domain in DOMAINS:
        domain_errors, domain_warnings = validate_domain(domain, seen)
        errors.extend(domain_errors)
        warnings.extend(domain_warnings)
    return errors, warnings
