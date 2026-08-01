from __future__ import annotations

from services.aicarmine_broker.error_handling import (
    BrokerError,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

from pathlib import Path
from typing import Any
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 compatibility
    tomllib = None  # type: ignore[assignment]

from aicarmine_broker.config import COMMAND_TIMEOUT_SECONDS
from aicarmine_broker.config import LAB_REPO
from aicarmine_broker.config.env_loader import env_str
from aicarmine_broker.job_store import now, write_json
from aicarmine_broker.application.command import evaluate_command_execution_policy
from aicarmine_broker.tools.command_safety import classify_command
from aicarmine_broker.tools.powershell_runner import run_ps


def _repo_bounded_int_arg(args: dict[str, Any], names: str | tuple[str, ...], *, default: int, minimum: int, maximum: int) -> int:
    """Helper locale per parsing bounded int senza dipendenze circolari."""
    keys = (names,) if isinstance(names, str) else names
    selected: Any = None
    for key in keys:
        value = args.get(key)
        if value is not None and str(value).strip() != "":
            selected = value
            break
    if selected is None:
        selected = default
    try:
        parsed = int(selected)
    except (TypeError, ValueError, OverflowError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _repo_relative_existing_path(root: Path, value: str) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        return ""
    candidate = (root / raw).resolve(strict=False)
    root_resolved = root.resolve(strict=False)
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        return ""
    return raw if candidate.exists() else ""


def _repo_relative_compile_target(root: Path, value: str) -> str:
    rel = _repo_relative_existing_path(root, value)
    if not rel:
        return ""
    candidate = (root / rel).resolve(strict=False)
    if candidate.is_file():
        parent = candidate.parent
        while parent != root.resolve(strict=False):
            if (parent / "__init__.py").exists():
                return str(parent.relative_to(root.resolve(strict=False))).replace("\\", "/")
            parent = parent.parent
        return rel
    return rel


def _split_targets(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    return [item.strip() for item in text.replace(";", ",").split(",") if item.strip()]


def _history_compile_paths(history: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for key in ("path", "paths", "target", "targets", "successful_paths", "read_paths", "modified_paths"):
                for item in _split_targets(value.get(key)):
                    paths.append(item)
            for key in ("arguments", "tool_result", "result", "artifact", "items"):
                collect(value.get(key))
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(history)
    return paths


def _pyproject_compile_targets(root: Path, pyproject: Path) -> tuple[str, ...]:
    targets: list[str] = []

    def add_existing_package(rel: str) -> None:
        raw = str(rel or "").strip().replace("\\", "/").strip("/")
        if not raw:
            return
        candidate = root / raw
        if candidate.is_dir() and (candidate / "__init__.py").exists():
            targets.append(raw)

    data: dict[str, Any] = {}
    if tomllib is not None:
        try:
            loaded = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = {}

    setuptools = data.get("tool", {}).get("setuptools", {}) if data else {}
    if isinstance(setuptools, dict):
        package_dir = setuptools.get("package-dir", {})
        root_prefix = ""
        if isinstance(package_dir, dict):
            root_prefix = str(package_dir.get("") or "").strip().replace("\\", "/").strip("/")

        packages = setuptools.get("packages")
        if isinstance(packages, list):
            for package in packages:
                package_rel = str(package or "").strip().replace(".", "/")
                add_existing_package("/".join(item for item in (root_prefix, package_rel) if item))
        elif isinstance(packages, dict):
            finder = packages.get("find", {})
            if isinstance(finder, dict):
                where_values = finder.get("where") or ["."]
                for where in _split_targets(where_values):
                    search_root = root / where
                    if not search_root.exists() or not search_root.is_dir():
                        continue
                    for path in search_root.iterdir():
                        if path.is_dir() and (path / "__init__.py").exists():
                            targets.append(str(path.relative_to(root)).replace("\\", "/"))

    if not targets:
        package_targets = [
            str(path.relative_to(root)).replace("\\", "/")
            for path in root.iterdir()
            if path.is_dir() and (path / "__init__.py").exists()
        ]
        src_root = root / "src"
        if src_root.exists() and src_root.is_dir():
            package_targets.extend(
                str(path.relative_to(root)).replace("\\", "/")
                for path in src_root.iterdir()
                if path.is_dir() and (path / "__init__.py").exists()
            )
        targets.extend(package_targets)

    return tuple(dict.fromkeys(targets))


def resolve_compile_targets(
    args: dict[str, Any],
    root: Path,
    *,
    history: list[dict[str, Any]] | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence_paths: list[str] = []
    for source in (evidence or {}, {"history": history or []}):
        for key in ("core_paths", "paths", "successful_paths", "read_paths", "modified_paths"):
            for item in _split_targets(source.get(key) if isinstance(source, dict) else ""):
                rel = _repo_relative_compile_target(root, item)
                if rel:
                    evidence_paths.append(rel)
    for item in _history_compile_paths(history or []):
        rel = _repo_relative_compile_target(root, item)
        if rel:
            evidence_paths.append(rel)
    if evidence_paths:
        return {
            "targets": tuple(dict.fromkeys(evidence_paths)),
            "source": "core_project_evidence",
            "confidence": "high",
            "reason": "Core runtime modules observed in repo evidence.",
            "errors": (),
        }
    explicit: list[str] = []
    for key in ("path", "paths", "target", "targets"):
        for item in _split_targets(args.get(key)):
            rel = _repo_relative_existing_path(root, item)
            if rel:
                explicit.append(rel)
    if explicit:
        return {
            "targets": tuple(dict.fromkeys(explicit)),
            "source": "explicit_path",
            "confidence": "high",
            "reason": "Explicit compile target path was provided.",
            "errors": (),
        }
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        package_targets = _pyproject_compile_targets(root, pyproject)
        if package_targets:
            return {
                "targets": package_targets,
                "source": "pyproject",
                "confidence": "medium",
                "reason": "pyproject.toml exists and package targets were detected.",
                "errors": (),
            }
    configured = [
        _repo_relative_existing_path(root, item)
        for item in _split_targets(env_str("AICARMINE_COMPILE_TARGETS", ""))
    ]
    configured = [item for item in configured if item]
    if configured:
        return {
            "targets": tuple(dict.fromkeys(configured)),
            "source": "configured_targets",
            "confidence": "medium",
            "reason": "AICARMINE_COMPILE_TARGETS provided compile targets.",
            "errors": (),
        }
    core_candidates = [
        "services/aicarmine_broker",
        "services/vulkan_bridge",
    ]
    core_existing = [
        item for item in core_candidates
        if (root / item).exists()
    ]
    if core_existing:
        return {
            "targets": tuple(core_existing),
            "source": "configured_core_services",
            "confidence": "medium",
            "reason": "Known core service directories exist in the repository layout.",
            "errors": (),
        }
    return {
        "targets": (),
        "source": "none",
        "confidence": "none",
        "reason": "No compile target resolved from evidence, pyproject, explicit path or config.",
        "errors": ("compile_targets_not_resolved",),
    }


def _compile_command_for_targets(targets: tuple[str, ...]) -> str:
    parts: list[str] = []
    for target in targets:
        quoted = target.replace("'", "''")
        parts.append(f"python -m compileall -q '{quoted}'")
    return "; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; ".join(parts)


def _has_explicit_consent(user_consent: str) -> bool:
    consent = str(user_consent or "").lower()
    return "confirm" in consent or "confermo" in consent


def repo_command(
    args: dict[str, Any],
    root: Path,
    allow_command: bool,
    user_consent: str,
) -> dict[str, Any]:
    if not allow_command:
        return {"ok": False, "tool": "repo_command", "error": "commands disabled by request"}

    command = str(args.get("command") or "").strip()
    try:
        timeout = _repo_bounded_int_arg(args, ("timeout_seconds", "timeout"), default=COMMAND_TIMEOUT_SECONDS, minimum=1, maximum=3600)
    except Exception as _e:
        raise BrokerError(
            message=f"Error in {__name__}:
            error_type=type(_e).__name__,
            error_message=str(_e),
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.HIGH,
        )
        return {"ok": False, "tool": "repo_command", "error": str(exc), "error_type": type(exc).__name__}

    if not command:
        return {"ok": False, "tool": "repo_command", "error": "missing command"}

    target_resolution: dict[str, Any] | None = None
    if command.lower() in {"compile", "build", "compila"}:
        target_resolution = resolve_compile_targets(args, root)
        targets = tuple(target_resolution.get("targets") or ())
        if not targets:
            return {
                "ok": False,
                "tool": "repo_command",
                "error": "compile_targets_not_resolved",
                "next_action": "Run repo_tree/repo_list_files first or pass explicit path/targets.",
                "target_resolution": target_resolution,
            }
        command = _compile_command_for_targets(targets)

    classification = classify_command(command)
    execution_policy = evaluate_command_execution_policy(
        command,
        command_class=classification.command_class,
        cwd=LAB_REPO,
        repo_root=LAB_REPO,
        approval_mode=str(args.get("approval_mode") or ""),
        user_consent=user_consent,
    )
    if classification.consent_required and not _has_explicit_consent(user_consent):
        return {
            "ok": False,
            "tool": "repo_command",
            "needs_consent": True,
            "command": command,
            "error": "command_requires_consent",
            "command_class": classification.command_class,
            "required_consent": "confirm command execution",
            "policy": classification.reason,
            "command_execution_policy": execution_policy,
        }

    result = run_ps(command, timeout=timeout)
    artifact = root / "commands" / f"command-{now()}.json"
    payload = {
        "ok": result["returncode"] == 0,
        "tool": "repo_command",
        "command": command,
        "command_class": classification.command_class,
        "consent_required": classification.consent_required,
        "policy": classification.reason,
        "command_execution_policy": execution_policy,
        "returncode": result["returncode"],
        "stdout_tail": result["stdout_tail"],
        "stderr_tail": result["stderr_tail"],
        "artifact": str(artifact),
    }
    if target_resolution is not None:
        payload["target_resolution"] = target_resolution
    write_json(artifact, {"command": command, "classification": classification.__dict__, "result": result})
    return payload
