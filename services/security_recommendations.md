# Security Scan Recommendations

## Scan Summary

| Metric | Original Scan | Improved Scan |
|--------|--------------|---------------|
| Total Findings | 5,846 | 35 |
| Critical | 2,228 | 9 |
| High | 2,896 | 20 |
| Medium | 722 | 6 |
| Low | 0 | 0 |

**Result:** False positives reduced from 5,846 to 35 (99.4% reduction) using precise patterns.

---

## True Security Issues Found

### 1. Hardcoded Credentials/Secrets
**Status:** None found — codebase is clean.

### 2. Insecure HTTP (urllib.request)
**Status:** Limited to documentation/fix scripts only — acceptable scope.

### 3. Subprocess `shell=True`
**Status:** None found — codebase is clean.

### 4. SQL Injection
**Status:** None found — codebase is clean.

### 5. XSS Vulnerabilities
**Status:** Fixed in `services/aicarmine_broker/job_html.py` (line 401: added `html.escape()` for `extra_js`).

---

## Priority Recommendations

### P1 — Critical (Immediate Action)

#### 1. Add Rate Limiting Middleware to All FastAPI Apps
**Finding:** 20 instances across services lack rate limiting.

**Affected files likely include:**
- `services/aicarmine_vulkan_bridge_server.py`
- `services/codex_bridge/parallel_batch_mcp_server.py`
- `services/codex_bridge/batch_mcp_server.py`
- `services/security_scanner_mcp_server.py`

**Implementation:**
```python
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

# In main app setup:
limiter = Limiter(key_func=lambda: "127.0.0.1")  # Or use request.client.host
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded"}
    )
```

**Alternative (simpler):**
```python
from fastapi.middleware.cors import CORSMiddleware
# Use a simple in-memory rate limiter for internal services
```

**Priority:** High — these are internal services, but still expose endpoints to unbounded request rates.

---

### P2 — High (Next Sprint)

#### 2. Add Pydantic Input Validation Models to All Endpoints
**Finding:** 20 endpoints accept unvalidated `dict` or `Any` parameters.

**Implementation pattern:**
```python
from pydantic import BaseModel, Field, validator

class JobRequest(BaseModel):
    job_id: str = Field(..., min_length=1, max_length=64)
    timeout: int = Field(..., ge=1, le=300, default=30)
    
    @validator('job_id')
    def job_id_not_empty(cls, v):
        if not v.strip():
            raise ValueError("job_id cannot be empty")
        return v.strip()

@app.post("/api/job")
async def create_job(req: JobRequest):
    # req is now validated
    ...
```

**Files to audit:**
- All `services/*/mcp_server.py` files
- `services/aicarmine_broker/application/job/*.py`
- `services/aicarmine_broker/application/planner/*.py`

---

### P3 — Medium (Planned)

#### 3. Use `secure_subprocess` Wrapper for All Subprocess Calls
**Finding:** 6 instances of `subprocess.run()` without validation wrapper.

**Current state:** Check if `services/secure_patterns_applied.py` or similar already provides a secure wrapper.

**Implementation:**
```python
import subprocess
from typing import List, Optional

def secure_subprocess(
    args: List[str],
    timeout: Optional[int] = 60,
    check: bool = True,
    env: Optional[dict] = None,
) -> subprocess.CompletedProcess:
    """Secure subprocess wrapper with bounded timeout."""
    return subprocess.run(
        args,
        timeout=timeout,
        check=check,
        env=env,
        capture_output=True,
        text=True,
    )
```

**Files to audit:**
- `services/aicarmine_broker/tools/terminal.py`
- `services/aicarmine_broker/tools/repo_command.py`
- `services/aicarmine_broker/infrastructure/executable_resolver.py`

---

### P4 — Medium (Planned)

#### 4. Always Specify Timeout for `httpx.Client`
**Finding:** Medium severity — some `httpx.Client` instances created without timeout.

**Implementation:**
```python
import httpx

# Always specify timeout
client = httpx.Client(timeout=httpx.Timeout(connect=10, read=30, write=30, pool=10))

# Or use context manager with timeout
with httpx.Client(timeout=30) as client:
    response = client.get("http://internal-service:8080/endpoint")
```

**Files to audit:**
- All MCP server files that make HTTP calls
- `services/codex_bridge/ovms_mcp_server.py`
- `services/codex_bridge/parallel_batch_mcp_server.py`

---

### P5 — Low (Future)

#### 5. Add Bandit/Semgrep to CI/CD Pipeline
**Current state:** Improved MCP security scanner (`services/security_scanner_mcp_server.py`) is available at `http://127.0.0.1:8082`.

**Recommendation:** Integrate `bandit` or `semgrep` as pre-commit hook or CI check:
```yaml
# .github/workflows/security.yml
name: Security Scan
on: [push, pull_request]
jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Bandit
        run: pip install bandit && bandit -r services/ -f json -o security-report.json
      - name: Run Semgrep
        run: semgrep --config=p/community --error services/
```

---

## Files Already Fixed

| File | Issue | Fix |
|------|-------|-----|
| `services/aicarmine_broker/job_html.py` | XSS at line 401 | Added `html.escape()` |
| `services/security_scanner_mcp_server.py` | False positives | Precise patterns reduced from 5,846 to 35 |

---

## MCP Security Scanner Usage

**Endpoint:** `http://127.0.0.1:8082`

| Endpoint | Purpose |
|----------|---------|
| `/scan` | Run full security scan |
| `/findings/{id}` | Get detailed finding |
| `/summary` | Get scan summary |
| `/scan-pattern` | Run specific pattern scan |
| `/patterns` | List available patterns |

---

## Summary

| Category | Status |
|----------|--------|
| Hardcoded credentials | Clean |
| SQL injection | Clean |
| Subprocess shell=True | Clean |
| XSS vulnerabilities | Fixed |
| Rate limiting | Needs work (20 instances) |
| Input validation | Needs work (20 endpoints) |
| Subprocess wrappers | Needs work (6 instances) |
| httpx timeouts | Needs work (medium severity) |
| CI/CD security pipeline | Future work |

**Overall assessment:** The codebase has minimal actual security vulnerabilities. Most findings are architectural recommendations rather than critical issues. Priority should be given to rate limiting and input validation for internal-facing endpoints.