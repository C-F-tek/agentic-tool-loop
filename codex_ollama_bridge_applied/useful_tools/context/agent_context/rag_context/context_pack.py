"""Build RAG context pack artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import (
    DEFAULT_CHAR_BUDGET,
    DEFAULT_EMBEDDING_ENDPOINT,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_TOP_K,
    now_iso,
    read_text,
    repo_rel,
    report_flags,
    sha256_text,
)
from .embedding import embed_batch, validate_vector
from .retrieval import hybrid_search
from .store import connect, record_retrieval_event, status


def query_from_task(repo_root: Path, query: str, task_file: str) -> tuple[str, str]:
    if query.strip():
        return query.strip(), ""
    if not task_file:
        return "", ""
    path = Path(task_file)
    if not path.is_absolute():
        path = repo_root / path
    text, error = read_text(path)
    return text[:4000], error


def build_context_pack(
    *,
    repo_root: Path,
    db_path: Path,
    query: str = "",
    task_file: str = "",
    top_k: int = DEFAULT_TOP_K,
    char_budget: int = DEFAULT_CHAR_BUDGET,
    embedding_endpoint: str = DEFAULT_EMBEDDING_ENDPOINT,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    query_embedding: bool = True,
    require_query_embedding: bool = False,
    require_results: bool = False,
) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    final_query, query_error = query_from_task(repo_root, query, task_file)
    if query_error:
        warnings.append(f"task query read warning: {query_error}")
    context_pack_id = sha256_text(f"{final_query}:{task_file}:{now_iso()}")[:32]
    if not final_query.strip():
        errors.append("query or task_file content is required")
    vector: list[float] | None = None
    norm = 0.0
    if query_embedding and final_query.strip():
        vectors, embed_errors = embed_batch(
            endpoint=embedding_endpoint,
            model=embedding_model,
            texts=[final_query],
            timeout_seconds=30,
            retries=0,
        )
        if embed_errors:
            message = "; ".join(embed_errors)
            if require_query_embedding:
                errors.append(f"query embedding required but unavailable: {message}")
            else:
                warnings.append(f"query embedding unavailable: {message}")
        elif vectors:
            vector, norm, error = validate_vector(vectors[0])
            if error:
                if require_query_embedding:
                    errors.append(f"query embedding required but rejected: {error}")
                else:
                    warnings.append(f"query embedding rejected: {error}")
    if not db_path.exists():
        warnings.append(f"rag database missing: {repo_rel(repo_root, db_path)}")
        chunks: list[dict[str, Any]] = []
        event_id = ""
        db_status = {"document_count": 0, "active_chunk_count": 0, "embedding_count": 0}
    else:
        with connect(db_path) as conn:
            db_status = status(conn)
            chunks = hybrid_search(
                conn,
                query=final_query,
                query_vector=vector,
                query_norm=norm,
                model=embedding_model,
                endpoint=embedding_endpoint,
                top_k=max(1, int(top_k)),
                char_budget=max(1, int(char_budget)),
            )
            config = {
                "embedding_endpoint": embedding_endpoint,
                "embedding_model": embedding_model,
                "query_embedding_performed": bool(vector),
                "retrieval_mode": "vector_fts5_rrf" if vector else "fts5_rrf_no_query_vector",
            }
            event_id = record_retrieval_event(
                conn,
                context_pack_id=context_pack_id,
                query=final_query,
                top_k=top_k,
                char_budget=char_budget,
                config=config,
                selected_chunk_ids=[str(item.get("chunk_id")) for item in chunks],
                warnings=warnings,
            )
    sources = sorted({str(item.get("source_path") or "") for item in chunks if item.get("source_path")})
    total_chars = sum(int(item.get("selected_chars") or len(str(item.get("text") or ""))) for item in chunks)
    if require_results and not chunks:
        errors.append("rag context pack required but no chunks were retrieved")
    pack: dict[str, Any] = {
        "schema_version": 1,
        "kind": "rag_context_pack",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "context_pack_id": context_pack_id,
        "query": final_query,
        "task_file": task_file,
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        **report_flags(),
        "db_path": repo_rel(repo_root, db_path),
        "db_status": db_status,
        "sources": sources,
        "chunks": chunks,
        "retrieved_count": len(chunks),
        "total_selected_chars": total_chars,
        "char_budget": char_budget,
        "token_budget": None,
        "retrieval_event_id": event_id,
        "retrieval_config": {
            "top_k": top_k,
            "char_budget": char_budget,
            "embedding_endpoint": embedding_endpoint,
            "embedding_model": embedding_model,
            "fts5": True,
            "vector_similarity": True,
            "fusion": "reciprocal_rank_fusion",
        },
        "provenance": [
            {
                "chunk_id": item.get("chunk_id"),
                "source_path": item.get("source_path"),
                "char_start": item.get("char_start"),
                "char_end": item.get("char_end"),
                "text_hash": item.get("text_hash"),
            }
            for item in chunks
        ],
    }
    return pack


def render_markdown(pack: dict[str, Any]) -> str:
    lines = [
        "# RAG Context Pack",
        "",
        f"- Passed: `{pack.get('passed')}`",
        f"- Context pack id: `{pack.get('context_pack_id')}`",
        f"- Retrieved chunks: `{pack.get('retrieved_count')}`",
        f"- Total selected chars: `{pack.get('total_selected_chars')}`",
        f"- DB: `{pack.get('db_path')}`",
        f"- Provider execution performed: `{pack.get('provider_execution_performed')}`",
        f"- Source writes performed: `{pack.get('source_writes_performed')}`",
        f"- Patch application performed: `{pack.get('patch_application_performed')}`",
        "",
        "## Sources",
        "",
    ]
    for source in pack.get("sources") or []:
        lines.append(f"- `{source}`")
    if pack.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {item}" for item in pack["warnings"])
    if pack.get("errors"):
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {item}" for item in pack["errors"])
    lines.extend(["", "## Chunks", ""])
    for item in pack.get("chunks") or []:
        lines.extend(
            [
                f"### `{item.get('source_path')}#{item.get('chunk_index')}`",
                "",
                f"- Chunk id: `{item.get('chunk_id')}`",
                f"- Fused score: `{item.get('fused_score')}`",
                f"- Vector rank: `{item.get('vector_rank', '')}`",
                f"- FTS rank: `{item.get('fts_rank', '')}`",
                "",
                "```text",
                str(item.get("text") or "")[:4000],
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
