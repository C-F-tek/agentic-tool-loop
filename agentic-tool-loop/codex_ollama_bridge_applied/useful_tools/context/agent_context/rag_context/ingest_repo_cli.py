"""Ingest repository text into the internal RAG SQLite index."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .chunking import ChunkPolicy, build_chunks
from .common import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_CHUNK_MAX_CHARS,
    DEFAULT_CHUNK_MIN_CHARS,
    DEFAULT_CHUNK_OVERLAP_CHARS,
    DEFAULT_DB,
    DEFAULT_EMBEDDING_ENDPOINT,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_MAX_FILE_SIZE,
    db_path_warning,
    language_for_suffix,
    now_iso,
    read_json,
    read_text,
    repo_rel,
    resolve_repo_path,
    sha256_text,
    write_json,
)
from .embedding import embed_batch, validate_vector
from .repo_files import list_repo_text_files
from .repo_files import list_repo_text_files_from_scan
from .schema import ensure_schema, integrity_check
from .store import (
    connect,
    insert_embedding,
    mark_absent_documents_inactive,
    missing_embedding_chunks,
    status,
    upsert_document_chunks,
)

SINGLETON_FINAL_RETRY_DELAYS = (0.75, 2.0, 5.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--embedding-endpoint", default=DEFAULT_EMBEDDING_ENDPOINT)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--chunk-min-chars", type=int, default=DEFAULT_CHUNK_MIN_CHARS)
    parser.add_argument("--chunk-max-chars", type=int, default=DEFAULT_CHUNK_MAX_CHARS)
    parser.add_argument("--chunk-overlap-chars", type=int, default=DEFAULT_CHUNK_OVERLAP_CHARS)
    parser.add_argument("--max-file-size", type=int, default=DEFAULT_MAX_FILE_SIZE)
    parser.add_argument("--startup-scan-index", default="")
    parser.add_argument("--skip-embeddings", action="store_true")
    parser.add_argument("--require-embeddings", action="store_true")
    parser.add_argument("--allow-missing-embeddings", action="store_true")
    parser.add_argument("--output", default="output/validation/rag_ingest_repo.json")
    parser.add_argument("--markdown-output", default="output/validation/rag_ingest_repo.md")
    return parser.parse_args()


def render_markdown(report: dict) -> str:
    lines = [
        "# RAG Repo Ingest",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Action: `{report.get('action')}`",
        f"- RAG index ready: `{report.get('rag_index_ready')}`",
        f"- DB: `{report.get('db_path')}`",
        f"- Files indexed: `{report.get('indexed_file_count')}`",
        f"- Files read: `{report.get('read_file_count')}`",
        f"- Files chunked: `{report.get('chunked_file_count')}`",
        f"- Chunks indexed: `{report.get('chunk_count')}`",
        f"- Unchanged ref-only files: `{report.get('unchanged_ref_only_document_count')}`",
        f"- Embeddings written: `{report.get('embedding_written_count')}`",
        f"- Missing embeddings after: `{report.get('missing_embedding_count_after')}`",
        f"- SQLite integrity: `{report.get('sqlite_integrity_check')}`",
        f"- Resource lane: `{report.get('resource_lane')}`",
        f"- Ollama embedding performed: `{report.get('ollama_embedding_performed')}`",
        f"- Provider execution performed: `{report.get('provider_execution_performed')}`",
        f"- Providers not started reason: `{report.get('providers_not_started_reason')}`",
        "",
    ]
    if report.get("embedding_failure_samples"):
        lines.extend(["## Embedding Failure Samples", ""])
        for item in report["embedding_failure_samples"][:20]:
            lines.append(
                "- `{path}` chunk `{index}` blocker `{blocker}` hash `{text_hash}`: {errors}".format(
                    path=item.get("source_path") or item.get("chunk_id"),
                    index=item.get("chunk_index"),
                    blocker=item.get("blocker") or "",
                    text_hash=item.get("text_hash") or "",
                    errors="; ".join(str(error) for error in item.get("errors", [])[:3]),
                )
            )
    if report.get("warnings"):
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {item}" for item in report["warnings"][:80])
    if report.get("errors"):
        lines.extend(["## Errors", ""])
        lines.extend(f"- {item}" for item in report["errors"])
    return "\n".join(lines).rstrip() + "\n"


def _embedding_failure_sample(item: dict, errors: list[str]) -> dict:
    return {
        "chunk_id": str(item.get("chunk_id") or ""),
        "source_path": str(item.get("source_path") or ""),
        "chunk_index": item.get("chunk_index"),
        "text_hash": str(item.get("text_hash") or ""),
        "text_preview": str(item.get("text") or "")[:300],
        "blocker": "rag_embedding_singleton_failed",
        "errors": errors[:3],
    }


def _insert_embedding_vectors(
    conn,
    *,
    batch: list[dict],
    vectors: list[list[float]],
    model: str,
    endpoint: str,
) -> tuple[int, list[dict]]:
    written = 0
    failures: list[dict] = []
    for item, vector in zip(batch, vectors):
        values, norm, error = validate_vector(vector)
        if error:
            failures.append(_embedding_failure_sample(item, [error]))
            continue
        insert_embedding(
            conn,
            chunk_id=str(item["chunk_id"]),
            model=model,
            endpoint=endpoint,
            vector=values,
            norm=norm,
        )
        written += 1
    return written, failures


def _embed_group_with_split(
    conn,
    *,
    group: list[dict],
    args: argparse.Namespace,
    embedder=embed_batch,
    retry_events: list[dict],
) -> tuple[int, list[dict]]:
    vectors, batch_errors = embedder(
        endpoint=args.embedding_endpoint,
        model=args.embedding_model,
        texts=[str(item["text"]) for item in group],
        timeout_seconds=60,
        retries=1,
    )
    if not batch_errors and len(vectors) == len(group):
        return _insert_embedding_vectors(
            conn,
            batch=group,
            vectors=vectors,
            model=args.embedding_model,
            endpoint=args.embedding_endpoint,
        )
    if len(group) > 1:
        midpoint = max(1, len(group) // 2)
        retry_events.append(
            {
                "action": "split_batch_after_embedding_error",
                "batch_size": len(group),
                "left_size": midpoint,
                "right_size": len(group) - midpoint,
                "errors": batch_errors[:3],
            }
        )
        left_written, left_failures = _embed_group_with_split(
            conn,
            group=group[:midpoint],
            args=args,
            embedder=embedder,
            retry_events=retry_events,
        )
        right_written, right_failures = _embed_group_with_split(
            conn,
            group=group[midpoint:],
            args=args,
            embedder=embedder,
            retry_events=retry_events,
        )
        return left_written + right_written, left_failures + right_failures
    return _embed_singleton_final_retry(
        conn,
        item=group[0],
        initial_errors=batch_errors or ["embedding request failed"],
        args=args,
        embedder=embedder,
        retry_events=retry_events,
    )


def _singleton_final_retry_delays(args: argparse.Namespace) -> tuple[float, ...]:
    value = getattr(args, "final_singleton_retry_delays", None)
    if value is None:
        return SINGLETON_FINAL_RETRY_DELAYS
    return tuple(max(0.0, float(item)) for item in value)


def _embed_singleton_final_retry(
    conn,
    *,
    item: dict,
    initial_errors: list[str],
    args: argparse.Namespace,
    embedder=embed_batch,
    retry_events: list[dict],
) -> tuple[int, list[dict]]:
    errors = list(initial_errors)
    delays = _singleton_final_retry_delays(args)
    for attempt, delay in enumerate(delays, start=1):
        if delay > 0:
            time.sleep(delay)
        vectors, retry_errors = embedder(
            endpoint=args.embedding_endpoint,
            model=args.embedding_model,
            texts=[str(item["text"])],
            timeout_seconds=90,
            retries=1,
        )
        retry_events.append(
            {
                "action": "singleton_final_retry",
                "attempt": attempt,
                "delay_seconds": delay,
                "chunk_id": str(item.get("chunk_id") or ""),
                "source_path": str(item.get("source_path") or ""),
                "errors": retry_errors[:3],
                "passed": not retry_errors and len(vectors) == 1,
            }
        )
        if not retry_errors and len(vectors) == 1:
            written, failures = _insert_embedding_vectors(
                conn,
                batch=[item],
                vectors=vectors,
                model=args.embedding_model,
                endpoint=args.embedding_endpoint,
            )
            if written == 1 and not failures:
                return written, []
            for failure in failures:
                failure["blocker"] = "rag_embedding_singleton_failed"
            errors = [str(error) for failure in failures for error in failure.get("errors", [])]
            continue
        errors = retry_errors or [f"embedding count mismatch: got {len(vectors)}, expected 1"]
    prefixed_written, prefixed_errors = _embed_singleton_with_source_prefix(
        conn,
        item=item,
        args=args,
        embedder=embedder,
        retry_events=retry_events,
    )
    if prefixed_written:
        return prefixed_written, []
    errors = prefixed_errors or errors
    failure = _embedding_failure_sample(item, errors or initial_errors)
    failure["final_retry_attempt_count"] = len(delays)
    return 0, [failure]


def _embed_singleton_with_source_prefix(
    conn,
    *,
    item: dict,
    args: argparse.Namespace,
    embedder=embed_batch,
    retry_events: list[dict],
) -> tuple[int, list[str]]:
    text = (
        f"Source: {item.get('source_path')}\n"
        f"Chunk: {item.get('chunk_index')}\n\n"
        f"{item.get('text') or ''}"
    )
    vectors, errors = embedder(
        endpoint=args.embedding_endpoint,
        model=args.embedding_model,
        texts=[text],
        timeout_seconds=90,
        retries=1,
    )
    retry_events.append(
        {
            "action": "singleton_source_prefixed_retry",
            "chunk_id": str(item.get("chunk_id") or ""),
            "source_path": str(item.get("source_path") or ""),
            "errors": errors[:3],
            "passed": not errors and len(vectors) == 1,
        }
    )
    if errors or len(vectors) != 1:
        return 0, errors or [f"embedding count mismatch: got {len(vectors)}, expected 1"]
    values, norm, error = validate_vector(vectors[0])
    if error:
        return 0, [error]
    insert_embedding(
        conn,
        chunk_id=str(item["chunk_id"]),
        model=args.embedding_model,
        endpoint=args.embedding_endpoint,
        vector=values,
        norm=norm,
        metadata={
            "embedding_text_transform": "source_path_prefixed_singleton_retry",
            "source_path": str(item.get("source_path") or ""),
            "text_hash": str(item.get("text_hash") or ""),
        },
    )
    return 1, []


def embed_pending_chunks(
    conn,
    *,
    pending: list[dict],
    args: argparse.Namespace,
    embedder=embed_batch,
) -> dict:
    written = 0
    failures: list[dict] = []
    retry_events: list[dict] = []
    batch_size = max(1, int(args.batch_size))
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        batch_written, batch_failures = _embed_group_with_split(
            conn,
            group=batch,
            args=args,
            embedder=embedder,
            retry_events=retry_events,
        )
        written += batch_written
        failures.extend(batch_failures)
    return {
        "written": written,
        "failures": failures,
        "retry_events": retry_events,
    }


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    db_path = resolve_repo_path(repo_root, args.db)
    output = resolve_repo_path(repo_root, args.output)
    markdown = resolve_repo_path(repo_root, args.markdown_output)
    warnings: list[str] = []
    errors: list[str] = []
    warning = db_path_warning(repo_root, db_path)
    if warning:
        warnings.append(warning)
    ensure_schema(db_path)
    startup_scan = read_json(Path(args.startup_scan_index)) if args.startup_scan_index else {}
    if startup_scan:
        files, skipped, discover_warnings = list_repo_text_files_from_scan(
            repo_root,
            startup_scan,
            max_file_size=max(1, int(args.max_file_size)),
        )
    else:
        files, skipped, discover_warnings = list_repo_text_files(
            repo_root, max_file_size=max(1, int(args.max_file_size))
        )
    warnings.extend(discover_warnings)
    policy = ChunkPolicy(
        min_chars=args.chunk_min_chars,
        max_chars=args.chunk_max_chars,
        overlap_chars=args.chunk_overlap_chars,
    ).normalized()
    indexed = 0
    chunk_count = 0
    changed_documents = 0
    unchanged_documents = 0
    unchanged_ref_only_documents = 0
    read_file_count = 0
    chunked_file_count = 0
    indexed_source_paths: set[str] = set()
    read_warnings: list[str] = []
    with connect(db_path) as conn:
        active_rows = conn.execute(
            "SELECT source_path, file_size, mtime_ns, content_hash FROM rag_documents WHERE status='active'"
        ).fetchall()
        active_docs = {str(row["source_path"]): dict(row) for row in active_rows}
        for item in files:
            indexed_source_paths.add(item.rel_path)
            active_doc = active_docs.get(item.rel_path)
            if active_doc and int(active_doc.get("file_size") or 0) == int(item.size_bytes):
                try:
                    current_mtime = int(item.path.stat().st_mtime_ns)
                except OSError:
                    current_mtime = 0
                if current_mtime and current_mtime == int(active_doc.get("mtime_ns") or 0):
                    unchanged_documents += 1
                    unchanged_ref_only_documents += 1
                    indexed += 1
                    continue
            text, read_error = read_text(item.path)
            read_file_count += 1
            if read_error:
                read_warnings.append(f"{item.rel_path}: {read_error}")
            if not text.strip():
                continue
            content_hash = sha256_text(text)
            chunks = build_chunks(
                source_path=item.rel_path,
                text=text,
                content_hash=content_hash,
                policy=policy,
                metadata={"language": language_for_suffix(item.suffix)},
            )
            chunked_file_count += 1
            result = upsert_document_chunks(
                conn,
                source_path=item.rel_path,
                file_size=item.size_bytes,
                mtime_ns=item.path.stat().st_mtime_ns,
                suffix=item.suffix,
                content_hash=content_hash,
                chunks=chunks,
                metadata={"ingested_at": now_iso()},
            )
            indexed_source_paths.add(item.rel_path)
            if result.get("changed"):
                changed_documents += 1
            else:
                unchanged_documents += 1
            indexed += 1
            chunk_count += int(result["chunk_count"])
        removed_documents = mark_absent_documents_inactive(conn, indexed_source_paths)
        embedding_written = 0
        embedding_errors: list[str] = []
        embedding_failures: list[dict] = []
        embedding_failure_samples: list[dict] = []
        embedding_retry_events: list[dict] = []
        missing_before = missing_embedding_chunks(
            conn,
            model=args.embedding_model,
            endpoint=args.embedding_endpoint,
        )
        if not args.skip_embeddings:
            embedding_result = embed_pending_chunks(conn, pending=missing_before, args=args)
            embedding_written = int(embedding_result["written"])
            embedding_failures.extend(embedding_result["failures"])
            embedding_retry_events = embedding_result["retry_events"][:80]
        missing_after = missing_embedding_chunks(
            conn,
            model=args.embedding_model,
            endpoint=args.embedding_endpoint,
        )
        if missing_after and not args.skip_embeddings and embedding_failures:
            rescue_args = argparse.Namespace(**vars(args))
            rescue_args.batch_size = 1
            rescue_args.final_singleton_retry_delays = [1.0, 3.0, 6.0]
            rescue_result = embed_pending_chunks(conn, pending=missing_after, args=rescue_args)
            embedding_written += int(rescue_result["written"])
            embedding_failures.extend(rescue_result["failures"])
            embedding_retry_events.append(
                {
                    "action": "final_missing_embedding_rescue_pass",
                    "pending_before": len(missing_after),
                    "written": rescue_result["written"],
                }
            )
            embedding_retry_events.extend(rescue_result["retry_events"])
            missing_after = missing_embedding_chunks(
                conn,
                model=args.embedding_model,
                endpoint=args.embedding_endpoint,
            )
        remaining_ids = {str(item.get("chunk_id") or "") for item in missing_after}
        active_failures = [
            failure
            for failure in embedding_failures
            if str(failure.get("chunk_id") or "") in remaining_ids
        ]
        known_failure_ids = {str(item.get("chunk_id") or "") for item in active_failures}
        for item in missing_after:
            chunk_id = str(item.get("chunk_id") or "")
            if chunk_id and chunk_id not in known_failure_ids:
                active_failures.append(
                    _embedding_failure_sample(
                        item,
                        ["embedding missing after final rescue pass"],
                    )
                )
        embedding_failure_samples = active_failures[:80]
        for failure in active_failures:
            source = failure.get("source_path") or failure.get("chunk_id")
            errors_for_chunk = failure.get("errors") if isinstance(failure.get("errors"), list) else []
            embedding_errors.append(f"{source}: {'; '.join(str(item) for item in errors_for_chunk[:3])}")
        if (args.require_embeddings or not args.allow_missing_embeddings) and embedding_errors:
            errors.extend(embedding_errors)
        elif embedding_errors:
            warnings.extend(f"embedding warning: {item}" for item in embedding_errors)
        db_status = status(conn)
    integrity = integrity_check(db_path)
    if integrity != "ok":
        errors.append(f"sqlite integrity check failed: {integrity}")
    if not db_status.get("active_chunk_count"):
        errors.append("rag index has no active chunks")
    if (args.require_embeddings or not args.allow_missing_embeddings) and missing_after:
        errors.append(f"missing embeddings after ingest: {len(missing_after)}")
    action = (
        "noop_current"
        if changed_documents == 0
        and removed_documents == 0
        and not missing_before
        and not missing_after
        and embedding_written == 0
        else "ingest_updated"
    )
    rag_index_ready = bool(
        not errors
        and integrity == "ok"
        and db_status.get("active_chunk_count")
        and not missing_after
    )
    warnings.extend(read_warnings[:40])
    report = {
        "schema_version": 1,
        "kind": "rag_repo_ingest",
        "generated_at": now_iso(),
        "repo_root": str(repo_root),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "action": action,
        "rag_index_ready": rag_index_ready,
        "resource_lane": f"ollama_embedding:{args.embedding_endpoint}",
        "ollama_embedding_performed": bool((not args.skip_embeddings) and missing_before),
        "embedding_provider_role": "rag_index_embedding_not_provider_planning",
        "providers_not_started_reason": "" if rag_index_ready else "startup_rag_index_not_ready",
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "db_path": repo_rel(repo_root, db_path),
        "startup_repo_scan_index_used": bool(startup_scan),
        "startup_repo_scan_file_count": int(startup_scan.get("file_count") or 0),
        "sqlite_integrity_check": integrity,
        "indexed_file_count": indexed,
        "read_file_count": read_file_count,
        "chunked_file_count": chunked_file_count,
        "candidate_file_count": len(files),
        "skipped_file_count": len(skipped),
        "skipped_files_sample": skipped[:80],
        "chunk_count": chunk_count,
        "changed_document_count": changed_documents,
        "unchanged_document_count": unchanged_documents,
        "unchanged_ref_only_document_count": unchanged_ref_only_documents,
        "removed_document_count": removed_documents,
        "missing_embedding_count_before": len(missing_before),
        "missing_embedding_count_after": len(missing_after),
        "embedding_written_count": embedding_written,
        "embedding_failure_samples": embedding_failure_samples,
        "embedding_retry_events": embedding_retry_events,
        "embedding_model": args.embedding_model,
        "embedding_endpoint": args.embedding_endpoint,
        "batch_size": args.batch_size,
        "chunk_policy": policy.__dict__,
        "db_status": db_status,
    }
    write_json(output, report)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
