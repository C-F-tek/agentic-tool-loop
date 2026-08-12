#!/usr/bin/env python3
"""MCP adapter for API documentation generation tools."""

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

SERVER_NAME = "aicarmine-api-documentation"
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
    
    def generate_signature_doc(args: dict[str, Any], root):
        """Generate function signature documentation."""
        target_path = args.get("path", ".")
        full_target = Path(root) / target_path
        
        if not full_target.exists():
            return {"ok": False, "error": f"path_not_found: {target_path}"}
        
        import re
        
        functions = []
        candidates = [full_target] if full_target.is_file() else list(full_target.rglob("*.py"))
        
        for pyfile in candidates:
            rel = str(pyfile.relative_to(root))
            
            try:
                with open(pyfile, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                
                # Parse function signatures
                func_pattern = re.compile(
                    r'def\s+(\w+)\s*\(([^)]*)\)\s*(?:->\s*([\w\[\],\s]+))?\s*:',
                    re.MULTILINE
                )
                
                for match in func_pattern.finditer(content):
                    func_name = match.group(1)
                    params_str = match.group(2).strip()
                    return_type = match.group(3)
                    
                    # Parse parameters
                    params = []
                    if params_str:
                        # Handle nested types in type hints
                        depth = 0
                        current = ""
                        for char in params_str:
                            if char in ('[', '(', '<'):
                                depth += 1
                            elif char in (']', ')', '>'):
                                depth -= 1
                            elif char == ',' and depth == 0:
                                if current.strip():
                                    params.append(current.strip())
                                current = ""
                                continue
                            current += char
                        if current.strip():
                            params.append(current.strip())
                    
                    # Clean parameter strings
                    cleaned_params = []
                    for p in params:
                        if '=' in p and p.split('=')[0].strip():
                            parts = p.split('=')
                            param_name = parts[0].strip()
                            type_hint = param_name.split(':')[0].strip() if ':' in p else param_name
                            default = '='.join(parts[1:])
                            cleaned_params.append({
                                "name": param_name,
                                "type": type_hint,
                                "default": default,
                                "required": ':' in p and '=' not in p
                            })
                        elif ':' in p:
                            param_name = p.split(':')[0].strip()
                            type_hint = p.split(':', 1)[1].strip()
                            cleaned_params.append({
                                "name": param_name,
                                "type": type_hint,
                                "default": None,
                                "required": True
                            })
                        else:
                            cleaned_params.append({
                                "name": p.strip(),
                                "type": None,
                                "default": None,
                                "required": True
                            })
                    
                    functions.append({
                        "file": rel,
                        "function": func_name,
                        "params": cleaned_params,
                        "return_type": return_type,
                        "has_docstring": '"""' in content[:content.index(f'def {func_name}')] if f'def {func_name}' in content else False
                    })
            except Exception as e:
                functions.append({"file": rel, "error": str(e)})
        
        # Statistics
        total_params = sum(len(f.get("params", [])) for f in functions)
        typed_functions = len([f for f in functions if f.get("params") and any(p.get("type") for p in f["params"])])
        documented = len([f for f in functions if f.get("has_docstring")])
        
        return {
            "ok": True,
            "tool": "aicarmine_api_documentation_signatures",
            "path": target_path,
            "total_functions": len(functions),
            "total_parameters": total_params,
            "typed_functions": typed_functions,
            "documented_functions": documented,
            "sample": functions[:50]
        }
    
    def generate_class_doc(args: dict[str, Any], root):
        """Generate class documentation."""
        target_path = args.get("path", ".")
        full_target = Path(root) / target_path
        
        if not full_target.exists():
            return {"ok": False, "error": f"path_not_found: {target_path}"}
        
        import re
        
        classes = []
        candidates = [full_target] if full_target.is_file() else list(full_target.rglob("*.py"))
        
        for pyfile in candidates:
            rel = str(pyfile.relative_to(root))
            
            try:
                with open(pyfile, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                
                # Parse class definitions
                class_pattern = re.compile(r'class\s+(\w+)(?:\s*\(([^)]+)\))?\s*:', re.MULTILINE)
                
                for match in class_pattern.finditer(content):
                    class_name = match.group(1)
                    bases_str = match.group(2)
                    
                    bases = []
                    if bases_str:
                        bases = [b.strip().split('(')[0].strip() for b in bases_str.split(',')]
                    
                    # Find docstring
                    class_body_start = match.end()
                    class_body_end = content.find('\nclass ', class_body_start)
                    if class_body_end == -1:
                        class_body_end = len(content)
                    class_body = content[class_body_start:class_body_end]
                    
                    has_docstring = '"""' in class_body or "'''" in class_body
                    
                    # Find methods
                    methods = re.findall(r'def\s+(\w+)\s*\(', class_body)
                    public_methods = [m for m in methods if not m.startswith('_')]
                    private_methods = [m for m in methods if m.startswith('_') and not m.startswith('__')]
                    dunder_methods = [m for m in methods if m.startswith('__') and m.endswith('__')]
                    
                    classes.append({
                        "file": rel,
                        "class": class_name,
                        "bases": bases,
                        "has_docstring": has_docstring,
                        "total_methods": len(methods),
                        "public_methods": len(public_methods),
                        "private_methods": len(private_methods),
                        "dunder_methods": len(dunder_methods),
                        "methods": methods[:20]
                    })
            except Exception as e:
                classes.append({"file": rel, "error": str(e)})
        
        return {
            "ok": True,
            "tool": "aicarmine_api_documentation_classes",
            "path": target_path,
            "total_classes": len(classes),
            "documented_classes": len([c for c in classes if c.get("has_docstring")]),
            "sample": classes[:50]
        }
    
    def generate_module_doc(args: dict[str, Any], root):
        """Generate module-level documentation."""
        target_path = args.get("path", ".")
        full_target = Path(root) / target_path
        
        if not full_target.exists():
            return {"ok": False, "error": f"path_not_found: {target_path}"}
        
        import re
        
        modules = []
        candidates = [full_target] if full_target.is_file() else list(full_target.rglob("*.py"))
        
        for pyfile in candidates:
            rel = str(pyfile.relative_to(root))
            
            try:
                with open(pyfile, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                
                # Check for module docstring
                has_module_docstring = '"""' in content[:500] or "'''" in content[:500]
                
                # Count exports
                all_match = re.findall(r'__all__\s*=\s*\[(.*?)\]', content, re.DOTALL)
                exported = []
                if all_match:
                    exported = [x.strip().strip("'\"") for x in all_match[0].split(',')]
                
                # Count top-level definitions
                classes = len(re.findall(r'^class\s+\w+', content, re.MULTILINE))
                functions = len(re.findall(r'^def\s+\w+', content, re.MULTILINE))
                
                # Detect imports
                imports = re.findall(r'(?:import|from)\s+(\w+)', content)
                external_imports = [i for i in imports if i not in ('os', 'sys', 'path', 'typing', 're', 'collections', 'itertools', 'functools', 'abc', 'dataclasses', 'enum', 'uuid', 'logging', 'datetime', 'time', 'math', 'copy', 'contextlib', 'types', 'io', 'string', 'textwrap', 'array', 'deque', 'counter', 'defaultdict', 'namedtuple', 'chain', 'combinations', 'permutations', 'product', 'zip', 'map', 'filter', 'sorted', 'list', 'set', 'dict', 'tuple', 'range', 'enumerate', 'super', 'vars', 'type', 'isinstance', 'hasattr', 'getattr', 'setattr', 'delattr', 'property', 'staticmethod', 'classmethod', 'object', 'Exception', 'BaseException')]
                
                modules.append({
                    "file": rel,
                    "has_module_docstring": has_module_docstring,
                    "exported_items": len(exported),
                    "classes": classes,
                    "functions": functions,
                    "total_imports": len(imports),
                    "external_imports": external_imports[:10],
                    "quality_score": (
                        (1 if has_module_docstring else 0) +
                        (1 if exported else 0) +
                        (1 if external_imports else 0)
                    ) / 3 * 100
                })
            except Exception as e:
                modules.append({"file": rel, "error": str(e)})
        
        return {
            "ok": True,
            "tool": "aicarmine_api_documentation_modules",
            "path": target_path,
            "total_modules": len(modules),
            "documented_modules": len([m for m in modules if m.get("has_module_docstring")]),
            "sample": modules[:50]
        }
    
    def generate_readme_suggestions(args: dict[str, Any], root):
        """Generate README/documentation suggestions."""
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
                
                # Check for docstrings
                has_class_docs = len(re.findall(r'class\s+\w+.*"""', content)) > 0
                has_func_docs = len(re.findall(r'def\s+\w+.*"""', content)) > 0
                
                # Check for type hints
                has_type_hints = '->' in content and ':' in content
                
                # Check for __all__
                has_exports = '__all__' in content
                
                # Generate suggestions
                if not has_class_docs:
                    suggestions.append({
                        "file": rel,
                        "type": "missing_class_docs",
                        "priority": "high",
                        "suggestion": "Add docstrings to all classes"
                    })
                
                if not has_func_docs:
                    suggestions.append({
                        "file": rel,
                        "type": "missing_func_docs",
                        "priority": "medium",
                        "suggestion": "Add docstrings to all functions"
                    })
                
                if not has_type_hints:
                    suggestions.append({
                        "file": rel,
                        "type": "missing_type_hints",
                        "priority": "medium",
                        "suggestion": "Add type hints to function signatures"
                    })
                
                if not has_exports:
                    suggestions.append({
                        "file": rel,
                        "type": "missing_exports",
                        "priority": "low",
                        "suggestion": "Define __all__ to explicitly export public API"
                    })
                    
            except Exception as e:
                suggestions.append({"file": rel, "error": str(e)})
        
        return {
            "ok": True,
            "tool": "aicarmine_api_documentation_readme_suggestions",
            "path": target_path,
            "total_suggestions": len(suggestions),
            "suggestions": suggestions[:50],
            "priority_summary": {
                "high": len([s for s in suggestions if s.get("priority") == "high"]),
                "medium": len([s for s in suggestions if s.get("priority") == "medium"]),
                "low": len([s for s in suggestions if s.get("priority") == "low"])
            }
        }
    
    def documentation_quality_score(args: dict[str, Any], root):
        """Calculate overall documentation quality score."""
        target_path = args.get("path", ".")
        full_target = Path(root) / target_path
        
        if not full_target.exists():
            return {"ok": False, "error": f"path_not_found: {target_path}"}
        
        import re
        
        candidates = [full_target] if full_target.is_file() else list(full_target.rglob("*.py"))
        
        total_functions = 0
        documented_functions = 0
        total_classes = 0
        documented_classes = 0
        total_modules = 0
        documented_modules = 0
        
        for pyfile in candidates:
            rel = str(pyfile.relative_to(root))
            
            try:
                with open(pyfile, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                
                # Count functions
                funcs = re.findall(r'def\s+\w+', content)
                doc_funcs = re.findall(r'def\s+\w+.*"""', content)
                total_functions += len(funcs)
                documented_functions += len(doc_funcs)
                
                # Count classes
                cls = re.findall(r'class\s+\w+', content)
                doc_cls = re.findall(r'class\s+\w+.*"""', content)
                total_classes += len(cls)
                documented_classes += len(doc_cls)
                
                # Module docstring
                total_modules += 1
                if '"""' in content[:500] or "'''" in content[:500]:
                    documented_modules += 1
            except Exception as e:
                pass
        
        # Calculate score (weighted)
        func_score = documented_functions / max(total_functions, 1) * 40
        class_score = documented_classes / max(total_classes, 1) * 30
        module_score = documented_modules / max(total_modules, 1) * 30
        
        overall = func_score + class_score + module_score
        
        return {
            "ok": True,
            "tool": "aicarmine_api_documentation_quality",
            "path": target_path,
            "score": round(overall, 2),
            "function_coverage": round(documented_functions / max(total_functions, 1) * 100, 2),
            "class_coverage": round(documented_classes / max(total_classes, 1) * 100, 2),
            "module_coverage": round(documented_modules / max(total_modules, 1) * 100, 2),
            "rating": "excellent" if overall > 80 else "good" if overall > 60 else "needs_improvement"
        }
    
    tools: dict[str, ToolSpec] = {}
    
    tools["aicarmine_api_documentation_health"] = ToolSpec(
        name="aicarmine_api_documentation_health",
        description="Report API documentation server health and capabilities.",
        input_schema=object_schema(),
        handler=health,
    )
    
    tools["aicarmine_api_documentation_signatures"] = ToolSpec(
        name="aicarmine_api_documentation_signatures",
        description="Generate function signature documentation.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=generate_signature_doc,
    )
    
    tools["aicarmine_api_documentation_classes"] = ToolSpec(
        name="aicarmine_api_documentation_classes",
        description="Generate class documentation.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=generate_class_doc,
    )
    
    tools["aicarmine_api_documentation_modules"] = ToolSpec(
        name="aicarmine_api_documentation_modules",
        description="Generate module-level documentation.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=generate_module_doc,
    )
    
    tools["aicarmine_api_documentation_readme_suggestions"] = ToolSpec(
        name="aicarmine_api_documentation_readme_suggestions",
        description="Generate README/documentation suggestions.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=generate_readme_suggestions,
    )
    
    tools["aicarmine_api_documentation_quality"] = ToolSpec(
        name="aicarmine_api_documentation_quality",
        description="Calculate overall documentation quality score.",
        input_schema=object_schema({
            "path": string_prop("."),
        }),
        handler=documentation_quality_score,
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
            health_tool="aicarmine_api_documentation_health",
            real_tool="aicarmine_api_documentation_signatures",
            real_args={"path": "services/codex_bridge/repo_mcp_common.py"},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())