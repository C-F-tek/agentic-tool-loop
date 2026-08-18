# API Documentation MCP Server - Complete Guide

## Overview

`services\codex_bridge\api_documentation_mcp_server.py` implements the **aicarmine-api-documentation** MCP server, providing automated API documentation generation for Python codebases. It scans source files and generates function signatures, class hierarchies, module-level documentation, README suggestions, and quality scores.

## Architecture

### Runtime Boundary

- **Server Name**: `aicarmine-api-documentation`
- **Version**: 1.0.0
- **Type**: Read-only MCP tool for static code analysis
- **Integration**: Part of codex_bridge MCP server inventory

### Component Map

| Tool | Description | Input | Output |
| --- | --- | --- | --- |
| `aicarmine_api_documentation_health` | Health check and capabilities report | Empty object | Server name, version, tool list |
| `aicarmine_api_documentation_signatures` | Generate function signature documentation | path (str) | Functions with params, return types, docstring coverage |
| `aicarmine_api_documentation_classes` | Generate class documentation | path (str) | Classes with bases, methods, inheritance hierarchy |
| `aicarmine_api_documentation_modules` | Generate module-level documentation | path (str) | Modules with exports, imports, quality score |
| `aicarmine_api_documentation_readme_suggestions` | README/documentation suggestions | path (str) | Priority-ranked suggestions for missing docs |
| `aicarmine_api_documentation_quality` | Overall documentation quality score | path (str) | Weighted score (func:40%, class:30%, module:30%) |

## Operational Rules

### 1. Static Analysis Only

- No code execution or modification
- Pure regex-based parsing of Python source files
- Read-only operation; does not write to repository
- Works on `.py` files recursively under target path

### 2. Path Resolution

- `path` parameter defaults to `.` (current directory)
- Resolved as `Path(root) / target_path` where root is the repo root
- Supports both single file and recursive directory scanning

### 3. Quality Scoring Algorithm

```
Overall Score = func_coverage * 40 + class_coverage * 30 + module_coverage * 30
```

**Ratings:**
- **Excellent**: score > 80
- **Good**: score > 60
- **Needs improvement**: score <= 60

### 4. Function Signature Detection

The server parses:
- Function definitions with parameter extraction
- Type hints (including nested types like `List[Optional[str]]`)
- Default values in signatures
- Return type annotations
- Docstring presence detection

### 5. Class Hierarchy Detection

The server extracts:
- Class names and base classes
- Inheritance chains
- Public/private/dunder method classification
- Docstring presence for classes and methods

## Tool Usage Examples

### Check Health
```json
{
  "tool": "aicarmine_api_documentation_health",
  "arguments": {}
}
```

### Generate Function Signatures
```json
{
  "tool": "aicarmine_api_documentation_signatures",
  "arguments": {
    "path": "services/aicarmine_broker/application/evidence"
  }
}
```

### Calculate Quality Score
```json
{
  "tool": "aicarmine_api_documentation_quality",
  "arguments": {
    "path": "."
  }
}
```

## Safety Boundaries

### What API Documentation Server Does NOT Do

- Does not modify source code or add docstrings automatically
- Does not execute Python code; only reads and parses
- Does not affect runtime services or broker operations
- Does not integrate with live documentation generators (e.g., Sphinx, MkDocs)

### Limitations

- Regex-based parsing may miss complex type hints or multi-line signatures
- Does not understand semantic meaning of functions/classes
- Quality scores are heuristic; human review required for accuracy
- External imports filtering is based on a hardcoded list of standard library modules

## Troubleshooting

### Common Issues

1. **Path Not Found**: Verify the target path exists and is accessible:
   ```powershell
   Test-Path "services/aicarmine_broker"
   ```

2. **Low Quality Score**: Review suggestions from `readme_suggestions` tool to identify missing docstrings, type hints, or exports.

3. **Missing Functions in Output**: Check if functions are at module level (not nested) and have standard Python signatures.

### Diagnostic Flow

```
Documentation gap → Read quality score → Review suggestions → Apply recommendations manually
```

## Integration with Documentation Index

This MCP server is referenced in:
- [DOCUMENTATION_INDEX.md](../../DOCUMENTATION_INDEX.md) - Section 1.2 Codex Bridge (MCP Servers)
- [MCP_SERVERS_GUIDE.md](./MCP_SERVERS_GUIDE.md) - Complete MCP inventory