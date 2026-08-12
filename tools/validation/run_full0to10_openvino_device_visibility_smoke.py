#!/usr/bin/env python3
"""Static smoke for OpenVINO device visibility normalization."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.repo_root).resolve()
    sys.path.insert(0, str(root / "Tools/ai"))

    from full0to10_hardware_capability.openvino_devices import (  # noqa: WPS433
        normalize_openvino_device_visibility,
    )

    sample = {
        "result": {
            "stdout": json.dumps({"devices": ["CPU", "GPU.0", "GPU.1", "NPU"]})
        }
    }
    visibility = normalize_openvino_device_visibility(sample)

    files = {
        "hardware_builder": root / "Tools/ai/full0to10_hardware_capability/builder.py",
        "openvino_devices": root / "Tools/ai/full0to10_hardware_capability/openvino_devices.py",
        "accelerator_visibility": root / "Tools/ai/full0to10_accelerator_control/device_visibility.py",
        "semantic_constants": root / "Tools/ai/full0to10_provider_telemetry_semantic/constants.py",
        "semantic_validator": root / "Tools/ai/full0to10_provider_telemetry_semantic/validator.py",
    }
    texts = {name: read(path) for name, path in files.items()}
    joined = "\n".join(texts.values())
    checks = {
        "required_files_exist": all(path.exists() for path in files.values()),
        "sample_devices_normalized": visibility["openvino_devices"] == ["CPU", "GPU.0", "GPU.1", "NPU"],
        "cpu_top_level_visible": visibility["openvino_cpu"]["device_visible"],
        "gpu0_top_level_visible": visibility["openvino_gpu0"]["device_visible"],
        "gpu1_top_level_visible": visibility["openvino_gpu1"]["device_visible"],
        "npu_top_level_visible": visibility["openvino_npu"]["device_visible"],
        "builder_exports_top_level_fields": all(
            token in texts["hardware_builder"]
            for token in ("openvino_cpu", "openvino_gpu0", "openvino_gpu1", "openvino_npu")
        ),
        "semantic_validator_requires_top_level_fields": (
            "accelerator_has_top_level_openvino_fields" in texts["semantic_constants"]
            and "openvino_gpu1" in texts["semantic_validator"]
        ),
        "no_git_restore_docs": "git restore docs" not in joined.lower(),
    }
    report = {"passed": all(checks.values()), "checks": checks, "visibility": visibility}
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
