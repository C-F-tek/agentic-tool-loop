import json
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


AI_ROOT = Path(os.environ.get("AI_ROOT", r"C:\Users\carmi\AI"))
RUNNER = Path(
    os.environ.get(
        "AICARMINE_SAFE_COMMAND_RUNNER",
        str(AI_ROOT / "services" / "aicarmine-run-safe-command.ps1"),
    )
).resolve(strict=False)
TOKEN = os.environ.get("AICARMINE_EXECUTOR_TOKEN", "")

app = FastAPI(title="AI-Carmine Codex Executor", version="2.0.0")


class RunRequest(BaseModel):
    command: str
    timeout_seconds: Optional[int] = Field(180, ge=1, le=3600)
    repo_mode: str = Field("lab", pattern="^(lab|main|custom)$")
    repo: str = ""
    user_consent: str = ""


def _auth(authorization: Optional[str]) -> None:
    if not TOKEN:
        return

    expected = f"Bearer {TOKEN}"

    if authorization != expected:
        raise HTTPException(status_code=401, detail="invalid executor token")


@app.get("/health")
def health() -> dict:
    return {
        "ok": RUNNER.exists(),
        "runner": str(RUNNER),
        "token_required": bool(TOKEN),
        "default_repo_mode": "lab",
        "time": time.time(),
    }


@app.post("/run")
def run_command(req: RunRequest, authorization: Optional[str] = Header(default=None)) -> dict:
    _auth(authorization)

    if not RUNNER.exists():
        raise HTTPException(status_code=500, detail=f"runner not found: {RUNNER}")

    timeout = int(req.timeout_seconds or 180)

    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(RUNNER),
        "-Command",
        req.command,
        "-TimeoutSeconds",
        str(timeout),
        "-RepoMode",
        req.repo_mode,
    ]

    if req.repo:
        cmd.extend(["-Repo", req.repo])

    if req.user_consent:
        cmd.extend(["-UserConsent", req.user_consent])

    try:
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=timeout + 30,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail=f"executor timeout: {exc}") from exc

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    parsed = None
    try:
        parsed = json.loads(stdout)
    except Exception:
        parsed = None

    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "report": parsed,
    }

# ------------------------------------------------------------------
# File-backed payload transport
# ------------------------------------------------------------------

PAYLOAD_ROOT = Path(os.environ.get("AICARMINE_PAYLOAD_ROOT", r"C:\Users\carmi\AI\payloads\executor")).resolve()


class RunPayloadFileRequest(BaseModel):
    payload_file: str


def _safe_payload_file(value: str) -> Path:
    raw = str(value or "").strip().strip("\"'")
    if not raw:
        raise HTTPException(status_code=400, detail="empty payload_file")

    path = Path(raw).resolve(strict=False)

    try:
        path.relative_to(PAYLOAD_ROOT)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"payload_file must be under {PAYLOAD_ROOT}",
        )

    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"payload file not found: {path}")

    return path


@app.get("/payload_health")
def payload_health() -> dict:
    PAYLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    return {
        "ok": True,
        "payload_root": str(PAYLOAD_ROOT),
        "exists": PAYLOAD_ROOT.exists(),
    }



def _read_payload_json_file(path: Path) -> dict:
    """Read file-backed JSON payloads robustly.

    Accepts:
    - UTF-8 without BOM
    - UTF-8 with BOM
    - UTF-16 LE/BE BOM
    """
    raw = path.read_bytes()

    if raw.startswith(b"\xef\xbb\xbf"):
        text = raw.decode("utf-8-sig")
    elif raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8")

    return json.loads(text)

@app.post("/run_payload_file")
def run_payload_file(
    req: RunPayloadFileRequest,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    _auth(authorization)

    PAYLOAD_ROOT.mkdir(parents=True, exist_ok=True)

    payload_file = _safe_payload_file(req.payload_file)

    try:
        payload = _read_payload_json_file(payload_file)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"invalid payload json: {type(exc).__name__}: {exc}",
        ) from exc

    run_req = RunRequest(**payload)

    result = run_command(run_req, authorization=authorization)
    result["payload_file"] = str(payload_file)
    result["transport"] = "file_backed"
    return result



