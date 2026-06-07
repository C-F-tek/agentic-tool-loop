from __future__ import annotations

import ast
import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TARGET_ROOT = ROOT / "services"

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "openwebui-data"}
MAX_FILE_BYTES = 2_000_000

PAYLOAD_ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    ("tool_context_for_30b", "agent_context_for_30b", "structured_context_for_30b", "structured_result_for_30b", "tool_result_for_30b"),
    ("evidence_guide_for_30b", "answer_for_30b", "message_for_30b", "summary_for_30b"),
    ("payload_index_for_30b", "result_index_for_30b"),
    ("priority_evidence_for_30b", "priority_payload_for_30b"),
    ("status", "job_status"),
    ("tool_name", "tool_result_for", "called_by_30b"),
    ("owner", "target_owner", "source_owner", "public_owner", "payload_owner", "materialization_owner"),
    ("source", "source_owner", "source_tool", "source_path"),
)

DROP_ALIAS_KEYS = {
    alias
    for group in PAYLOAD_ALIAS_GROUPS
    for alias in group[1:]
}


@dataclass(frozen=True)
class Removal:
    path: Path
    start: int
    end: int
    reason: str
    detail: str


class Normalizer(ast.NodeTransformer):
    def visit_Name(self, node: ast.Name) -> ast.AST:
        node = copy.copy(node)
        node.id = "_name"
        return node

    def visit_arg(self, node: ast.arg) -> ast.AST:
        node = copy.copy(node)
        node.arg = "_arg"
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        node = copy.copy(node)
        if isinstance(node.value, str):
            node.value = "_str"
        elif isinstance(node.value, (int, float, complex)):
            node.value = 0
        return node

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        node = self.generic_visit(copy.copy(node))
        node.attr = "_attr"
        return node


def target_files() -> list[Path]:
    files: list[Path] = []
    for path in TARGET_ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        files.append(path)
    return sorted(files)


def literal_key(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def node_range(node: ast.AST) -> tuple[int, int] | None:
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None)
    if not isinstance(start, int) or not isinstance(end, int):
        return None
    return start, end


def dict_field_removals(path: Path, tree: ast.AST) -> list[Removal]:
    removals: list[Removal] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = [literal_key(key) for key in node.keys]
        present = {key for key in keys if key}
        last_index: dict[str, int] = {}
        for index, key in enumerate(keys):
            if key is not None:
                last_index[key] = index
        aliases_to_drop = set()
        for group in PAYLOAD_ALIAS_GROUPS:
            primary = group[0]
            if primary in present:
                aliases_to_drop.update(key for key in group[1:] if key in present)
        for index, (key_node, value_node, key) in enumerate(zip(node.keys, node.values, keys)):
            if key is None:
                continue
            reason = ""
            detail = key
            if last_index.get(key) != index:
                reason = "duplicate_payload_key"
            elif key in aliases_to_drop or key in DROP_ALIAS_KEYS:
                reason = "similar_payload_alias"
            if not reason:
                continue
            source_node = key_node if key_node is not None else value_node
            span = node_range(source_node)
            value_span = node_range(value_node)
            if not span:
                continue
            start = span[0]
            end = value_span[1] if value_span else span[1]
            removals.append(Removal(path, start, end, reason, detail))
    return removals


def function_key(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    body = copy.deepcopy(node.body)
    normalizer = Normalizer()
    normalized = [normalizer.visit(item) for item in body]
    dump = ast.dump(
        ast.Module(body=normalized, type_ignores=[]),
        annotate_fields=True,
        include_attributes=False,
    )
    return hashlib.sha256(dump.encode("utf-8", errors="replace")).hexdigest()


def function_removals(parsed: list[tuple[Path, ast.AST]]) -> list[Removal]:
    all_seen: dict[str, list[tuple[Path, ast.FunctionDef | ast.AsyncFunctionDef]]] = {}
    removals: list[Removal] = []
    for path, tree in parsed:
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            span = node_range(node)
            if not span:
                continue
            if span[1] - span[0] < 4:
                continue
            key = function_key(node)
            all_seen.setdefault(key, []).append((path, node))
    for items in all_seen.values():
        if len(items) < 2:
            continue
        keep_path, keep_node = items[-1]
        for path, node in items[:-1]:
            span = node_range(node)
            if not span:
                continue
            removals.append(Removal(
                path,
                span[0],
                span[1],
                "duplicate_or_similar_function_body",
                f"{node.name} duplicates {keep_path.relative_to(ROOT)}:{keep_node.name}",
            ))
    return removals


def apply_removals(path: Path, removals: list[Removal]) -> int:
    if not removals:
        return 0
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    removed = 0
    for removal in sorted(removals, key=lambda item: item.start, reverse=True):
        start = max(removal.start - 1, 0)
        end = min(removal.end, len(lines))
        while end < len(lines) and lines[end].strip() == "":
            end += 1
            break
        del lines[start:end]
        removed += 1
    path.write_text("".join(lines), encoding="utf-8", newline="")
    return removed


def main() -> int:
    parsed: list[tuple[Path, ast.AST]] = []
    parse_failures: list[dict[str, str]] = []
    removals: list[Removal] = []
    for path in target_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as exc:
            parse_failures.append({"path": str(path.relative_to(ROOT)), "error": str(exc)})
            continue
        parsed.append((path, tree))
        removals.extend(dict_field_removals(path, tree))
    removals.extend(function_removals(parsed))

    by_path: dict[Path, list[Removal]] = {}
    for removal in removals:
        by_path.setdefault(removal.path, []).append(removal)

    changed: list[dict[str, Any]] = []
    for path, path_removals in sorted(by_path.items()):
        count = apply_removals(path, path_removals)
        if count:
            changed.append({
                "path": str(path.relative_to(ROOT)),
                "removed": count,
                "items": [
                    {
                        "start": item.start,
                        "end": item.end,
                        "reason": item.reason,
                        "detail": item.detail,
                    }
                    for item in path_removals
                ],
            })

    print(json.dumps({
        "schema": "mechanical_services_dedupe_report.v1",
        "mode": "apply",
        "target_root": str(TARGET_ROOT),
        "files_parsed": len(parsed),
        "parse_failures": parse_failures,
        "files_changed": len(changed),
        "changed": changed,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
