#!/usr/bin/env python3
"""MCP server for configuration validation.

Validates configuration files, checks consistency, audits environment
variables, and provides migration helpers for config changes.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import tomllib
from pathlib import Path
from typing import Any

# Add codex_bridge to sys.path for repo_mcp_common import
try:
    _codex_bridge_dir = Path(__file__).resolve().parent
except NameError:
    _codex_bridge_dir = Path("services/codex_bridge").resolve()
if str(_codex_bridge_dir) not in sys.path:
    sys.path.insert(0, str(_codex_bridge_dir))

from repo_mcp_common import (
    ToolSpec,
    health_payload,
    object_schema,
    serve,
)

SERVER_NAME = "aicarmine-config-validator-mcp"
SERVER_VERSION = "1.0.0"


class ConfigValidator:
    """Validates configuration across the repository."""

    def __init__(self, repo_root: str) -> None:
        self.repo_root = Path(repo_root)
        self._lock = threading.Lock()

    CONFIG_EXTENSIONS = ['.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.env', '.conf']

    def _find_config_files(self, path: str | None = None) -> list[Path]:
        """Find all configuration files."""
        target = self.repo_root / path if path else self.repo_root
        if not target.exists():
            return []
        configs = []
        for ext in self.CONFIG_EXTENSIONS:
            configs.extend(target.rglob(f"*{ext}"))
        return sorted(set(configs), key=lambda p: p.relative_to(self.repo_root))

    def _parse_json_file(self, filepath: Path) -> tuple[dict[str, Any] | None, str | None]:
        """Parse a JSON file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data, None
        except Exception as e:
            return None, str(e)

    def _parse_yaml_file(self, filepath: Path) -> tuple[dict[str, Any] | None, str | None]:
        """Parse a YAML file using basic text parsing (no yaml module dependency)."""
        try:
            # Simple YAML parser for basic key-value structures
            content = filepath.read_text(encoding='utf-8')
            result = {}
            current_key = None
            for line in content.split('\n'):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if ':' in line:
                    key, _, value = line.partition(':')
                    key = key.strip()
                    value = value.strip()
                    if value:
                        try:
                            result[key] = int(value)
                        except ValueError:
                            try:
                                result[key] = float(value)
                            except ValueError:
                                result[key] = value
            return result, None
        except Exception as e:
            return None, str(e)

    def _parse_toml_file(self, filepath: Path) -> tuple[dict[str, Any] | None, str | None]:
        """Parse a TOML file."""
        try:
            with open(filepath, 'rb') as f:
                data = tomllib.load(f)
            return data, None
        except Exception as e:
            return None, str(e)

    def _parse_ini_file(self, filepath: Path) -> tuple[dict[str, dict[str, str]] | None, str | None]:
        """Parse an INI file."""
        try:
            import configparser
            config = configparser.ConfigParser()
            config.read(str(filepath))
            sections = {s: dict(config[s]) for s in config.sections()}
            return sections, None
        except Exception as e:
            return None, str(e)

    def validate(self, path: str = ".", config_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        """Validate configuration files."""
        config_files = self._find_config_files(path)
        results: list[dict[str, Any]] = []
        valid_count = 0
        invalid_count = 0

        for cf in config_files:
            ext = cf.suffix.lower()
            data, error = None, None

            if ext == '.json':
                data, error = self._parse_json_file(cf)
            elif ext in ('.yaml', '.yml'):
                data, error = self._parse_yaml_file(cf)
            elif ext == '.toml':
                data, error = self._parse_toml_file(cf)
            elif ext in ('.ini', '.cfg'):
                data, error = self._parse_ini_file(cf)
            else:
                # Try JSON as fallback
                data, error = self._parse_json_file(cf)

            results.append({
                "file": str(cf.relative_to(self.repo_root)),
                "format": ext.lstrip('.'),
                "valid": error is None,
                "error": error,
                "size_bytes": cf.stat().st_size
            })

            if error is None:
                valid_count += 1
            else:
                invalid_count += 1

        return {
            "ok": True,
            "path": path,
            "config_files_found": len(config_files),
            "valid_count": valid_count,
            "invalid_count": invalid_count,
            "results": results[:200]
        }

    def consistency_check(self, path: str = ".") -> dict[str, Any]:
        """Check for configuration inconsistencies."""
        config_files = self._find_config_files(path)
        issues: list[dict[str, Any]] = []

        # Collect all keys across config files
        all_keys: dict[str, set[str]] = {}
        key_values: dict[str, list[dict[str, Any]]] = {}

        for cf in config_files:
            ext = cf.suffix.lower()
            data, error = None, None

            if ext == '.json':
                data, error = self._parse_json_file(cf)
            elif ext in ('.yaml', '.yml'):
                data, error = self._parse_yaml_file(cf)
            elif ext == '.toml':
                data, error = self._parse_toml_file(cf)

            if data and isinstance(data, dict):
                file_keys = set()
                self._flatten_keys(data, file_keys, key_values, str(cf.relative_to(self.repo_root)))

                all_keys[str(cf.relative_to(self.repo_root))] = file_keys

        # Check for overlapping keys with different values
        for key, occurrences in key_values.items():
            if len(occurrences) > 1:
                values = [o.get('value') for o in occurrences if o.get('value') is not None]
                if len(set(str(v) for v in values)) > 1:
                    issues.append({
                        "type": "conflicting_values",
                        "key": key,
                        "occurrences": occurrences,
                        "severity": "high"
                    })

        # Check for orphan references
        for cf in config_files:
            try:
                content = cf.read_text(encoding='utf-8')
                # Check for ${} or {{}} references to non-existent keys
                import re
                refs = re.findall(r'\$\{([^}]+)\}', content) or re.findall(r'\{\{([^}]+)\}\}', content)
                for ref in refs:
                    if ref not in str(all_keys):
                        issues.append({
                            "type": "orphan_reference",
                            "reference": ref,
                            "file": str(cf.relative_to(self.repo_root)),
                            "severity": "medium"
                        })
            except Exception:
                continue

        return {
            "ok": True,
            "path": path,
            "config_files_checked": len(config_files),
            "issues_count": len(issues),
            "issues": issues[:100]
        }

    def _flatten_keys(self, data: dict[str, Any], keys: set[str], all_keys: dict[str, list[dict[str, Any]]], file_path: str) -> None:
        """Flatten nested dict keys."""
        for k, v in data.items():
            keys.add(k)
            if isinstance(v, dict):
                self._flatten_keys(v, keys, all_keys, file_path)
            else:
                if k not in all_keys:
                    all_keys[k] = []
                all_keys[k].append({"file": file_path, "value": v})

    def env_audit(self) -> dict[str, Any]:
        """Audit environment variables."""
        vars_list = []
        issues: list[dict[str, Any]] = []

        for key, value in os.environ.items():
            is_sensitive = any(s in key.lower() for s in ['password', 'secret', 'token', 'api_key', 'key', 'credential'])
            vars_list.append({
                "name": key,
                "length": len(value),
                "is_sensitive": is_sensitive,
                "is_set": bool(value)
            })

            # Check for empty sensitive variables
            if is_sensitive and not value:
                issues.append({
                    "type": "empty_sensitive_var",
                    "var": key,
                    "severity": "high"
                })

            # Check for hardcoded values in env vars
            if is_sensitive and value and len(value) > 8:
                issues.append({
                    "type": "potential_hardcoded_secret",
                    "var": key,
                    "severity": "medium"
                })

        return {
            "ok": True,
            "total_vars": len(vars_list),
            "sensitive_count": len([v for v in vars_list if v["is_sensitive"]]),
            "set_count": len([v for v in vars_list if v["is_set"]]),
            "variables": vars_list[:100],
            "issues": issues[:50]
        }

    def migration_helper(self, old_config: str, new_config: dict[str, Any]) -> dict[str, Any]:
        """Generate migration suggestions."""
        old_keys = set()
        self._flatten_keys(old_config if isinstance(old_config, dict) else {}, old_keys, {}, "")
        
        new_keys = set(new_config.keys()) if isinstance(new_config, dict) else set()
        
        added = new_keys - old_keys
        removed = old_keys - new_keys
        common = old_keys & new_keys

        suggestions = []
        for k in added:
            suggestions.append({"action": "add", "key": k, "value": new_config.get(k)})
        for k in removed:
            suggestions.append({"action": "remove", "key": k})
        for k in common:
            if old_config.get(k) != new_config.get(k):
                suggestions.append({
                    "action": "update",
                    "key": k,
                    "old_value": old_config.get(k),
                    "new_value": new_config.get(k)
                })

        return {
            "ok": True,
            "added_keys": len(added),
            "removed_keys": len(removed),
            "changed_keys": len([s for s in suggestions if s["action"] == "update"]),
            "suggestions": suggestions[:100]
        }


# ---------------------------------------------------------------------------
# MCP Server Setup
# ---------------------------------------------------------------------------

_validator: ConfigValidator | None = None

def _get_validator(repo_root: str) -> ConfigValidator:
    global _validator
    if _validator is None:
        _validator = ConfigValidator(repo_root)
    return _validator


def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    def health(args: dict[str, Any], root):
        return health_payload(SERVER_NAME, list(tools))

    tools["aicarmine_config_validate"] = ToolSpec(
        name="aicarmine_config_validate",
        description="Validate configuration files",
        input_schema=object_schema({
            "path": {"type": "string"},
            "config_schema": {"type": "object"}
        }),
        handler=lambda args, root: _get_validator(str(root)).validate(
            path=args.get("path", "."),
            config_schema=args.get("config_schema")
        ),
    )

    tools["aicarmine_config_consistency_check"] = ToolSpec(
        name="aicarmine_config_consistency_check",
        description="Check for configuration inconsistencies",
        input_schema=object_schema({
            "path": {"type": "string"}
        }),
        handler=lambda args, root: _get_validator(str(root)).consistency_check(
            path=args.get("path", ".")
        ),
    )

    tools["aicarmine_config_env_audit"] = ToolSpec(
        name="aicarmine_config_env_audit",
        description="Audit environment variables",
        input_schema=object_schema(),
        handler=lambda args, root: _get_validator(str(root)).env_audit(),
    )

    tools["aicarmine_config_migration_helper"] = ToolSpec(
        name="aicarmine_config_migration_helper",
        description="Generate migration suggestions between configs",
        input_schema=object_schema({
            "old_config": {"type": "object"},
            "new_config": {"type": "object"}
        }),
        handler=lambda args, root: _get_validator(str(root)).migration_helper(
            old_config=args.get("old_config", {}),
            new_config=args.get("new_config", {})
        ),
    )

    return tools


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    return serve(SERVER_NAME, SERVER_VERSION, tools)


if __name__ == "__main__":
    raise SystemExit(main())