:#!/usr/bin/env python3
"""Simple local MCP server for intelligent search.

Tools:
  - simple_search_health
  - simple_search_ollama_generate
  - simple_search_reindex
  - simple_search_query

This server delegates to:
  - Ollama endpoint for LLM generation
  - RAG index for semantic search
  - Planner reindex for index updates

No agentic loop, no broker HTTP, no OpenWebUI.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from repo_mcp_common import (
    ToolSpec,
    health_payload,
    object_schema,
    serve,
    safe_bool,
    safe_int,
    safe_float,
)

SERVER_NAME = "aicarmine-simple-local-search-mcp"
SERVER_VERSION = "0.1.0"

# Default Ollama endpoint matches agentic loop planner constants from vulkan tool broker
DEFAULT_OLLAMA_URL = os.environ.get("SIMPLE_SEARCH_OLLAMA_URL", "http://127.0.0.1:11435/api/chat")
DEFAULT_OLLAMA_MODEL = os.environ.get("SIMPLE_SEARCH_OLLAMA_MODEL", "qwen3-task-8k")
DEFAULT_OLLAMA_KEEP_ALIVE = os.environ.get("SIMPLE_SEARCH_OLLAMA_KEEP_ALIVE", "24h")

# Default RAG DB path
DEFAULT_RAG_DB = Path(os.environ.get("AICARMINE_RAG_DB", str(Path.home() / "AI" / "state" / "codex_rag" / "code_rag.sqlite3")))


def _http_json(method: str, url: str, payload: Any | None = None, timeout: int = 30) -> dict[str, Any]:
    """Simple HTTP JSON request."""
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read()
            text = raw.decode("utf-8", errors="replace")
            if not text.strip():
                return {"status": getattr(res, "status", None)}
            if "application/json" in (res.headers.get("Content-Type") or "").lower() or text.strip().startswith(("{", "[")):
                return json.loads(text)
            return {"status": getattr(res, "status", None), "text": text[:2000]}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "detail": str(exc)[:500]}


def _ollama_generate(args: dict[str, Any]) -> dict[str, Any]:
    """Generate completion via Ollama using agentic loop planner pattern.

    Uses the same message format, keep_alive, and think parameters as the
    canonical agentic-loop planner (see aicarmine_vulkan_tool_broker.py constants).
    """
    url = args.get("url") or DEFAULT_OLLAMA_URL
    model = args.get("model") or DEFAULT_OLLAMA_MODEL
    prompt = str(args.get("prompt") or "").strip()
    system = str(args.get("system") or "").strip()
    max_tokens = safe_int(args.get("max_tokens"), 4096, low=1, high=32768)
    temperature = safe_float(args.get("temperature"), 0.1, low=0.0, high=2.0)
    keep_alive = args.get("keep_alive") or DEFAULT_OLLAMA_KEEP_ALIVE

    if not prompt:
        return {"ok": False, "error": "missing_prompt"}

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    # Agentic loop planner payload shape: model + messages + options + keep_alive + think
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": keep_alive,
        "think": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    result = _http_json("POST", url, payload=payload, timeout=120)
    if result.get("ok") is False or "error" in result:
        return result

    content = result.get("message", {}).get("content", "")
    return {
        "ok": True,
        "tool": "simple_search_ollama_generate",
        "model": model,
        "url": url,
        "content": content,
        "keep_alive": keep_alive,
        "tokens": result.get("total_duration"),
    }


def _rag_reindex(args: dict[str, Any]) -> dict[str, Any]:
    """Trigger RAG reindex via subprocess call to rag_index_repo."""
    try:
        from rag_index_repo import (
            build_index,
            MODE_DELTA,
            MODE_FULL,
            SOURCE_GIT_DEFAULT,
            SOURCE_FILESYSTEM,
            CHUNK_CHARS_DEFAULT,
            CHUNK_LINES_DEFAULT,
            MAX_FILE_BYTES_DEFAULT,
            DEFAULT_SUFFIXES,
        )
    except ImportError:
        return {"ok": False, "error": "rag_index_repo_not_available"}

    db = Path(args.get("db") or str(DEFAULT_RAG_DB)).expanduser()
    repo = Path(args.get("repo") or os.getcwd()).resolve()
    source = str(args.get("source") or SOURCE_GIT_DEFAULT).strip().lower()
    mode = str(args.get("mode") or MODE_DELTA).strip().lower()
    suffixes = set()
    if args.get("suffixes"):
        text = str(args["suffixes"]).strip()
        suffixes = {s.strip() for s in text.split(",") if s.strip()}
    max_file_bytes = safe_int(args.get("max_file_bytes"), MAX_FILE_BYTES_DEFAULT, low=1, high=100_000_000)
    chunk_lines = safe_int(args.get("chunk_lines"), CHUNK_LINES_DEFAULT, low=20, high=2000)
    chunk_chars = safe_int(args.get("chunk_chars"), CHUNK_CHARS_DEFAULT, low=1000, high=200_000)

    if source not in {SOURCE_GIT_DEFAULT, SOURCE_FILESYSTEM}:
        return {"ok": False, "error": f"unsupported source: {source}"}
    if mode not in {MODE_DELTA, MODE_FULL}:
        return {"ok": False, "error": f"unsupported mode: {mode}"}

    result = build_index(
        repo_root=repo,
        db=db,
        suffixes=suffixes,
        exclude_dirs=set(),
        max_file_bytes=max_file_bytes,
        chunk_lines=chunk_lines,
        chunk_chars=chunk_chars,
        source=source,
        mode=mode,
    )
    return {
        "ok": True,
        "tool": "simple_search_reindex",
        "selector": "git ls-files --cached --others --exclude-standard" if source == SOURCE_GIT_DEFAULT else "filesystem",
        "result": result,
    }


def _search_query(args: dict[str, Any]) -> dict[str, Any]:
    """Combined search: RAG FTS + optional Ollama reranking."""
    query = str(args.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "missing_query"}

    db = Path(args.get("db") or str(DEFAULT_RAG_DB)).expanduser()
    if not db.exists():
        return {"ok": False, "error": "rag_db_not_found", "db": str(db)}

    # FTS search
    import sqlite3
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        candidate_limit = safe_int(args.get("candidate_limit"), 80, low=1, high=300)
        rows = conn.execute(
            """
            SELECT c.id, c.path, c.start_line, c.end_line, c.symbol, c.kind, c.content, 0.0 AS rank
            FROM chunks_fts f
            JOIN chunks c ON c.id = f.rowid
            WHERE chunks_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, candidate_limit),
        ).fetchall()
        candidates = [dict(r) for r in rows]
    except Exception as exc:
        conn.close()
        # Fallback LIKE query
        like = f"%{query[:200]}%"
        rows = conn.execute(
            "SELECT id, path, start_line, end_line, symbol, kind, content, 0.0 AS rank FROM chunks WHERE content LIKE ? OR path LIKE ? LIMIT ?",
            (like, like, candidate_limit),
        ).fetchall()
        candidates = [dict(r) for r in rows]
    finally:
        conn.close()

    # Optional Ollama reranking of top candidates
    rerank_enabled = safe_bool(args.get("rerank"), False)
    if rerank_enabled and candidates:
        ollama_url = args.get("ollama_url") or DEFAULT_OLLAMA_URL
        ollama_model = args.get("ollama_model") or DEFAULT_OLLAMA_MODEL
        top_k = safe_int(args.get("top_k"), 12, low=1, high=50)
        docs = [c.get("content", "")[:2500] for c in candidates[:top_k]]
        rerank_payload = {"model": ollama_model, "query": query, "documents": docs}
        rerank_result = _http_json("POST", f"{ollama_url}/api/rerank", payload=rerank_payload, timeout=30)
        if rerank_result.get("ok") is True:
            results = rerank_result.get("results", [])
            scored = []
            for item in results:
                idx = item.get("index", 0)
                if idx < len(candidates):
                    merged = dict(candidates[idx])
                    merged["rerank_score"] = item.get("relevance_score", 0.0)
                    scored.append(merged)
            candidates = scored

    return {
        "ok": True,
        "tool": "simple_search_query",
        "query": query,
        "db": str(db),
        "candidate_count": len(candidates),
        "returned": min(len(candidates), safe_int(args.get("top_k"), 12, low=1, high=50)),
        "chunks": candidates[:safe_int(args.get("top_k"), 12, low=1, high=50)],
    }


def _health(args: dict[str, Any], root: Path, tools: dict[str, ToolSpec]) -> dict[str, Any]:
    payload = health_payload(SERVER_NAME, list(tools))
    payload.update({
        "ollama_url": DEFAULT_OLLAMA_URL,
        "ollama_model": DEFAULT_OLLAMA_MODEL,
        "rag_db": str(DEFAULT_RAG_DB),
        "tools_available": [
            "simple_search_health",
            "simple_search_ollama_generate",
            "simple_search_reindex",
            "simple_search_query",
        ],
        "no_agentic_loop": True,
        "no_broker_http": True,
    })
    # Check Ollama connectivity
    try:
        tags_result = _http_json("GET", f"{DEFAULT_OLLAMA_URL}/api/tags", timeout=5)
        payload["ollama_connected"] = "error" not in str(tags_result)
    except Exception:
        payload["ollama_connected"] = False
    return payload


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root: Path) -> dict[str, Any]:
        return _health(args, root, tools)

    tools["simple_search_health"] = ToolSpec(
        name="simple_search_health",
        description="Report simple local search MCP health, Ollama connectivity, and RAG DB status.",
        input_schema=object_schema(),
        handler=health,
    )

    tools["simple_search_ollama_generate"] = ToolSpec(
        name="simple_search_ollama_generate",
        description="Generate completion via Ollama using agentic loop planner pattern (keep_alive, think:false).",
        input_schema=object_schema({
            "prompt": {"type": "string"},
            "model": {"type": "string", "default": ""},
            "system": {"type": "string", "default": ""},
            "url": {"type": "string", "default": DEFAULT_OLLAMA_URL},
            "keep_alive": {"type": "string", "default": DEFAULT_OLLAMA_KEEP_ALIVE},
            "max_tokens": {"type": "integer", "default": 4096, "minimum": 1, "maximum": 32768},
            "temperature": {"type": "number", "default": 0.1, "minimum": 0.0, "maximum": 2.0},
        }, required=["prompt"]),
        handler=lambda args, root: _ollama_generate(args),
    )

    tools["simple_search_reindex"] = ToolSpec(
        name="simple_search_reindex",
        description="Rebuild the RAG SQLite index from Git candidates or filesystem.",
        input_schema=object_schema({
            "repo": {"type": "string"},
            "db": {"type": "string"},
            "source": {"type": "string", "enum": ["git", "filesystem"], "default": "git"},
            "mode": {"type": "string", "enum": ["delta", "full"], "default": "delta"},
            "suffixes": {"type": "string"},
            "max_file_bytes": {"type": "integer", "default": 2000000},
            "chunk_lines": {"type": "integer", "default": 180},
            "chunk_chars": {"type": "integer", "default": 35000},
        }),
        handler=lambda args, root: _rag_reindex(args),
    )

    tools["simple_search_query"] = ToolSpec(
        name="simple_search_query",
        description="Combined FTS search over RAG index with optional Ollama reranking.",
        input_schema=object_schema({
            "query": {"type": "string"},
            "db": {"type": "string"},
            "candidate_limit": {"type": "integer", "default": 80},
            "top_k": {"type": "integer", "default": 12},
            "rerank": {"type": "boolean", "default": False},
            "ollama_url": {"type": "string"},
            "ollama_model": {"type": "string"},
        }, required=["query"]),
        handler=lambda args, root: _search_query(args),
    )

    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    if "--self-test" in argv:
        print(json.dumps({"ok": True, "server": SERVER_NAME, "tool_count": len(tools)}, ensure_ascii=False))
        return 0
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())