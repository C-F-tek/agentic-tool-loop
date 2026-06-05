from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


DOC_ROOTS = (
    ROOT / "README.md",
    ROOT / "AGENTS.md",
    ROOT / "docs",
    ROOT / "services",
    ROOT / "codex_ollama_bridge_applied",
)


def _markdown_files() -> list[Path]:
    files: list[Path] = []
    for root in DOC_ROOTS:
        if root.is_file() and root.suffix.lower() == ".md":
            files.append(root)
        elif root.exists():
            files.extend(path for path in root.rglob("*.md") if "openwebui-data" not in path.parts)
    return files


def _link_targets(text: str) -> list[str]:
    return [match.group(1).strip() for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", text)]


def _local_target_path(base: Path, target: str) -> Path | None:
    if not target or "://" in target or target.startswith("#"):
        return None
    clean = target.split("#", 1)[0].strip()
    if not clean:
        return None
    return (base / clean).resolve(strict=False)


def test_referenced_flow_svgs_exist() -> None:
    missing: list[str] = []
    for readme in _markdown_files():
        text = readme.read_text(encoding="utf-8", errors="replace")
        for target in _link_targets(text):
            if "flow.svg" not in target:
                continue
            path = _local_target_path(readme.parent, target)
            if path is not None and not path.exists():
                missing.append(f"{readme}: {target}")

    assert missing == []


def test_module_reference_links_in_readmes_exist() -> None:
    missing: list[str] = []
    for readme in _markdown_files():
        text = readme.read_text(encoding="utf-8", errors="replace")
        for target in _link_targets(text):
            if "MODULE_REFERENCE.md" not in target:
                continue
            path = _local_target_path(readme.parent, target)
            if path is not None and not path.exists():
                missing.append(f"{readme}: {target}")

    assert missing == []


def test_runtime_env_contract_mentions_public_and_internal_ports() -> None:
    text = (ROOT / "docs" / "runtime_env_contract.md").read_text(encoding="utf-8", errors="replace")

    assert "3571" in text
    assert "3572" in text
    assert "AICARMINE_LAB_REPO" in text


def test_launcher_contract_distinguishes_ollama_ports() -> None:
    text = (ROOT / "docs" / "launcher_contract.md").read_text(encoding="utf-8", errors="replace")

    assert "11434" in text
    assert "11435" in text


def test_documented_service_flow_svgs_exist() -> None:
    for rel in (
        "flow.svg",
        "services/flow.svg",
        "services/aicarmine_broker/flow.svg",
        "services/vulkan_bridge/flow.svg",
        "services/launch/flow.svg",
        "services/codex_bridge/flow.svg",
        "services/model_export/flow.svg",
    ):
        assert (ROOT / rel).exists(), rel
