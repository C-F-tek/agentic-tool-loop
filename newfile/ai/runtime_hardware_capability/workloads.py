from __future__ import annotations

import time
from datetime import datetime
from typing import Any


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _base_report() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "kind": "openvino_gpu0_secondary_workload",
        "generated_at": now_iso(),
        "provider_execution_requested": True,
        "provider_execution_performed": False,
        "patch_application_performed": False,
        "source_writes_performed": False,
        "media_runtime_performed": False,
        "openvino_gpu0_visible": False,
        "openvino_gpu0_probe_performed": False,
        "openvino_gpu0_workload_performed": False,
        "openvino_gpu0_workload_passed": False,
        "openvino_gpu0_provider_execution_performed": False,
        "openvino_gpu0_role": "secondary_accelerator",
        "openvino_gpu0_not_primary_advisory": True,
        "openvino_gpu0_support_lane": False,
        "openvino_gpu0_sustained_workload_requested": False,
        "openvino_gpu0_sustained_workload_performed": False,
        "openvino_gpu0_sustained_iterations_requested": 1,
        "openvino_gpu0_sustained_iterations_performed": 0,
        "openvino_gpu0_sustained_min_seconds_requested": 0.0,
        "openvino_gpu1_reserved_visible": False,
        "openvino_gpu1_workload_performed": False,
        "openvino_gpu1_openvino_workload_allowed": False,
        "openvino_gpu1_role": "reserved_for_cuda_ollama",
        "selected_device": "",
        "available_devices": [],
        "elapsed_seconds": 0.0,
        "compile_seconds": 0.0,
        "inference_seconds": 0.0,
        "output_preview": "",
        "errors": [],
        "warnings": [],
        "passed": False,
    }


def run_openvino_gpu0_tensor_test(
    *,
    iterations: int = 1,
    min_seconds: float = 0.0,
    role: str = "secondary_accelerator",
    production_support: bool = False,
) -> dict[str, Any]:
    report = _base_report()
    report["openvino_gpu0_role"] = role
    report["openvino_gpu0_support_lane"] = bool(production_support)
    report["openvino_gpu0_sustained_workload_requested"] = iterations > 1 or min_seconds > 0
    report["openvino_gpu0_sustained_iterations_requested"] = max(1, int(iterations))
    report["openvino_gpu0_sustained_min_seconds_requested"] = max(0.0, float(min_seconds))
    started = time.perf_counter()
    try:
        import numpy as np
    except Exception as exc:
        report["errors"].append(f"numpy import failed: {type(exc).__name__}: {exc}")
        report["elapsed_seconds"] = round(time.perf_counter() - started, 6)
        return report
    try:
        try:
            from openvino import Core, Model
        except ImportError:
            from openvino.runtime import Core, Model
        try:
            from openvino.runtime import opset8 as opset
        except ImportError:
            from openvino import opset8 as opset
    except Exception as exc:
        report["errors"].append(f"OpenVINO import failed: {type(exc).__name__}: {exc}")
        report["elapsed_seconds"] = round(time.perf_counter() - started, 6)
        return report
    try:
        core = Core()
        devices = [str(item) for item in core.available_devices]
        report["available_devices"] = devices
        report["openvino_gpu0_probe_performed"] = True
        report["openvino_gpu0_visible"] = "GPU.0" in devices
        report["openvino_gpu1_reserved_visible"] = "GPU.1" in devices
        if "GPU.1" in devices:
            report["warnings"].append("OpenVINO GPU.1 is visible but reserved; no workload was executed on GPU.1.")
        if "GPU.0" not in devices:
            report["errors"].append("OpenVINO GPU.0 secondary lane is not visible; workload not executed.")
            report["elapsed_seconds"] = round(time.perf_counter() - started, 6)
            return report

        shape = [256, 256]
        x = opset.parameter(shape, dtype=np.float32, name="x")
        one = opset.constant(np.ones(tuple(shape), dtype=np.float32))
        two = opset.constant(np.full(tuple(shape), 2.0, dtype=np.float32))
        y = opset.add(opset.multiply(x, two), one, name="gpu0_support_math")
        model = Model([y], [x], "ia_carmine_gpu0_provider_support_test")
        compile_started = time.perf_counter()
        compiled = core.compile_model(model, "GPU.0")
        report["compile_seconds"] = round(time.perf_counter() - compile_started, 6)

        payload = np.zeros(tuple(shape), dtype=np.float32)
        values = []
        inference_started = time.perf_counter()
        performed = 0
        minimum_iterations = max(1, int(iterations))
        minimum_seconds = max(0.0, float(min_seconds))
        while True:
            result = compiled({"x": payload})
            performed += 1
            for item in result.values():
                values = np.asarray(item).reshape(-1)[:4].tolist()
                break
            if performed >= minimum_iterations and (time.perf_counter() - inference_started) >= minimum_seconds:
                break
        inference_elapsed = time.perf_counter() - inference_started
        report["inference_seconds"] = round(inference_elapsed, 6)
        report["openvino_gpu0_sustained_iterations_performed"] = performed
        report["openvino_gpu0_sustained_workload_performed"] = bool(performed > 1 or minimum_seconds > 0)

        expected = [1.0, 1.0, 1.0, 1.0]
        passed = len(values) == 4 and all(abs(float(a) - b) < 0.0001 for a, b in zip(values, expected))
        report["selected_device"] = "GPU.0"
        report["output_preview"] = str(values[:4])
        report["openvino_gpu0_workload_performed"] = True
        report["openvino_gpu0_workload_passed"] = passed
        report["openvino_gpu0_provider_execution_performed"] = True
        report["provider_execution_performed"] = True
        report["passed"] = bool(passed)
        if not passed:
            report["errors"].append(f"unexpected GPU.0 tensor output: {values}")
    except Exception as exc:
        report["errors"].append(f"OpenVINO GPU.0 workload failed: {type(exc).__name__}: {exc}")
    finally:
        report["elapsed_seconds"] = round(time.perf_counter() - started, 6)
    return report
