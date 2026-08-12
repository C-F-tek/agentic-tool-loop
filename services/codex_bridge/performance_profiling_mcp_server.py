#!/usr/bin/env python3
"""MCP adapter for performance profiling tools."""

from __future__ import annotations

import json
import sys
from typing import Any
from pathlib import Path

from repo_mcp_common import (
    ToolSpec,
    health_payload,
    object_schema,
    self_test,
    serve,
)

SERVER_NAME = "aicarmine-performance-profiling"
SERVER_VERSION = "1.0.0"


def string_prop(default: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if default is not None:
        schema["default"] = default
    return schema


def integer_prop(default: int, minimum: int, maximum: int) -> dict[str, Any]:
    return {"type": "integer", "default": default, "minimum": minimum, "maximum": maximum}


def _tools() -> dict[str, ToolSpec]:
    from repo_mcp_common import selected_repo_root
    
    def health(args: dict[str, Any], root):
        return health_payload(SERVER_NAME, list(tools))
    
    def complexity_analysis(args: dict[str, Any], root):
        """Analyze algorithmic complexity of functions."""
        target_path = args.get("path", ".")
        full_target = Path(root) / target_path
        
        if not full_target.exists():
            return {"ok": False, "error": f"path_not_found: {target_path}"}
        
        import re
        
        results = []
        candidates = [full_target] if full_target.is_file() else list(full_target.rglob("*.py"))
        
        for pyfile in candidates:
            rel = str(pyfile.relative_to(root))
            
            try:
                with open(pyfile, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                
                # Detect function definitions
                functions = re.finditer(r'def\s+(\w+)\s*\([^)]*\)\s*:(.*?)(?=\ndef\s+\w+|$)', content, re.DOTALL)
                
                for func_match in functions:
                    func_name = func_match.group(1)
                    func_body = func_match.group(0)
                    
                    # Estimate complexity based on nested loops and conditionals
                    loops = len(re.findall(r'\b(for|while)\b', func_body))
                    conditionals = len(re.findall(r'\b(if|elif|else|match|case)\b', func_body))
                    nested_loops = len(re.findall(r'\b(for|while).*(for|while)', func_body))
                    
                    # Simple complexity estimation
                    base_complexity = 1
                    estimated_complexity = base_complexity + loops + conditionals
                    
                    # Classify complexity
                    if estimated_complexity <= 3:
                        classification = "O(1)" if estimated_complexity == 1 else "O(log n)"
                    elif estimated_complexity <= 10:
                        classification = "O(n)"
                    elif estimated_complexity <= 20:
                        classification = "O(n log n)"
                    else:
                        classification = "O(n²)"
                    
                    results.append({
                        "file": rel,
                        "function": func_name,
                        "loops": loops,
                        "conditionals": conditionals,
                        "nested_loops": nested_loops,
                        "estimated_complexity": estimated_complexity,
                        "classification": classification
                    })
            except Exception as e:
                results.append({"file": rel, "error": str(e)})
        
        return {
            "ok": True,
            "tool": "aicarmine_performance_profiling_complexity",
            "path": target_path,
            "total_functions": len(results),
            "complexity_distribution": {
                "constant": len([r for r in results if r["classification"] == "O(1)"]),
                "logarithmic": len([r for r in results if r["classification"] == "O(log n)"]),
                "linear": len([r for r in results if r["classification"] == "O(n)"]),
                "linear_log": len([r for r in results if r["classification"] == "O(n log n)"]),
                "quadratic": len([r for r in results if r["classification"] == "O(n²)"])
            },
            "sample": results[:50]
        }
    
    def memory_hotspots(args: dict[str, Any], root):
        """Identify potential memory hotspots in code."""
        target_path = args.get("path", ".")
        full_target = Path(root) / target_path
        
        if not full_target.exists():
            return {"ok": False, "error": f"path_not_found: {target_path}"}
        
        import re
        
        hotspots = []
        candidates = [full_target] if full_target.is_file() else list(full_target.rglob("*.py"))
        
        for pyfile in candidates:
            rel = str(pyfile.relative_to(root))
            
            try:
                with open(pyfile, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                
                # Detect large list/dict comprehensions
                list_comprehensions = len(re.findall(r'\[[^\]]*\sfor\s+.*\]', content))
                dict_comprehensions = len(re.findall(r'\{[^}]*\sfor\s+.*\}', content))
                
                # Detect recursive functions
                functions = re.findall(r'def\s+(\w+)', content)
                recursive = []
                for func in functions:
                    if f"{func}(" in content and content.count(f"def {func}") > 1:
                        recursive.append(func)
                
                # Detect large string concatenation
                string_ops = len(re.findall(r'\+\s*["\'\\]', content))
                
                if list_comprehensions > 5 or dict_comprehensions > 5:
                    hotspots.append({
                        "file": rel,
                        "type": "large_comprehensions",
                        "list_count": list_comprehensions,
                        "dict_count": dict_comprehensions,
                        "risk": "medium"
                    })
                
                if recursive:
                    hotspots.append({
                        "file": rel,
                        "type": "recursive_functions",
                        "functions": recursive,
                        "risk": "high"
                    })
                
                if string_ops > 10:
                    hotspots.append({
                        "file": rel,
                        "type": "string_concatenation",
                        "count": string_ops,
                        "risk": "low"
                    })
                    
            except Exception as e:
                hotspots.append({"file": rel, "error": str(e)})
        
        return {
            "ok": True,
            "tool": "aicarmine_performance_profiling_hotspots",
            "path": target_path,
            "total_hotspots": len(hotspots),
            "hotspots": hotspots[:50],
            "risk_summary": {
                "high": len([h for h in hotspots if h.get("risk") == "high"]),
                "medium": len([h for h in hotspots if h.get("risk") == "medium"]),
                "low": len([h for h in hotspots if h.get("risk") == "low"])
            }
        }
    
    def execution_patterns(args: dict[str, Any], root):
        """Analyze common execution patterns and their efficiency."""
        target_path = args.get("path", ".")
        full_target = Path(root) / target_path
        
        if not full_target.exists():
            return {"ok": False, "error": f"path_not_found: {target_path}"}
        
        import re
        
        patterns_found = {
            "linear_search": 0,
            "nested_loops": 0,
            "recursion": 0,
            "string_manipulation": 0,
            "list_growth": 0,
            "repeated_computation": 0
        }
        
        candidates = [full_target] if full_target.is_file() else list(full_target.rglob("*.py"))
        
        for pyfile in candidates:
            rel = str(pyfile.relative_to(root))
            
            try:
                with open(pyfile, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                
                # Detect linear search patterns
                if re.search(r'for\s+.*\s+in\s+.*:\s*\n\s*if\b', content):
                    patterns_found["linear_search"] += 1
                
                # Detect nested loops
                if re.search(r'for.*for|while.*for|for.*while|while.*while', content):
                    patterns_found["nested_loops"] += 1
                
                # Detect recursion
                functions = re.findall(r'def\s+(\w+)', content)
                for func in functions:
                    if f"{func}(" in content[content.index(f"def {func}"):]:
                        patterns_found["recursion"] += 1
                
                # Detect string manipulation
                if re.search(r'\.format\(|f["\']|%\s*\(.*\)', content):
                    patterns_found["string_manipulation"] += 1
                
                # Detect list growth patterns
                if re.search(r'\.append\(|\.extend\(|\.insert\(', content):
                    patterns_found["list_growth"] += 1
                
                # Detect repeated computation (same function called multiple times)
                repeated = len(re.findall(r'\b([a-zA-Z_]+)\([^)]*\)', content))
                if repeated > 20:
                    patterns_found["repeated_computation"] += 1
                    
            except Exception as e:
                pass
        
        return {
            "ok": True,
            "tool": "aicarmine_performance_profiling_patterns",
            "path": target_path,
            "patterns_found": patterns_found,
            "total_patterns": sum(patterns_found.values()),
            "efficiency_score": max(0, 100 - sum(patterns_found.values()) * 5),
            "patterns_returned": len(patterns_found),
            "returncode": 0
        }
    
    def benchmark_suggestions(args: dict[str, Any], root):
        """Generate suggestions for performance benchmarking."""
        target_path = args.get("path", ".")
        full_target = Path(root) / target_path
        
        if not full_target.exists():
            return {"ok": False, "error": f"path_not_found: {target_path}"}
        
        import re
        
        suggestions = []
        candidates = [full_target] if full_target.is_file() else list(full_target.rglob("*.py"))
        
        for pyfile in candidates:
            rel = str(pyfile.relative_to(root))
            
            try:
                with open(pyfile, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                
                # Check for computationally intensive patterns
                if re.search(r'map\(|filter\(|reduce\(', content):
                    suggestions.append({
                        "file": rel,
                        "pattern": "functional_operations",
                        "suggestion": "Consider using list comprehensions instead for better performance"
                    })
                
                if re.search(r'\.join\(|\.split\(', content):
                    suggestions.append({
                        "file": rel,
                        "pattern": "string_operations",
                        "suggestion": "Use string methods efficiently, avoid repeated concatenation"
                    })
                
                if re.search(r'@.*decorator', content):
                    suggestions.append({
                        "file": rel,
                        "pattern": "decorators",
                        "suggestion": "Ensure decorators are cached to avoid recomputation"
                    })
                
                # Check for missing caching
                if re.search(r'def\s+\w+', content):
                    functions = re.findall(r'def\s+(\w+)', content)
                    for func in functions:
                        if '@cache' not in content and '@lru_cache' not in content:
                            pattern = r'def\s+' + re.escape(func) + r'.*\n.*' + re.escape(func) + r'\('
                            if re.search(pattern, content):
                                suggestions.append({
                                    "file": rel,
                                    "function": func,
                                    "pattern": "pure_function",
                                    "suggestion": f"Consider adding @lru_cache to {func}"
                                })
                                
            except Exception as e:
                suggestions.append({"file": rel, "error": str(e)})
        
        return {
            "ok": True,
            "tool": "aicarmine_performance_profiling_benchmarks",
            "path": target_path,
            "total_suggestions": len(suggestions),
            "suggestions": suggestions[:50]
        }
    
    def performance_summary(args: dict[str, Any], root):
        """Generate overall performance summary."""
        target_path = args.get("path", ".")
        full_target = Path(root) / target_path
        
        if not full_target.exists():
            return {"ok": False, "error": f"path_not_found: {target_path}"}
        
        import re
        
        candidates = [full_target] if full_target.is_file() else list(full_target.rglob("*.py"))
        
        total_functions = 0
        total_loops = 0
        total_conditionals = 0
        total_recursion = 0
        total_string_ops = 0
        
        for pyfile in candidates:
            rel = str(pyfile.relative_to(root))
            
            try:
                with open(pyfile, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                
                functions = len(re.findall(r'def\s+\w+', content))
                loops = len(re.findall(r'\b(for|while)\b', content))
                conditionals = len(re.findall(r'\b(if|elif|else)\b', content))
                # Count recursive function calls by checking if function name appears in its body
                recursion = 0
                for func_match in re.finditer(r'def\s+(\w+)\s*\([^)]*\)', content):
                    func_name = func_match.group(1)
                    func_start = func_match.start()
                    next_def = re.search(r'\ndef\s+', content[func_start + 4:])
                    if next_def:
                        func_end = func_start + 4 + next_def.start()
                    else:
                        func_end = len(content)
                    func_body = content[func_start:func_end]
                    if re.search(r'\b' + re.escape(func_name) + r'\s*\(', func_body):
                        recursion += 1
                string_ops = len(re.findall(r'\+\s*["\'\\]', content))
                
                total_functions += functions
                total_loops += loops
                total_conditionals += conditionals
                total_recursion += recursion
                total_string_ops += string_ops
            except Exception as e:
                pass
        
        # Calculate efficiency score (higher is better)
        complexity_score = max(0, 100 - (total_loops + total_conditionals) / max(total_functions, 1) * 10)
        recursion_penalty = min(20, total_recursion * 5)
        string_penalty = min(10, total_string_ops / 10)
        
        overall_score = max(0, complexity_score - recursion_penalty - string_penalty)
        
        return {
            "ok": True,
            "tool": "aicarmine_performance_profiling_summary",
            "path": target_path,
            "total_functions": total_functions,
            "total_loops": total_loops,
            "total_conditionals": total_conditionals,
            "total_recursion": total_recursion,
            "efficiency_score": round(overall_score, 2),
            "rating": "excellent" if overall_score > 80 else "good" if overall_score > 60 else "needs_improvement"
        }
    
    tools: dict[str, ToolSpec] = {}
    
    tools["aicarmine_performance_profiling_health"] = ToolSpec(
        name="aicarmine_performance_profiling_health",
        description="Report performance profiling server health and capabilities.",
        input_schema=object_schema(),
        handler=health,
    )
    
    tools["aicarmine_performance_profiling_complexity"] = ToolSpec(
        name="aicarmine_performance_profiling_complexity",
        description="Analyze algorithmic complexity of functions.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=complexity_analysis,
    )
    
    tools["aicarmine_performance_profiling_hotspots"] = ToolSpec(
        name="aicarmine_performance_profiling_hotspots",
        description="Identify potential memory hotspots in code.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=memory_hotspots,
    )
    
    tools["aicarmine_performance_profiling_patterns"] = ToolSpec(
        name="aicarmine_performance_profiling_patterns",
        description="Analyze common execution patterns and their efficiency.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=execution_patterns,
    )
    
    tools["aicarmine_performance_profiling_benchmarks"] = ToolSpec(
        name="aicarmine_performance_profiling_benchmarks",
        description="Generate suggestions for performance benchmarking.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=benchmark_suggestions,
    )
    
    tools["aicarmine_performance_profiling_summary"] = ToolSpec(
        name="aicarmine_performance_profiling_summary",
        description="Generate overall performance summary.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=performance_summary,
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
            health_tool="aicarmine_performance_profiling_health",
            real_tool="aicarmine_performance_profiling_complexity",
            real_args={"path": "services/codex_bridge/repo_mcp_common.py"},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())