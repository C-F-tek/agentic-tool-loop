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
    for src in (args, args.get("original_30b_arguments") or {}, args.get("arguments") or {}):
        if not isinstance(src, dict):
            continue
        for key in ("task", "request", "query", "prompt", "instruction", "reason", "context"):
            v = src.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return compact(args, 4000)


def helper_search_queries(task: str, public_tool: str) -> list[str]:
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
    low = task.lower()
    if not any(t in low for t in ("analizza", "analyze", "review", "problema", "issue", "repo")):
        return []
    docs = []
    for rel in ("problems.md", "AGENTS.md", "README.md", "CONTEXT_INDEX.md"):
        from .repo_tools import LAB_REPO  
        if (LAB_REPO / rel).exists():
            docs.append(repo_read({"path": rel, "max_chars": 12000}, root))
    return docs


def first_read_item(docs: list[dict[str, Any]], path: str) -> dict[str, Any] | None:
    for doc in docs:
        for item in doc.get("items") or []:
            if item.get("ok") and item.get("path") == path:
                return item
    return None


def fenced_field(block: str, label: str, limit: int = 1400) -> str:
    pattern = re.compile(
        rf"{re.escape(label)}:\s*\n\s*```text\s*\n(.*?)\n```", re.DOTALL
    )
    m = pattern.search(block)
    if not m:
        return ""
    text = "\n".join(line.rstrip() for line in m.group(1).strip().splitlines())
    return compact(text, limit)


def extract_open_problems(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
    *,
    purpose: str,
    request: str,
    function: str,
    parameters: dict[str, Any] | None = None,
    expected_output: str = "",
) -> dict[str, Any]:
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
    *,
    verified_problems: list[dict[str, Any]],
    patch_targets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
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
    *,
    task: str,
    verified_problems: list[dict[str, Any]],
    status: dict[str, Any],
    useful_calls: list[dict[str, Any]],
) -> str:
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
    from .job_store import write_json, now  

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

