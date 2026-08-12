"""Build Full0To10 track input contract artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import CONTRACT_JSON, CONTRACT_MD, TEMPLATE_JSON
from .contract import build_contract
from .paths import ensure_dir, repo_relative
from .render import render_contract_markdown
from .template import build_template


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_track_input_contract(
    repo_root: Path,
    output_dir: Path,
    track_name: str,
    require_inputs: bool,
    max_candidates: int,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output_dir = ensure_dir(output_dir)
    contract = build_contract(repo_root, track_name, max_candidates, require_inputs)
    template = build_template(track_name)

    contract_path = output_dir / CONTRACT_JSON
    markdown_path = output_dir / CONTRACT_MD
    template_path = output_dir / TEMPLATE_JSON
    write_json(contract_path, contract)
    write_json(template_path, template)
    markdown_path.write_text(render_contract_markdown(contract), encoding="utf-8")

    contract["outputs"] = {
        "contract": repo_relative(contract_path, repo_root),
        "markdown": repo_relative(markdown_path, repo_root),
        "template": repo_relative(template_path, repo_root),
    }
    return contract
