# NPU Phi Service - Complete Guide

## Overview

`services\npu_phi_service` is a local diagnostic sidecar for `OpenVINO/Phi-3.5-mini-instruct-int4-cw-ov`. It runs as an independent process on port **3551** and provides OpenVINO-based inference capabilities without interfering with the main broker/planner loop or the existing reranker on port 3550.

## Architecture

### Runtime Boundary

- **Process**: Runs as a separate FastAPI HTTP service
- **Port**: `127.0.0.1:3551` (dedicated, never shares with 3550)
- **Virtual Environment**: Uses `C:\Users\carmi\AI\venvs\openvino`
- **Model**: OpenVINO/Phi-3.5-mini-instruct-int4-cw-ov
- **Device**: NPU (Neural Processing Unit)

### Component Map

| File | Owner | Description |
| --- | --- | --- |
| `settings.py` | Configuration model | Environment/config for model/cache/spool/port |
| `diagnostics.py` | Read-only doctor payload | Model files, runtime paths, dependencies, 3550/3551 contract checks. Does not build pipeline or create cache dirs. |
| `blob_lock.py` | Cross-process file lock | Local AOT blob export/warmup. Recovers stale locks and prevents parallel export to same blob path. |
| `pipeline.py` | Lazy singleton | `openvino_genai.LLMPipeline` on device NPU. Construction happens only on warmup or real job, never at import. |
| `job_queue.py` | Mono-worker queue | Dedupe, drop-on-full policy and local spool. Max size defaults to 1. |
| `circuit_breaker.py` | Failure tracking | Explicit open/closed diagnostics for repeated failures. |
| `app.py` | FastAPI HTTP surface | `/healthz`, `/readyz`, `/metrics`, job enqueue/status, admin warmup/reset endpoints. |
| `__main__.py` | Entrypoint | `python -m npu_phi_service`; supports `--doctor --pretty` for read-only diagnostics before startup. |

## Operational Rules

### 1. Cache and Blob Management

- `CACHE_DIR` is always configured through `NPU_PHI_CACHE_DIR`
- AOT (Ahead-of-Time) blob export is local host optimization only, not a repo artifact
- Blob lock prevents parallel exports to the same path; stale locks are automatically recovered

### 2. Queue Behavior

- Queue defaults to max size **1** (mono-worker)
- When queue is full: returns `accepted=false` with `reason=queue_full`
- Jobs are deduplicated before enqueueing
- Local spool manages pending and completed jobs

### 3. Pipeline Construction

- Lazy singleton pattern: pipeline construction happens only on warmup or a real job
- Never constructed at import time
- Missing model/dependency state is surfaced in `/readyz`; not hidden by CPU/GPU fallback

### 4. Diagnostic Contract

Before starting the sidecar, run:
```powershell
python -m npu_phi_service --doctor --pretty
```

This verifies:
- Model XML/BIN files exist and are valid
- Dependencies are installed correctly
- Virtual environment identity matches expected path
- Cache/spool paths are accessible
- Dedicated port contract (3551 != 3550) is satisfied
- No side effects: read-only check only

### 5. Health Endpoints

| Endpoint | Purpose | Read/Write |
| --- | --- | --- |
| `/healthz` | Service health check | Read-only |
| `/readyz` | Model readiness and dependency status | Read-only |
| `/metrics` | Operational metrics | Read-only |
| POST `/job` | Enqueue a job | Write |
| GET `/job/{id}` | Get job status | Read-only |
| POST `/admin/warmup` | Trigger warmup | Admin write |
| POST `/admin/reset` | Reset pipeline state | Admin write |

## Safety Boundaries

### What NPU Phi Service Does NOT Do

- Does not replace the existing OpenVINO reranker on port 3550
- Does not expose a public OpenWebUI tool
- Does not block the broker/planner loop (runs independently)
- Does not perform CPU/GPU fallback silently; missing state is surfaced in `/readyz`

### What You Should NOT Do

- Do not add or restore smoke/test scripts unless Carmine explicitly asks
- Use doctor output, process ownership, port ownership and real sidecar responses as diagnostic evidence
- Do not modify cache directories or blob exports as repo artifacts
- Do not treat NPU phi service as part of the main agentic loop; it's a supporting inference sidecar

## Troubleshooting

### Common Issues

1. **Port Conflict**: If port 3551 is already in use, verify no stale process exists:
   ```powershell
   netstat -ano | findstr ":3551"
   ```

2. **Model Not Found**: Check `NPU_PHI_CACHE_DIR` points to valid model XML/BIN files
   Run doctor mode first to diagnose.

3. **Queue Full**: If jobs are rejected with `queue_full`, the mono-worker is busy; wait for completion or reset via admin endpoint.

4. **Stale Blob Lock**: blob_lock.py handles automatic recovery, but if locks persist, clear the cache directory and restart.

### Diagnostic Flow

```
Symptom → Doctor output check → Process/port verification → Sidecar response → Evidence logged
```

Use `--doctor --pretty` before any modification to ensure baseline state is healthy.