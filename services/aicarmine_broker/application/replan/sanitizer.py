"""Replan specialist result sanitizer."""

from __future__ import annotations

import json
from typing import Any


class ReplanPathExtractor:
    """Estrae percorsi noti dal contratto."""

    def extract_known_paths(self, contract: dict[str, Any]) -> set[str]:
        """Estrae tutti i percorsi noti dal contratto."""
        known: set[str] = set()
        for key in (
            "validator_admissible_repo_read_paths",
            "read_admissible_paths",
            "successful_repo_read_paths",
            "covered_owner_paths",
            "candidate_owner_paths",
            "missing_owner_paths",
        ):
            for item in self._path_items(contract.get(key)):
                token = self._repo_path_token(item)
                if token:
                    known.add(token)
        for item in self._path_items(contract.get("verified_content_reads")):
            token = self._repo_path_token(item)
            if token:
                known.add(token)
        final_contract = contract.get("finalization_contract") or {}
        coverage = final_contract.get("minimum_read_coverage") or contract.get("minimum_read_coverage") or {}
        for key in ("covered_owner_paths", "candidate_owner_paths", "missing_owner_paths"):
            for item in self._path_items(coverage.get(key)):
                token = self._repo_path_token(item)
                if token:
                    known.add(token)
        return known

    def extract_known_dirs(self, paths: set[str]) -> set[str]:
        """Estrae le directory note dai percorsi."""
        dirs: set[str] = { "." }
        for path in paths:
            parts = [part for part in path.split("/") if part]
            for index in range(1, len(parts)):
                dirs.add("/".join(parts[:index]))
        return dirs

    def is_prose_or_metric(self, token: str) -> bool:
        """Verifica se un token è prosa o metrica."""
        token = str(token or "").strip()
        if not token:
            return True
        lowered = token.lower()
        if lowered in {"ridondanze/rischi", "docs/config", "planner/final-quality", "planner/controller rejection paths"}:
            return True
        if any(sep in lowered for sep in (":\\", "://")):
            return True
        compact = lowered.replace("/", "").replace(".", "").replace("-", "").replace("_", "")
        if compact.isdigit() and "/" in lowered:
            return True
        if " " in token and not any(token.endswith(suffix) for suffix in (".py", ".md", ".json", ".toml", ".yaml", ".yml", ".txt")):
            return True
        return False

    def is_concrete_query(self, query: str) -> bool:
        """Verifica se una query è concreta."""
        text = str(query or "").strip()
        if not text:
            return False
        lowered = text.lower()
        if len(text) > 260:
            return False
        if self.is_prose_or_metric(text):
            return False
        if lowered in {"docs/config", "ridondanze/rischi", "8/2", "8/8", "9/9"}:
            return False
        useful_tokens = [
            token
            for token in lowered.replace(",", " ").replace(";", " ").split()
            if len(token) >= 3 and "/" not in token and any(ch.isalpha() for ch in token)
        ]
        if "/" in lowered and len(useful_tokens) < 2:
            return False
        return bool(useful_tokens)

    def _path_items(self, value: Any) -> list[Any]:
        if isinstance(value, dict):
            items = value.get("items")
            return items if isinstance(items, list) else []
        if isinstance(value, list):
            return value
        return []

    def _repo_path_token(self, value: Any) -> str:
        if isinstance(value, dict):
            value = value.get("path") or value.get("source_path") or ""
        token = str(value or "").strip().replace("\\", "/")
        while token.startswith("./"):
            token = token[2:]
        return token


class ReplanValidator:
    """Validatore per i risultati del replan specialist."""

    def validate_path(self, path: str, allowed_paths: set[str]) -> bool:
        """Valida un percorso contro la lista dei permessi."""
        return path in allowed_paths

    def validate_directory(self, path: str, known_dirs: set[str]) -> bool:
        """Valida una directory contro le directory note."""
        return path == "." or (path in known_dirs and not ReplanPathExtractor().is_prose_or_metric(path))

    def validate_query(self, query: str) -> bool:
        """Valida una query di ricerca."""
        return ReplanPathExtractor().is_concrete_query(query)


class ReplanSanitizer:
    """Sanitizza i risultati del replan specialist contro il contratto."""

    def __init__(self) -> None:
        self.path_extractor = ReplanPathExtractor()
        self.validator = ReplanValidator()

    def sanitize(self, result: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
        """Sanitizza il risultato contro il contratto."""
        if result.get("ok") is not True:
            return result

        required_call = result.get("required_next_tool_call") if isinstance(result.get("required_next_tool_call"), dict) else {}
        tool = self._normalize_tool_name(str(required_call.get("tool") or ""))
        if not tool:
            return result

        args = required_call.get("arguments") if isinstance(required_call.get("arguments"), dict) else {}
        known_paths = self.path_extractor.extract_known_paths(contract)
        known_dirs = self.path_extractor.extract_known_dirs(known_paths)

        if tool == "repo_read":
            return self._validate_repo_read(result, required_call, args, contract, known_paths)

        if tool == "repo_list_files":
            return self._validate_repo_list_files(result, required_call, args, known_dirs)

        if tool in {"repo_semantic_search", "repo_rg_search", "repo_search"}:
            return self._validate_search(result, required_call, args, known_dirs)

        if tool == "planner_scratchpad_read":
            return self._validate_scratchpad_read(result, required_call, args, known_paths)

        result["required_next_tool_call"] = {}
        result["required_next_tool_call_validated"] = False
        result["invalid_required_next_tool_call_reason"] = (
            "planner_replan_specialist proposed a route that has no deterministic validator proof"
        )
        return result

    def _validate_repo_read(
        self,
        result: dict[str, Any],
        required_call: dict[str, Any],
        args: dict[str, Any],
        contract: dict[str, Any],
        known_paths: set[str],
    ) -> dict[str, Any]:
        """Valida una chiamata repo_read."""
        allowed_paths = self._repo_read_allowlist(contract)
        raw_paths = self._required_repo_read_paths(args)

        valid_paths: list[str] = []
        invalid_paths: list[str] = []
        for raw_path in raw_paths:
            token = self.path_extractor._repo_path_token(raw_path)
            if token and token in allowed_paths:
                if token not in valid_paths:
                    valid_paths.append(token)
            elif token and token not in invalid_paths:
                invalid_paths.append(token)

        if invalid_paths:
            result["invalid_required_next_tool_call_paths"] = invalid_paths[:12]
            result["invalid_required_next_tool_call_reason"] = (
                "planner_replan_specialist proposed repo_read paths that are not "
                "known/admissible repo paths in the current evidence contract"
            )

        if valid_paths:
            required_call["arguments"] = {"paths": valid_paths[:12]}
            return self._mark_validated(result, required_call)

        result["required_next_tool_call"] = {}
        result["required_next_tool_call_validated"] = False
        result["decision"] = "block_recommended"
        result["required_next_progress"] = (
            "Replan specialist proposed no valid existing repo_read path. "
            "Do not call repo_read for prose, metrics, headings, or non-existing paths. "
            "Use verified evidence for a terminal answer if allowed, or return a typed block."
        )
        return result

    def _validate_repo_list_files(
        self,
        result: dict[str, Any],
        required_call: dict[str, Any],
        args: dict[str, Any],
        known_dirs: set[str],
    ) -> dict[str, Any]:
        """Valida una chiamata repo_list_files."""
        path_token = self.path_extractor._repo_path_token(args.get("path") or ".") or "."
        if path_token == "." or (path_token in known_dirs and not self.path_extractor.is_prose_or_metric(path_token)):
            args["path"] = path_token
            required_call["arguments"] = args
            return self._mark_validated(result, required_call)
        result["invalid_required_next_tool_call_paths"] = [path_token]
        result["invalid_required_next_tool_call_reason"] = (
            "planner_replan_specialist proposed repo_list_files path that is not "
            "a known concrete repo directory in the current evidence contract"
        )
        result["required_next_tool_call"] = {}
        result["required_next_tool_call_validated"] = False
        result["required_next_progress"] = (
            "Do not list files for prose, metrics, headings, or unknown path tokens. "
            "Use verified evidence for final/block, or provide a concrete search query."
        )
        return result

    def _validate_search(
        self,
        result: dict[str, Any],
        required_call: dict[str, Any],
        args: dict[str, Any],
        known_dirs: set[str],
    ) -> dict[str, Any]:
        """Valida una chiamata di ricerca."""
        query_value = args.get("query") or args.get("pattern") or args.get("symbol")
        if self.path_extractor.is_concrete_query(query_value):
            path_token = self.path_extractor._repo_path_token(args.get("path")) if args.get("path") else ""
            if path_token and path_token not in known_dirs and path_token not in known_dirs:
                result["invalid_required_next_tool_call_paths"] = [path_token]
                args.pop("path", None)
            required_call["arguments"] = args
            return self._mark_validated(result, required_call)
        result["invalid_required_next_tool_call_query"] = str(query_value or "").strip()[:260]
        result["invalid_required_next_tool_call_reason"] = (
            "planner_replan_specialist proposed a search query that looks like a "
            "heading, metric, violation label, or path token rather than a concrete query"
        )
        result["required_next_tool_call"] = {}
        result["required_next_tool_call_validated"] = False
        result["required_next_progress"] = (
            "Do not lock the next turn on a weak search query. Rewrite from verified "
            "evidence if possible, or provide a concrete semantic query in prose-free form."
        )
        return result

    def _validate_scratchpad_read(
        self,
        result: dict[str, Any],
        required_call: dict[str, Any],
        args: dict[str, Any],
        known_paths: set[str],
    ) -> dict[str, Any]:
        """Valida una chiamata planner_scratchpad_read."""
        document_id = str(args.get("document_id") or "").strip()
        target_file = self.path_extractor._repo_path_token(args.get("target_file")) if args.get("target_file") else ""
        section = str(args.get("section") or "").strip()
        if document_id and not self.path_extractor.is_prose_or_metric(document_id):
            return self._mark_validated(result, required_call)
        if target_file and target_file in known_paths:
            return self._mark_validated(result, required_call)
        result["invalid_required_next_tool_call_reason"] = (
            "planner_replan_specialist proposed planner_scratchpad_read without a "
            "known document_id or verified target_file"
        )
        if target_file:
            result["invalid_required_next_tool_call_paths"] = [target_file]
        elif section:
            result["invalid_required_next_tool_call_query"] = section[:260]
        result["required_next_tool_call"] = {}
        result["required_next_tool_call_validated"] = False
        result["required_next_progress"] = (
            "Do not lock rewrite recovery on an unverified scratchpad selector. "
            "Use verified evidence for final/block, or request a concrete known window."
        )
        return result

    def _mark_validated(self, result: dict[str, Any], required_call: dict[str, Any]) -> dict[str, Any]:
        """Marca il required_call come validato."""
        required_call["validated"] = True
        required_call["validation_source"] = "planner_replan_specialist_sanitizer"
        result["required_next_tool_call"] = required_call
        result["required_next_tool_call_validated"] = True
        result["required_next_tool_call_validation_source"] = "planner_replan_specialist_sanitizer"
        return result

    def _normalize_tool_name(self, tool: str) -> str:
        """Normalizza il nome del tool."""
        mapping = {
            "repo_read": "repo_read",
            "repo_list_files": "repo_list_files",
            "repo_semantic_search": "repo_semantic_search",
            "repo_rg_search": "repo_rg_search",
            "repo_search": "repo_search",
            "planner_scratchpad_read": "planner_scratchpad_read",
        }
        return mapping.get(tool.lower().strip(), "")

    def _repo_read_allowlist(self, contract: dict[str, Any]) -> set[str]:
        """Estrae la lista dei percorsi permessi per repo_read."""
        allowed: set[str] = set()
        completed: set[str] = set()
        for key in ("validator_admissible_repo_read_paths", "read_admissible_paths"):
            for item in self._path_items(contract.get(key)):
                token = self.path_extractor._repo_path_token(item)
                if token:
                    allowed.add(token)
        for key in ("successful_repo_read_paths", "verified_content_reads"):
            for item in self._path_items(contract.get(key)):
                token = self.path_extractor._repo_path_token(item)
                if token:
                    completed.add(token)
        for row in self._path_items(contract.get("stale_required_next_tool_calls")):
            if not isinstance(row, dict):
                continue
            args = row.get("arguments") if isinstance(row.get("arguments"), dict) else {}
            for item in (args.get("paths", []) if isinstance(args.get("paths"), list) else [args.get("path")]):
                token = self.path_extractor._repo_path_token(item)
                if token:
                    completed.add(token)
        return allowed - completed

    def _required_repo_read_paths(self, args: dict[str, Any]) -> list[Any]:
        """Estrae i percorsi richiesti da repo_read."""
        out: list[Any] = []
        if not isinstance(args, dict):
            return out
        if args.get("path") not in (None, "", [], {}):
            out.append(args.get("path"))
        raw_paths = args.get("paths")
        if isinstance(raw_paths, list):
            out.extend(raw_paths)
        return out