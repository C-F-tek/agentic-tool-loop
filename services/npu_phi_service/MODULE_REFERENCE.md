# npu_phi_service Module Reference

Updated: 2026-08-13

`services\npu_phi_service` is a local diagnostic sidecar for
`OpenVINO/Phi-3.5-mini-instruct-int4-cw-ov`.

Runtime boundary:

- Runs as a separate process on `127.0.0.1:3551`.
- Uses `C:\Users\carmi\AI\venvs\openvino`.
- Does not replace the existing OpenVINO reranker on `3550`.
- Does not expose a public OpenWebUI tool.
- Does not block the broker/planner loop.

Main components:

| File | Owner |
| --- | --- |
| `settings.py` | Environment/config model for model/cache/spool/port. |
| `diagnostics.py` | Read-only doctor payload for model files, runtime paths, dependencies and 3550/3551 contract checks. It does not build the pipeline, create cache/spool dirs or start the service. |
| `blob_lock.py` | Cross-process file lock for local AOT blob export/warmup. Recovers stale locks and prevents parallel export to the same blob path. |
| `pipeline.py` | Lazy singleton `openvino_genai.LLMPipeline` on device `NPU`. |
| `job_queue.py` | Mono-worker queue, dedupe, drop-on-full policy and local spool. |
| `circuit_breaker.py` | Explicit open/closed diagnostics for repeated failures. |
| `app.py` | FastAPI HTTP surface: `/healthz`, `/readyz`, `/metrics`, job enqueue/status and admin warmup/reset. |
| `__main__.py` | `python -m npu_phi_service` entrypoint; supports `--doctor --pretty` for read-only diagnostics before startup. |

Operational rules:

- `CACHE_DIR` is always configured through `NPU_PHI_CACHE_DIR`.
- AOT blob export is local host optimization only, not a repo artifact.
- Queue defaults to max size `1`; overload returns `accepted=false` with
  `reason=queue_full`.
- Pipeline construction happens only on warmup or a real job, never at import.
- Missing model/dependency state is surfaced in `/readyz`; it is not hidden by
  CPU/GPU fallback.
- Before starting the sidecar, `python -m npu_phi_service --doctor --pretty`
  can verify model XML/BIN, dependencies, venv identity, cache/spool paths and
  the dedicated `3551 != 3550` contract without side effects.
- Do not add or restore smoke/test scripts for this sidecar unless Carmine
  explicitly asks. Use doctor output, process ownership, port ownership and
  real sidecar responses as diagnostic evidence.
