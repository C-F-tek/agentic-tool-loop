# npu_phi_service Module Reference

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
| `pipeline.py` | Lazy singleton `openvino_genai.LLMPipeline` on device `NPU`. |
| `job_queue.py` | Mono-worker queue, dedupe, drop-on-full policy and local spool. |
| `circuit_breaker.py` | Explicit open/closed diagnostics for repeated failures. |
| `app.py` | FastAPI HTTP surface: `/healthz`, `/readyz`, `/metrics`, job enqueue/status and admin warmup/reset. |
| `__main__.py` | `python -m npu_phi_service` entrypoint. |

Operational rules:

- `CACHE_DIR` is always configured through `NPU_PHI_CACHE_DIR`.
- AOT blob export is local host optimization only, not a repo artifact.
- Queue defaults to max size `1`; overload returns `accepted=false` with
  `reason=queue_full`.
- Pipeline construction happens only on warmup or a real job, never at import.
- Missing model/dependency state is surfaced in `/readyz`; it is not hidden by
  CPU/GPU fallback.
