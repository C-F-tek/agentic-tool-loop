"""
aicarmine_broker.helper
========================
The ``vulkan_helper`` composite tool and its supporting evidence-gathering
helpers (repo analysis, open-problem extraction, patch-plan generation).

All HTTP calls come from ``repo_tools`` indirectly through ``repo_search``,
``repo_read``, and ``repo_status``.  This module has no subprocess calls of
its own.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .config import VALID_INTERNAL_TOOLS
from .repo_tools import compact, repo_read, repo_search, repo_status


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def helper_text(args: dict[str, Any]) -> str:
    """Extract task/request text from nested argument dictionaries.

    Scans args, original_30b_arguments, and arguments for the first non-empty
    string found under keys like 'task', 'request', 'query', etc. Falls back to
    compacting the full payload when no direct instruction is found.

    Args:
        args: Nested argument dictionary from tool calls.

    Returns:
        The extracted task string, truncated at 4000 characters if needed.
    """
    for src in (args, args.get("original_30b_arguments") or {}, args.get("arguments") or {}):
        if not isinstance(src, dict):
            continue
        for key in ("task", "request", "query", "prompt", "instruction", "reason", "context"):
            v = src.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return compact(args, 4000)


def helper_search_queries(task: str, public_tool: str) -> list[str]:
    """Build deterministic search query patterns from task keywords.

    Maps semantic categories (bridge/broker, patch/fix, analysis) to ripgrep-style
    queries that the broker uses for evidence gathering. Returns up to 8 unique
    queries deduplicated and sorted by relevance.

    Args:
        task: The user-facing task string.
        public_tool: Name of the public tool being invoked.

    Returns:
        List of search query strings, max 8 entries.
    """
    low = (task + " " + public_tool).lower()
    queries: list[str] = []
    if any(t in low for t in ("bridge", "broker", "3571", "3572", "vulkan", "dispatcher")):
        queries += [
            "vulkan|bridge|broker|wrapper|tool_call|dispatcher|3571|3572",
            "tool_result_for|called_by_30b|internal_vulkan|bridge_forwarding_mode|public_tool_x",
        ]
    if any(t in low for t in ("patch", "fix", "bug", "errore", "error", "problema", "issue")):
        queries += [
            "TODO|FIXME|HACK|BUG|error|exception|traceback|raise |except ",
            "patch|diff|backup|py_compile|validator",
        ]
    if any(t in low for t in ("analizza", "analyze", "review", "repo", "repository")):
        queries += [
            "TODO|FIXME|HACK|BUG|problem|problema|issue|failure|failed|blocked",
            "not proven|evidence missing|blocked|diagnostic only|not tested",
            "raise |except |pass|return None|return \\{\\}",
        ]
    queries += [
        "vulkan_helper",
        "repo_search|repo_read|repo_status|repo_apply_patch|repo_validate|repo_command",
    ]
    seen: list[str] = []
    for q in queries:
        if q and q not in seen:
            seen.append(q)
    return seen[:8]


def evidence_from_search(result: dict[str, Any], limit: int = 12) -> list[dict[str, Any]]:
    """Parse search result matches into structured evidence rows.

    Extracts path, line number, and text from each match using colon-separated
    format (path:line:text). Returns a list of dicts suitable for downstream
    problem extraction.

    Args:
        result: Dict containing 'matches' array from repo_search tool output.
        limit: Maximum number of rows to return (default 12).

    Returns:
        List of evidence dicts with keys: raw, text, path, line, text.
    """
    evidence: list[dict[str, Any]] = []
    for raw in (result.get("matches") or [])[:limit]:
        text = str(raw)
        item: dict[str, Any] = {"raw": text, "text": text}
        parts = text.split(":", 2)
        if len(parts) >= 3 and parts[1].isdigit():
            item.update({"path": parts[0], "line": int(parts[1]), "text": parts[2]})
        evidence.append(item)
    return evidence


def changed_files_from_status(status: dict[str, Any]) -> list[str]:
    """Extract modified file paths from git diff --name-status output.

    Parses the stdout_tail of a diff_name_status result, splitting each line on
    whitespace and collecting the last token as the file path.

    Args:
        status: Dict containing results from repo_status tool with diff data.

    Returns:
            List of changed file paths (empty list if parsing fails).
    """
    try:
        text = status["results"]["diff_name_status"]["stdout_tail"]
    except Exception:
        return []
    files: list[str] = []
    for line in str(text).splitlines():
        parts = line.split()
        if len(parts) >= 2:
            files.append(parts[-1])
    return files


# ---------------------------------------------------------------------------
# Doc/problem extraction
# ---------------------------------------------------------------------------


def review_docs(task: str, root: Path) -> list[dict[str, Any]]:
    """Read repository documentation files when the task indicates analysis intent.

    Checks for problems.md, AGENTS.md, README.md, and CONTEXT_INDEX.md under the
    repo root. Only reads files that exist; returns empty list otherwise.

    Args:
        task: User-facing instruction string (lowercase keywords checked).
        root: Repository root Path object.

    Returns:
        List of doc read results from repo_read tool, max 4 items.
    """
    low = task.lower()
    if not any(t in low for t in ("analizza", "analyze", "review", "problema", "issue", "repo")):
        return []
    docs = []
    for rel in ("problems.md", "AGENTS.md", "README.md", "CONTEXT_INDEX.md"):
        from .repo_tools import LAB_REPO  # noqa: PLC0415
        if (LAB_REPO / rel).exists():
            docs.append(repo_read({"path": rel, "max_chars": 12000}, root))
    return docs


def first_read_item(docs: list[dict[str, Any]], path: str) -> dict[str, Any] | None:
    """Find the first successful read item matching a specific file path.

    Iterates through doc results looking for an item where ok=True and path matches
        exactly. Used as lookup helper for extract_open_problems.

    Args:
        docs: List of doc read result dicts from review_docs.
        path: Target file path string (e.g., 'problems.md').

    Returns:
        The matching dict or None if no match found.
    """
    for doc in docs:
        for item in doc.get("items") or []:
            if item.get("ok") and item.get("path") == path:
                return item
    return None


def fenced_field(block: str, label: str, limit: int = 1400) -> str:
    """Extract a named fenced code block from markdown content.

    Parses triple-backtick text blocks labeled with the given field name and returns
    the inner text truncated to the specified character limit.

    Args:
        block: Full markdown content string containing fenced blocks.
        label: Field name to search for (e.g., 'Evidence from code/document review').
        limit: Maximum output characters (default 1400).

    Returns:
        The extracted field text, stripped and truncated; empty string if not found.
    """
    pattern = re.compile(
        rf"{re.escape(label)}:\s*\n\s*```text\s*\n(.*?)\n```", re.DOTALL
    )
    m = pattern.search(block)
    if not m:
        return ""
    text = "\n".join(line.rstrip() for line in m.group(1).strip().splitlines())
    return compact(text, limit)


def extract_open_problems(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse open problem headings from a problems.md document.

    Scans for ### P-* heading patterns and extracts status, evidence, impact, and
    expected fix fields using fenced_field extraction. Filters out closed problems.

    Args:
        docs: List of doc read results containing problems.md content.

    Returns:
        List of problem dicts with keys: id, title, status, source, evidence, why_it_matters, expected_fix.
    """
    item = first_read_item(docs, "problems.md")
    if not item:
        return []
    content = str(item.get("content") or "")
    if "## Open problems" in content:
        content = content.split("## Open problems", 1)[1]
    if "## Closed problems" in content:
        content = content.split("## Closed problems", 1)[0]
    headings = list(re.finditer(r"^###\s+(P-\d+)\s+(.+)$", content, re.MULTILINE))
    problems: list[dict[str, Any]] = []
    for idx, m in enumerate(headings):
        block_start = m.end()
        block_end = headings[idx + 1].start() if idx + 1 < len(headings) else len(content)
        block = content[block_start:block_end].strip()
        sm = re.search(r"^Status:\s*(.+?)\s*$", block, re.MULTILINE)
        status = sm.group(1).strip() if sm else "unknown"
        if status.lower().startswith("closed"):
            continue
        title = re.sub(r"^[^\w`]+", "", m.group(2).strip()).strip()
        problems.append(
            {
                "id": m.group(1),
                "title": title,
                "status": status,
                "source": {
                    "path": "problems.md",
                    "line_count": item.get("line_count"),
                    "artifact": item.get("artifact"),
                },
                "evidence": fenced_field(block, "Evidence from code/document review"),
                "why_it_matters": fenced_field(block, "Why it matters"),
                "expected_fix": fenced_field(block, "Expected fix", limit=1800),
            }
        )
    return problems


def verified_problem_evidence(
    problems: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build minimal evidence rows from verified problem dicts.

    Extracts id, path, text (evidence or title), and status for each open problem.
        Used to populate the evidence array in final answer payloads.

    Args:
        problems: List of problem dicts from extract_open_problems.

    Returns:
        List of minimal evidence dicts with keys: problem_id, path, text, status.
    """
    return [
        {
            "problem_id": p.get("id"),
            "path": p.get("source", {}).get("path"),
            "text": p.get("evidence") or p.get("title"),
            "status": p.get("status"),
        }
        for p in problems
    ]


def patch_targets_from_verified_problems(
    problems: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract file paths referenced in verified problem evidence/fix text.

    Scans title, evidence, and expected_fix fields for backtick-wrapped file paths
        (containing / or \\). Builds a deduplicated target list with associated problem IDs.

    Args:
        problems: List of verified open problem dicts.

    Returns:
        List of patch target dicts with keys: path, problem_ids, reason.
    """
    targets: dict[str, dict[str, Any]] = {}
    for p in problems:
        text = "\n".join(str(p.get(k) or "") for k in ("title", "evidence", "expected_fix"))
        for ref in re.findall(r"`([^`]+)`", text):
            if "/" not in ref and "\\" not in ref and "." not in ref:
                continue
            path = ref.replace("\\", "/")
            rec = targets.setdefault(
                path,
                {"path": path, "problem_ids": [], "reason": "verified open problem target"},
            )
            if p.get("id") not in rec["problem_ids"]:
                rec["problem_ids"].append(p.get("id"))
    return list(targets.values())


def compact_review_docs(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Truncate doc read items to metadata and short content excerpts.

    Removes full content from each item, keeping only path, size_bytes, line_count,
        truncated flag, artifact reference, and a compact excerpt (1800 chars for problems.md, 700 otherwise).

    Args:
        docs: Full doc read results from review_docs.

    Returns:
        Truncated doc results suitable for summary output.
    """
    out: list[dict[str, Any]] = []
    for doc in docs:
        items = []
        for item in doc.get("items") or []:
            items.append(
                {
                    "ok": item.get("ok"),
                    "path": item.get("path"),
                    "size_bytes": item.get("size_bytes"),
                    "line_count": item.get("line_count"),
                    "truncated": item.get("truncated"),
                    "artifact": item.get("artifact"),
                    "content_excerpt": compact(
                        item.get("content"),
                        1800 if item.get("path") == "problems.md" else 700,
                    ),
                }
            )
        out.append({"ok": doc.get("ok"), "tool": doc.get("tool"),
                    "count": doc.get("count"), "items": items})
    return out


def repo_non_findings(status: dict[str, Any]) -> list[str]:
    """Build non-finding lines from git diff status and diff-check results.

    Collects the count of changed files from worktree state plus git diff --check
        return code and stderr tail for conflict detection reporting.

    Args:
        status: Dict containing diff_name_status and diff_check results.

    Returns:
        List of human-readable non-finding strings for answer output.
    """
    changed = changed_files_from_status(status)
    lines = [f"{len(changed)} changed files are worktree state, not automatic problems."]
    try:
        dc = status["results"]["diff_check"]
        lines.append(
            f"git diff --check returncode={dc.get('returncode')}; "
            f"stderr={compact(dc.get('stderr_tail'), 300)}"
        )
    except Exception:
        lines.append("git diff --check evidence missing.")
    return lines


# ---------------------------------------------------------------------------
# Answer builders
# ---------------------------------------------------------------------------


def _helper_call_payload(
    
    purpose: str,
    request: str,
    function: str,
    parameters: dict[str, Any] | None = None,
    expected_output: str = "",
) -> dict[str, Any]:
    """Build a structured tool call payload for the operational helper pipeline.

    Creates a nested dictionary containing the target function name, parameters,
        purpose description, and expected output contract. Used by useful_next_calls to generate follow-up instructions.

    Args:
        purpose: Human-readable description of why this call is needed.
        request: Natural language instruction for the 30b model.
        function: Target tool function name (e.g., 'repo_read', 'vulkan_helper').
        parameters: Tool-specific argument dict passed to the target function.
        expected_output: Contract string describing what the caller should return.

    Returns:
        Dict with keys: tool, fallback_tool, purpose, payload containing function_name and operation_id.
    """
    payload: dict[str, Any] = {
        "request": request,
        "function": function,
        "parameters": parameters or {},
        "expected_output": expected_output
        or "Return compact evidence only; do not invent missing files or conclusions.",
    }
    return {
        "tool": function,
        "fallback_tool": "helper_for_all",
        "purpose": purpose,
        "payload": {**payload, "tool_name": function, "operation_id": function},
    }


def useful_next_calls(
    
    verified_problems: list[dict[str, Any]],
    patch_targets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generate a prioritized sequence of follow-up tool calls based on verified problems.

    Builds up to 8 structured call payloads including: (1) read problems.md register,
        (2) read each patch target file, (3) request scoped patch plan for problem IDs,
        (4) re-check git diff --check status after edits.

    Args:
        verified_problems: List of open problem dicts from extract_open_problems.
        patch_targets: File path targets extracted from problem evidence text.

    Returns:
        List of call payload dicts max 8 entries, ordered by priority.
    """
    calls: list[dict[str, Any]] = [
        _helper_call_payload(
            purpose="Read the verified problem register before reporting or patching.",
            request="Leggi problems.md e restituisci solo problemi aperti, evidenza e fix atteso.",
            function="repo_read",
            parameters={"path": "problems.md", "max_chars": 20000},
            expected_output="Only open P-* problems with evidence, impact and expected fix.",
        )
    ]
    for p in patch_targets[:4]:
        if p.get("path"):
            calls.append(
                _helper_call_payload(
                    purpose=f"Read exact target file for verified problem: {p['path']}.",
                    request=f"Leggi il file {p['path']} e riporta le sezioni rilevanti.",
                    function="repo_read",
                    parameters={"path": p["path"], "max_chars": 24000},
                )
            )
    if verified_problems:
        ids = ", ".join(str(p.get("id")) for p in verified_problems)
        calls.append(
            _helper_call_payload(
                purpose="Ask for a scoped patch plan, not generic repo analysis.",
                request=f"Prepara un piano patch minimo per risolvere solo {ids}; non modificare file.",
                function="vulkan_helper",
                parameters={"task": f"Scoped patch plan only for verified problems: {ids}"},
            )
        )
    calls.append(
        _helper_call_payload(
            purpose="Re-check repository whitespace/conflict status after any edit.",
            request="Esegui git diff --check e riporta solo returncode e stderr.",
            function="repo_status",
        )
    )
    return calls[:8]


def answer_for_30b(
    
    task: str,
    verified_problems: list[dict[str, Any]],
    status: dict[str, Any],
    useful_calls: list[dict[str, Any]],
) -> str:
    """Build the final 30b model answer using only verified problems as evidence.

    Constructs a structured response starting with STRICT_EVIDENCE_ONLY directive,
        listing each verified problem with ID, title, status, evidence excerpt, impact,
        and expected fix. Appends non-findings from git diff and useful next calls.

    Args:
        task: Original user instruction string.
        verified_problems: List of open problems with evidence from extract_open_problems.
        status: Git diff status dict for worktree state reporting.
        useful_calls: Follow-up tool call payloads from useful_next_calls.

    Returns:
        Compact answer string (max 9000 chars) suitable as instruction_for_30b.
    """
    lines = [
        "RISPOSTA FINALE VINCOLATA ALL'EVIDENZA DEL TOOL.",
        "Non aggiungere file, moduli o problemi non presenti in verified_problems.",
        f"Richiesta: {task}",
        "",
    ]
    if verified_problems:
        lines.append("Problemi verificati:")
        for i, p in enumerate(verified_problems, 1):
            lines.append(f"{i}. {p.get('id')} - {p.get('title')} ({p.get('status')})")
            if p.get("evidence"):
                lines.append(f"   Evidenza: {compact(p.get('evidence'), 700)}")
            if p.get("why_it_matters"):
                lines.append(f"   Impatto: {compact(p.get('why_it_matters'), 700)}")
            if p.get("expected_fix"):
                lines.append(f"   Fix atteso: {compact(p.get('expected_fix'), 900)}")
    else:
        lines.append("Problemi verificati: insufficient evidence.")
    lines += ["", "Non-problemi / limiti della lettura:"]
    lines += [f"- {item}" for item in repo_non_findings(status)]
    if useful_calls:
        lines += ["", "Chiamate utili successive:"]
        for i, call in enumerate(useful_calls[:5], 1):
            payload = call.get("payload") or {}
            fn = payload.get("function") or ""
            params = compact(payload.get("parameters") or {}, 500)
            lines.append(f"{i}. {call.get('purpose')} function={fn}; parameters={params}")
    return compact("\n".join(lines), 9000)


def helper_summary(
    public_tool: str,
    task: str,
    status: dict[str, Any],
    searches: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    patch_targets: list[dict[str, Any]],
    docs: list[dict[str, Any]],
    verified_problems: list[dict[str, Any]],
) -> str:
    """Build a compact operational summary for the vulkan_helper result.

    Concatenates tool name, task, problem counts, changed file count, search matches,
        patch targets, git diff check status, doc excerpts, and search results into a single structured string.

    Args:
        public_tool: Name of the invoked public tool (e.g., 'helper_for_all').
        task: User-facing instruction string.
        status: Git diff result dict for worktree state.
        searches: List of search query results with match counts and return codes.
        evidence: Parsed evidence rows from evidence_from_search.
        patch_targets: File path targets from patch_targets_from_verified_problems.
        docs: Doc read results from review_docs.
        verified_problems: Open problem dicts from extract_open_problems.

    Returns:
        Compact summary string (max 9000 chars) for result['summary'] field.
    """
    changed = changed_files_from_status(status)
    lines = [
        f"Operational helper result for public tool X `{public_tool}`.",
        "STRICT_EVIDENCE_ONLY: final answer must use verified_problems first.",
        f"Task: {task}",
        f"Verified open problems: {len(verified_problems)}",
        f"Changed files from git diff --name-status: {len(changed)}",
        f"Secondary search evidence rows: {len(evidence)}",
        f"Verified patch target files: {len(patch_targets)}",
    ]
    for p in verified_problems:
        lines.append(f"- {p.get('id')}: {p.get('title')} [{p.get('status')}]")
        if p.get("evidence"):
            lines.append(f"  evidence: {compact(p.get('evidence'), 500)}")
    try:
        dc = status["results"]["diff_check"]
        lines.append(
            f"git diff --check rc={dc.get('returncode')} "
            f"stderr={compact(dc.get('stderr_tail'), 600)}"
        )
    except Exception:
        pass
    for doc in docs:
        for item in (doc.get("items") or [])[:2]:
            lines.append(
                f"Read `{item.get('path')}` ok={item.get('ok')} "
                f"lines={item.get('line_count')} "
                f"excerpt={compact(item.get('content'), 900)}"
            )
    for s in searches[:5]:
        lines.append(
            f"Search `{s.get('query')}` -> matches={s.get('match_count')} "
            f"rc={s.get('returncode')}"
        )
    return compact("\n".join(lines), 9000)


# ---------------------------------------------------------------------------
# vulkan_helper tool entry point
# ---------------------------------------------------------------------------


def vulkan_helper(args: dict[str, Any], root: Path) -> dict[str, Any]:
    """Main entry point for the composite operational helper tool.

    Orchestrates evidence gathering pipeline: (1) extract task from args, (2) run
        repo_status check, (3) execute search queries via helper_search_queries patterns,
        (4) read docs via review_docs, (5) extract open problems, (6) build patch targets,
        (7) generate useful_next_calls and answer_for_30b. Writes result JSON to tool-results/.

    Args:
        args: Tool arguments dict from the broker dispatcher containing public_tool_name and task.
        root: Repository root Path object for file resolution.

    Returns:
        Dict with keys: ok, tool (vulkan_helper), kind, public_tool_name, task, answer_for_30b,
            verified_problems, useful_next_calls, wrapper_call_contract, non_findings, summary,
            context_for_30b, evidence, secondary_search_evidence, patch_targets, review_docs,
            searches, repo_status, next_actions, input_args, artifact path.

    Raises:
        No explicit exceptions; errors are captured in result['ok'] field.
    """
    from .job_store import write_json, now  # noqa: PLC0415

    args = dict(args or {})
    public_tool = str(
        args.get("public_tool_name")
        or args.get("public_tool_x")
        or args.get("tool_name")
        or "helper_for_all"
    ).strip()
    task = helper_text(args)

    status = repo_status({}, root)

    searches: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for query in helper_search_queries(task, public_tool):
        result = repo_search(
            {"query": query, "mode": "rg", "path": ".", "max_results": 40}, root
        )
        searches.append(
            {
                "query": query,
                "ok": result.get("ok"),
                "returncode": result.get("returncode"),
                "match_count": len(result.get("matches") or []),
                "stderr_tail": result.get("stderr_tail"),
                "command": result.get("command"),
            }
        )
        for item in evidence_from_search(result, limit=8):
            item["query"] = query
            evidence.append(item)
        if len(evidence) >= 30:
            break

    docs = review_docs(task, root)
    verified_problems = extract_open_problems(docs)
    patch_targets = patch_targets_from_verified_problems(verified_problems)
    verified_evidence = verified_problem_evidence(verified_problems)
    summary = helper_summary(
        public_tool, task, status, searches, evidence, patch_targets, docs, verified_problems
    )
    useful_calls = useful_next_calls(
        verified_problems=verified_problems, patch_targets=patch_targets
    )
    answer = answer_for_30b(
        task=task,
        verified_problems=verified_problems,
        status=status,
        useful_calls=useful_calls,
    )

    result: dict[str, Any] = {
        "ok": True,
        "tool": "vulkan_helper",
        "kind": "operational_helper_result",
        "public_tool_name": public_tool,
        "task": task,
        "instruction_for_30b": (
            "Use answer_for_30b as the final answer unless the user asked for raw JSON. "
            "Only list verified_problems as problems."
        ),
        "answer_for_30b": answer,
        "verified_problems": verified_problems,
        "useful_next_calls": useful_calls,
        "wrapper_call_contract": {
            "public_tool": public_tool,
            "fallback_tool": "helper_for_all",
            "valid_function_hints": sorted(VALID_INTERNAL_TOOLS),
        },
        "non_findings": repo_non_findings(status),
        "summary": summary,
        "context_for_30b": answer,
        "evidence": verified_evidence,
        "secondary_search_evidence": evidence[:30],
        "patch_targets": patch_targets,
        "review_docs": compact_review_docs(docs),
        "searches": searches,
        "repo_status": status,
        "next_actions": [
            "Report only verified_problems as problems.",
            "If more detail is needed, call the specific tool from useful_next_calls.",
        ],
        "input_args": args,
    }
    artifact = root / "tool-results" / f"{now()}-vulkan_helper.json"
    artifact_payload = dict(result)
    artifact_payload["raw_review_docs"] = docs
    write_json(artifact, artifact_payload)
    result["artifact"] = str(artifact)
    return result