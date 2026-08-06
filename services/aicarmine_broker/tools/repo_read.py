from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from aicarmine_broker.config import LAB_REPO
from aicarmine_broker.infrastructure.filesystem_repo import safe_rel_path
from aicarmine_broker.job_store import now, write_json
from aicarmine_broker.tools.deterministic_common import bounded_int_arg, deterministic_input_error


def _detect_file_type(path: Path) -> str:
    """Detect file type from extension and content signature."""
    ext = path.suffix.lower()
    if ext in (".py",):
        return "python"
    if ext in (".sqlite3", ".db", ".sqlite"):
        return "sqlite"
    if ext in (".json",):
        return "json"
    if ext in (".toml",):
        return "toml"
    if ext in (".yaml", ".yml"):
        return "yaml"
    if ext in (".md",):
        return "markdown"
    # Check magic bytes for binary detection
    try:
        with open(path, "rb") as f:
            header = f.read(16)
        if len(header) == 16:
            # SQLite magic bytes: 53 4d 4c 69 74 65 20 46 6f 72 6d 61 74 20 31 3d
            sqlite_magic = b'SQLite format 3\x00'
            if header[:15] == sqlite_magic:
                return "sqlite"
            # PDF magic
            if header[:4] == b'%PDF':
                return "pdf"
            # ZIP/DOCX/XLSX/PNG/JPEG/GIF magic
            if header[:2] in (b'PK', b'\x89PNG'):
                return "binary"
            if header[:2] == b'\xff\xd8':
                return "jpeg"
            if header[:6] in (b'GIF87a', b'GIF89a'):
                return "gif"
    except Exception:
        pass
    return "text"


def _extract_sqlite_schema(db_path: Path, max_chars: int) -> str:
    """Extract SQL schema from a SQLite database file."""
    try:
        conn = sqlite3.connect(f"file:{db_path.as_uri()}?mode=ro")
        cursor = conn.cursor()
        # Get list of tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT 50")
        tables = [row[0] for row in cursor.fetchall()]
        
        result_parts = [f"# SQLite Schema Extraction\n"]
        result_parts.append(f"# Database: {db_path.name}\n")
        result_parts.append(f"# Tables found: {len(tables)}\n\n")
        
        for tbl in tables[:50]:
            result_parts.append(f"## Table: {tbl}\n")
            cursor.execute(f"PRAGMA table_info('{tbl}')")
            columns = cursor.fetchall()
            
            # Get CREATE TABLE statement
            cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{tbl}'")
            create_stmt = cursor.fetchone()
            if create_stmt and create_stmt[0]:
                result_parts.append(f"{create_stmt[0]}\n")
            
            # Show column info
            result_parts.append(f"\nColumns ({len(columns)}):\n")
            for col in columns:
                cid, name, col_type, notnull, dflt, pk = col
                result_parts.append(f"  - {name} ({col_type}) {'PRIMARY KEY' if pk else ''} {'NOT NULL' if notnull else ''}\n")
            
            # Sample data (first 10 rows)
            try:
                cursor.execute(f"SELECT * FROM {tbl} LIMIT 10")
                rows = cursor.fetchall()
                if rows:
                    result_parts.append(f"\nSample data ({len(rows)} rows):\n")
                    # Headers
                    cursor.execute(f"PRAGMA table_info('{tbl}')")
                    col_info = cursor.fetchall()
                    headers = [c[1] for c in col_info] if col_info else [f"col_{i}" for i in range(len(rows[0]))]
                    result_parts.append(" | ".join(str(h) for h in headers) + "\n")
                    result_parts.append("-" * 80 + "\n")
                    for row in rows:
                        result_parts.append(" | ".join(str(v) for v in row) + "\n")
                    result_parts.append("\n")
            except Exception as sample_err:
                result_parts.append(f"[Sample data unavailable: {sample_err}]\n")
            
            result_parts.append("\n" + "=" * 80 + "\n\n")
        
        conn.close()
        content = "\n".join(result_parts)
        return content[:max_chars]
    except Exception as exc:
        return f"# SQLite extraction failed: {exc}\n# File may be corrupted or not a valid SQLite database."


def _extract_python_ast(filepath: Path, max_chars: int) -> str:
    """Extract Python AST structure for analysis without executing code."""
    try:
        text = filepath.read_text(encoding="utf-8-sig", errors="replace")
        import ast
        tree = ast.parse(text, filename=str(filepath))
        
        result_parts = [f"# Python AST Structure Analysis\n"]
        result_parts.append(f"# File: {filepath.name}\n")
        result_parts.append(f"# Lines: {len(text.splitlines())}\n\n")
        
        # Class definitions
        classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        if classes:
            result_parts.append("## Classes\n")
            for cls in classes:
                bases = ", ".join(ast.unparse(b) for b in cls.bases) if cls.bases else ""
                result_parts.append(f"### class {cls.name}({bases})\n")
                methods = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                for m in methods:
                    args = [a.arg for a in m.args.args[1:] if a.arg != 'self']  # Skip 'self'
                    result_parts.append(f"  - def {m.name}({', '.join(args)})\n")
                result_parts.append("\n")
        
        # Top-level functions
        funcs = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if funcs:
            result_parts.append("## Functions\n")
            for fn in funcs:
                args = [a.arg for a in fn.args.args]
                result_parts.append(f"- def {fn.name}({', '.join(args)})\n")
            result_parts.append("\n")
        
        # Imports
        imports = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
        if imports:
            result_parts.append("## Imports\n")
            for imp in imports:
                if isinstance(imp, ast.Import):
                    result_parts.append(f"- import {' '.join(alias.name for alias in imp.names)}\n")
                else:
                    result_parts.append(f"- from {imp.module} import {' '.join(alias.name for alias in imp.names)}\n")
            result_parts.append("\n")
        
        content = "\n".join(result_parts)
        return content[:max_chars]
    except SyntaxError:
        return f"# Python AST extraction failed: file contains syntax errors (may be partial/incomplete code)"
    except Exception as exc:
        return f"# Python AST extraction failed: {exc}"


def _hex_dump(data: bytes, max_chars: int) -> str:
    """Generate a compact hex dump of binary data."""
    lines = []
    lines.append("# Binary file hex dump (first 512 bytes)\n")
    lines.append(f"# File size: {len(data)} bytes\n")
    lines.append(f"# SHA-256: {hashlib.sha256(data).hexdigest()}\n\n")
    
    for i in range(0, min(len(data), 512), 16):
        chunk = data[i:i+16]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{i:08x}: {hex_part:<48} |{ascii_part}|\n")
    
    content = "\n".join(lines)
    return content[:max_chars]


def _read_paths_from_items(value: object) -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return paths
    for item in value:
        if isinstance(item, str) and item.strip():
            paths.append(item.strip())
        elif isinstance(item, dict):
            for key in ("path", "file", "filename", "name"):
                candidate = item.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    paths.append(candidate.strip())
                    break
            nested = item.get("paths") or item.get("files")
            if isinstance(nested, list):
                paths.extend(str(p).strip() for p in nested if str(p).strip())
    return paths


def repo_read(args: dict[str, Any], root: Path) -> dict[str, Any]:
    paths: list[str] = []
    if isinstance(args.get("paths"), list):
        paths.extend(str(p) for p in args["paths"] if str(p).strip())
    if args.get("path"):
        paths.append(str(args["path"]))
    paths.extend(_read_paths_from_items(args.get("items") or args.get("item")))

    deduped: list[str] = []
    for raw_path in paths:
        raw_s = str(raw_path).strip()
        if raw_s and raw_s not in deduped:
            deduped.append(raw_s)
    paths = deduped

    try:
        max_chars = bounded_int_arg(args, "max_chars", default=80000, minimum=1, maximum=200000)
        requested_max_paths = bounded_int_arg(
            args,
            ("max_paths", "limit"),
            default=len(paths) or 1,
            minimum=1,
            maximum=max(1, len(paths)),
        )
        max_paths = min(requested_max_paths, len(paths))
        before = bounded_int_arg(args, "before", default=40, minimum=0, maximum=1000)
        after = bounded_int_arg(args, "after", default=120, minimum=0, maximum=1000)
        line = bounded_int_arg(args, "line", default=0, minimum=0, maximum=10_000_000)
    except Exception as exc:
        return deterministic_input_error("repo_read", exc)
    items: list[dict[str, Any]] = []

    for raw in paths[:max_paths]:
        try:
            rel = safe_rel_path(raw)
            full = (LAB_REPO / rel).resolve(strict=False)
            full.relative_to(LAB_REPO)
            if not full.exists() or not full.is_file():
                items.append({"ok": False, "path": rel, "error": "file_not_found"})
                continue
            
            # Detect file type and extract content appropriately
            file_type = _detect_file_type(full)
            
            # For SQLite files, extract schema instead of raw text
            if file_type == "sqlite":
                content = _extract_sqlite_schema(full, max_chars)
                content_type = "sqlite_schema"
            # For Python files, optionally extract AST structure
            elif file_type == "python":
                # First try AST extraction for analysis context
                ast_content = _extract_python_ast(full, max_chars // 2)
                # Then get raw text for detailed reading
                raw_text = full.read_text(encoding="utf-8-sig", errors="replace")
                if line:
                    lines = raw_text.splitlines()
                    n = max(1, min(int(line), max(1, len(lines))))
                    start = max(1, n - before)
                    end = min(len(lines), n + after)
                    text_content = "\n".join(
                        f"{i}: {lines[i - 1]}" for i in range(start, end + 1)
                    )
                else:
                    text_content = raw_text
                content = f"{ast_content}\n\n{'=' * 60}\n\n{text_content}"
                content_type = "python_ast_plus_text"
            else:
                # Default: read as text
                text = full.read_text(encoding="utf-8-sig", errors="replace")
                if line:
                    lines = text.splitlines()
                    n = max(1, min(int(line), max(1, len(lines))))
                    start = max(1, n - before)
                    end = min(len(lines), n + after)
                    content = "\n".join(
                        f"{i}: {lines[i - 1]}" for i in range(start, end + 1)
                    )
                else:
                    content = text
                content_type = "text"
            
            # Check if file is binary and needs hex dump fallback
            if file_type in ("binary", "jpeg", "gif", "pdf"):
                try:
                    raw_bytes = full.read_bytes()
                    content = _hex_dump(raw_bytes, max_chars)
                    content_type = "binary_hex_dump"
                except Exception as hex_err:
                    content = f"# Binary file read failed: {hex_err}"
                    content_type = "error"
            
            # Handle line-specific extraction for non-special content types
            if line and content_type == "text":
                lines_list = content.splitlines()
                n = max(1, min(int(line), max(1, len(lines_list))))
                start = max(1, n - before)
                end = min(len(lines_list), n + after)
                content = "\n".join(
                    f"{i}: {lines_list[i - 1]}" for i in range(start, end + 1)
                )
            
            # Compute line count from content, not raw text (which may be binary)
            content_lines = content.splitlines() if isinstance(content, str) else []
            
            item: dict[str, Any] = {
                "ok": True,
                "path": rel,
                "size_bytes": full.stat().st_size,
                "line_count": len(content_lines),
                "content_type": content_type,
                "content": content[:max_chars],
                "truncated": len(content) > max_chars,
            }
            safe_name = rel.replace("/", "__").replace("\\", "__")
            artifact = root / "reads" / f"{safe_name}.json"
            artifact_item = dict(item)
            artifact_item["content"] = content
            artifact_item["truncated"] = False
            artifact_item["inline_result_truncated"] = item["truncated"]
            artifact_item["inline_max_chars"] = max_chars
            write_json(artifact, artifact_item)
            item["artifact"] = str(artifact)
            items.append(item)
        except Exception as exc:
            items.append(
                {
                    "ok": False,
                    "path": raw,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    if not paths:
        payload = {
            "ok": False,
            "tool": "repo_read",
            "count": 0,
            "items": [],
            "error": "missing path/paths/items",
            "input_keys": sorted(str(k) for k in args.keys()),
        }
    else:
        success_count = sum(1 for item in items if isinstance(item, dict) and item.get("ok") is True)
        failed_count = sum(1 for item in items if isinstance(item, dict) and item.get("ok") is False)
        payload = {
            "ok": success_count > 0,
            "tool": "repo_read",
            "count": len(items),
            "requested_count": len(paths),
            "max_paths": max_paths,
            "success_count": success_count,
            "failed_count": failed_count,
            "all_ok": bool(items) and success_count == len(items),
            "items": items,
        }
    write_json(root / "tool-results" / f"{now()}-repo_read.json", payload)
    return payload
