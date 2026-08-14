#!/usr/bin/env python3
"""MCP adapter for context window compression tools."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import FilePath

from repo_mcp_common import (
    ToolSpec,
    health_payload,
    object_schema,
    self_test,
    serve,
)

SERVER_NAME = "aicarmine-context-compressor"
SERVER_VERSION = "1.0.0"


def string_prop(default: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if default is not None:
        schema["default"] = default
    return schema


def integer_prop(default: int, minimum: int, maximum: int) -> dict[str, Any]:
    return {"type": "integer", "default": default, "minimum": minimum, "maximum": maximum}


def _estimate_lines(filepath: str, root) -> int:
    """Estimate line count of a file."""
    from pathlib import Path
    full_path = Path(root) / filepath
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def _smart_summarize(lines: list[str], max_summary_len: int = 20) -> str:
    """Create a compact summary of file lines."""
    total = len(lines)
    if total <= max_summary_len:
        return "\n".join(lines)
    
    header = f"# {FilePath}\n"
    preview_count = max_summary_len // 3
    
    # First lines
    first_part = "\n".join(lines[:preview_count])
    # Last lines
    last_part = "\n".join(lines[-preview_count:])
    
    summary = f"{header}{first_part}\n\n...[truncated {total - 2*preview_count} lines]...\n{last_part}"
    return summary


def _build_toc(filepath: str, lines: list[str]) -> dict[str, Any]:
    """Build table of contents from file structure."""
    import re
    toc = []
    
    # Look for function definitions
    func_pattern = r'^(\s*)(def\s+(\w+))'
    class_pattern = r'^(\s*)(class\s+(\w+))'
    
    for i, line in enumerate(lines, 1):
        func_match = re.match(func_pattern, line)
        class_match = re.match(class_pattern, line)
        
        if class_match:
            indent = len(class_match.group(1))
            toc.append({
                "line": i,
                "type": "class",
                "name": class_match.group(3),
                "indent": indent
            })
        elif func_match:
            indent = len(func_match.group(1))
            toc.append({
                "line": i,
                "type": "function",
                "name": func_match.group(3),
                "indent": indent
            })
    
    return {"filepath": filepath, "toc": toc, "total_lines": len(lines)}


def _tools() -> dict[str, ToolSpec]:
    from repo_mcp_common import selected_repo_root
    
    def health(args: dict[str, Any], root):
        return health_payload(SERVER_NAME, list(tools))
    
    def summarize_file(args: dict[str, Any], root):
        """Summarize a large file for context compression."""
        filepath = args.get("path", "")
        max_summary_lines = args.get("max_summary_lines", 20)
        
        try:
            full_path = Path(root).resolve() / filepath
        except Exception as e:
            return {"ok": False, "error": f"invalid_path: {str(e)}"}
        
        if not full_path.exists():
            return {"ok": False, "error": f"path_not_found: {filepath}"}
        
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            return {"ok": False, "error": str(e)}
        
        total_lines = len(lines)
        estimated_tokens = total_lines * 7  # Rough estimate
        
        if total_lines <= max_summary_lines:
            return {
                "ok": True,
                "filepath": filepath,
                "total_lines": total_lines,
                "estimated_tokens": estimated_tokens,
                "summarized": False,
                "content": "".join(lines)
            }
        
        # Summarize
        preview = max_summary_lines // 3
        first_part = "\n".join(lines[:preview])
        last_part = "\n".join(lines[-preview:])
        
        summary = {
            "ok": True,
            "filepath": filepath,
            "total_lines": total_lines,
            "estimated_tokens": estimated_tokens,
            "summarized": True,
            "summary_preview_lines": preview,
            "content": f"{first_part}\n\n...[truncated {total_lines - 2*preview} lines]...\n{last_part}"
        }
        return summary
    
    def build_toc(args: dict[str, Any], root):
        """Build table of contents for a file."""
        filepath = args.get("path", "")
        
        full_path = Path(root) / filepath
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            return {"ok": False, "error": str(e)}
        
        toc = []
        import re
        
        func_pattern = r'^\s*(def\s+(\w+))'
        class_pattern = r'^\s*(class\s+(\w+))'
        
        for i, line in enumerate(lines, 1):
            class_match = re.match(class_pattern, line)
            if class_match:
                toc.append({
                    "line": i,
                    "type": "class",
                    "name": class_match.group(2),
                    "indent": len(line) - len(line.lstrip())
                })
            else:
                func_match = re.match(func_pattern, line)
                if func_match:
                    toc.append({
                        "line": i,
                        "type": "function",
                        "name": func_match.group(2),
                        "indent": len(line) - len(line.lstrip())
                    })
        
        return {
            "ok": True,
            "filepath": filepath,
            "total_lines": len(lines),
            "toc": toc,
            "structure_summary": {
                "classes": len([t for t in toc if t["type"] == "class"]),
                "functions": len([t for t in toc if t["type"] == "function"])
            }
        }
    
    def get_budget(args: dict[str, Any], root):
        """Get context budget allocation for files."""
        total_tokens = args.get("total_tokens", 260000)
        files = args.get("files", [])
        
        # Simple proportional allocation based on estimated lines
        allocations = {}
        remaining = total_tokens
        
        for filepath in files:
            lines = _estimate_lines(filepath, root)
            tokens = lines * 7  # Rough estimate
            
            alloc = min(tokens, total_tokens // len(files)) if files else tokens
            allocations[filepath] = {
                "estimated_lines": lines,
                "estimated_tokens": tokens,
                "allocated_budget": alloc,
                "within_budget": True
            }
        
        return {
            "ok": True,
            "total_context_budget": total_tokens,
            "files_count": len(files),
            "allocations": allocations
        }
    
    def compress_module(args: dict[str, Any], root):
        """Compress a module (directory) into compact representation."""
        module_path = args.get("path", ".")
        max_file_summary_lines = args.get("max_file_summary_lines", 15)
        
        from pathlib import Path
        full_module = Path(root) / module_path
        
        if not full_module.exists():
            return {"ok": False, "error": f"module_not_found: {module_path}"}
        
        results = []
        total_files = 0
        total_lines = 0
        total_tokens = 0
        
        for pyfile in full_module.rglob("*.py"):
            rel = pyfile.relative_to(full_module)
            try:
                with open(pyfile, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                
                total_files += 1
                file_lines = len(lines)
                total_lines += file_lines
                file_tokens = file_lines * 7
                total_tokens += file_tokens
                
                if file_lines <= max_file_summary_lines:
                    content = "".join(lines)
                    summarized = False
                else:
                    preview = max_file_summary_lines // 3
                    first_part = "\n".join(lines[:preview])
                    last_part = "\n".join(lines[-preview:])
                    content = f"{first_part}\n\n...[truncated {file_lines - 2*preview} lines]...\n{last_part}"
                    summarized = True
                
                results.append({
                    "file": str(rel),
                    "lines": file_lines,
                    "tokens_est": file_tokens,
                    "summarized": summarized,
                    "content": content
                })
            except Exception as e:
                results.append({
                    "file": str(rel),
                    "error": str(e)
                })
        
        return {
            "ok": True,
            "module": module_path,
            "total_files": total_files,
            "total_lines": total_lines,
            "total_estimated_tokens": total_tokens,
            "files": results
        }
    
    def get_context_usage(args: dict[str, Any], root):
        """Track context window usage."""
        used = args.get("used", 0)
        total = args.get("total", 260000)
        files = args.get("files", [])
        
        # Calculate per-file token usage
        file_usage = []
        for filepath in files:
            lines = _estimate_lines(filepath, root)
            tokens = lines * 7
            file_usage.append({
                "file": filepath,
                "lines": lines,
                "tokens_est": tokens
            })
        
        remaining = total - used
        percentage_used = (used / total * 100) if total > 0 else 0
        
        return {
            "ok": True,
            "context_window": {
                "total_tokens": total,
                "used_tokens": used,
                "remaining_tokens": remaining,
                "percentage_used": round(percentage_used, 2),
                "status": "critical" if percentage_used > 90 else "warning" if percentage_used > 80 else "normal"
            },
            "per_file_usage": file_usage
        }
    
    tools: dict[str, ToolSpec] = {}
    
    tools["aicarmine_context_compressor_health"] = ToolSpec(
        name="aicarmine_context_compressor_health",
        description="Report context compressor server health and capabilities.",
        input_schema=object_schema(),
        handler=health,
    )
    
    tools["aicarmine_context_compressor_summarize"] = ToolSpec(
        name="aicarmine_context_compressor_summarize",
        description="Summarize a large file for context window compression.",
        input_schema=object_schema({
            "path": string_prop(),
            "max_summary_lines": integer_prop(20, 1, 100),
        }, required=["path"]),
        handler=summarize_file,
    )
    
    tools["aicarmine_context_compressor_build_toc"] = ToolSpec(
        name="aicarmine_context_compressor_build_toc",
        description="Build table of contents for a file to enable smart navigation.",
        input_schema=object_schema({
            "path": string_prop(),
        }, required=["path"]),
        handler=build_toc,
    )
    
    tools["aicarmine_context_compressor_get_budget"] = ToolSpec(
        name="aicarmine_context_compressor_get_budget",
        description="Get context budget allocation for a set of files.",
        input_schema=object_schema({
            "total_tokens": integer_prop(260000, 10000, 1000000),
            "files": {"type": "array", "items": {"type": "string"}},
        }),
        handler=get_budget,
    )
    
    tools["aicarmine_context_compressor_compress_module"] = ToolSpec(
        name="aicarmine_context_compressor_compress_module",
        description="Compress an entire module directory into compact representation.",
        input_schema=object_schema({
            "path": string_prop("."),
            "max_file_summary_lines": integer_prop(15, 1, 100),
        }),
        handler=compress_module,
    )
    
    tools["aicarmine_context_compressor_get_context_usage"] = ToolSpec(
        name="aicarmine_context_compressor_get_context_usage",
        description="Track and report context window token usage.",
        input_schema=object_schema({
            "used": integer_prop(0, 0, 1000000),
            "total": integer_prop(260000, 10000, 1000000),
            "files": {"type": "array", "items": {"type": "string"}},
        }),
        handler=get_context_usage,
    )
    
    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    if "--self-test" in argv:
        result = self_test(
            server_name=SERVER_NAME,
            server_version=SERVER_VERSION,
            tools=tools,
            health_tool="aicarmine_context_compressor_health",
            real_tool="aicarmine_context_compressor_summarize",
            real_args={"path": "services/codex_bridge/context_compressor_mcp_server.py", "max_summary_lines": 10},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())