"""
Secure Ollama API Wrapper with FastAPI
=====================================

This module provides a secure REST API layer around the Ollama local model service.
It implements:
- Input validation and sanitization
- Dangerous pattern detection (command injection, file operations, etc.)
- Rate limiting per client
- Structured error responses
- Security headers
- Request logging and audit trail

Usage:
    python services/secure_ollama_api.py

The server starts on http://127.0.0.1:8080 by default.
"""

import json
import time
import logging
import re
from typing import Optional
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request, Header, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
import uvicorn

# ------------------------------------------------------------------
# Logging setup
# ------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("secure_ollama_api")

# ------------------------------------------------------------------
# Ollama connection config
# ------------------------------------------------------------------
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_API_GENERATE = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_API_CHAT     = f"{OLLAMA_BASE_URL}/api/chat"
OLLAMA_API_TAGS     = f"{OLLAMA_BASE_URL}/api/tags"

# Timeout for Ollama calls (seconds)
OLLAMA_TIMEOUT = 30

# ------------------------------------------------------------------
# Rate-limit tracking:  {client_ip: [timestamp, ...]}
# ------------------------------------------------------------------
RATE_LIMIT_MAX_REQUESTS = 60       # max requests per window
RATE_LIMIT_WINDOW_SECONDS = 60     # sliding window
rate_limit_store: dict[str, list[float]] = {}

# ------------------------------------------------------------------
# Dangerous-pattern blocks (case-insensitive)
# ------------------------------------------------------------------
DANGEROUS_PATTERNS = [
    # Shell injection
    r";\s*(?:rm|mkdir|chmod|chown|cp|mv|wget|curl|apt|yum|pip|npm|sudo)\b",
    r"\|\s*(?:rm|mkdir|chmod|chown|cp|mv|wget|curl|apt|yum|pip|npm|sudo)\b",
    r"\&\&\s*(?:rm|mkdir|chmod|chown|cp|mv|wget|curl|apt|yum|pip|npm|sudo)\b",
    r"\$\([^)]+\)",                    # $(...) subshell
    r"`[^`]+`",                       # backtick execution
    r"\bexec\s*\(",                   # exec(
    r"\bsystem\s*\(",                 # system(
    r"\bos\.system\b",                # os.system
    r"\bsubprocess\.",                # subprocess module
    r"\bpopen\b",                     # popen
    r"\bsh\b\s*\.",                   # sh.
    r"\bbash\b\s*\.",                 # bash.
    r"\bsh\b\s*-",                    # sh -
    r"\bbash\b\s*-",                  # bash -
    r"\bwget\b",                      # wget
    r"\bcurl\b",                      # curl (as command, not URL)
    r"\brm\s+-",                      # rm -
    r"\bchmod\b",                     # chmod
    r"\bsudo\b",                      # sudo
    # SQL injection (if user is passing to a DB)
    r"\bDROP\s+TABLE\b",
    r"\bDELETE\s+FROM\b",
    r"\bDROP\s+DATABASE\b",
    # Path traversal
    r"\.\./",                          # ../
    r"\\\.\\",                        # \..\
    # Data exfiltration hints
    r"\bcat\s+/etc/",                # /etc/ file read
    r"\bcat\s+/proc/",               # /proc/ file read
    r"\bcat\s+/var/",                # /var/ file read
    r"\bcat\s+/root/",               # /root/ file read
    # Python dangerous imports
    r"\bimport\s+os\b",
    r"\bimport\s+subprocess\b",
    r"\bimport\s+shutil\b",
    r"\bimport\s+pickle\b",
    r"\bimport\s+marshal\b",
    r"\bimport\s+ctypes\b",
    # JavaScript dangerous
    r"\beval\s*\(",
    r"\bFunction\s*\(",
    r"\bsetTimeout\s*\(",
    r"\bsetInterval\s*\(",
    # Base64 decode (potential obfuscation)
    r"\bbase64\s*decode\b",
    r"\bdecode\s*\(.*base64",
    # PowerShell dangerous
    r"\bpowershell\s+-command\s+",
    r"\bInvoke-Expression\b",
    r"\bIEX\s*\(",
    r"\bInvoke-RestMethod\b",
    r"\bInvoke-WebRequest\b",
]

# Compile patterns once
COMPILED_DANGEROUS_PATTERNS = [
    __import__("re").compile(p, __import__("re").IGNORECASE)
    for p in DANGEROUS_PATTERNS
]


def _check_dangerous(text: str) -> Optional[str]:
    """Return the first matching dangerous pattern, or None."""
    for pat in COMPILED_DANGEROUS_PATTERNS:
        if pat.search(text):
            return pat.pattern
    return None


# ------------------------------------------------------------------
# Pydantic models
# ------------------------------------------------------------------
class QueryRequest(BaseModel):
    """Request for /query endpoint."""
    prompt: str = Field(..., min_length=1, max_length=4096)
    model: Optional[str] = Field(default="llama2", description="Ollama model name")
    stream: bool = Field(default=False, description="Stream response")

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        danger = _check_dangerous(v)
        if danger:
            raise ValueError(f"Prompt contains dangerous pattern: {danger}")
        return v.strip()


class ChatRequest(BaseModel):
    """Request for /chat endpoint."""
    messages: list[dict] = Field(..., min_length=1)
    model: Optional[str] = Field(default="llama2")
    stream: bool = False

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, v: list[dict]) -> list[dict]:
        for msg in v:
            content = msg.get("content", "")
            if isinstance(content, str):
                danger = _check_dangerous(content)
                if danger:
                    raise ValueError(f"Message contains dangerous pattern: {danger}")
        return v


class TagsResponse(BaseModel):
    """Response from /api/tags."""
    models: list[dict] = Field(default_factory=list)


class GenerateResponse(BaseModel):
    """Response from /api/generate."""
    response: Optional[str] = None
    model: Optional[str] = None
    done: Optional[bool] = None
    error: Optional[str] = None


class ChatResponse(BaseModel):
    """Response from /api/chat."""
    message: Optional[dict] = None
    model: Optional[str] = None
    done: Optional[bool] = None
    error: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str
    code: int
    reason: str


# ------------------------------------------------------------------
# Rate limiter
# ------------------------------------------------------------------
def _check_rate_limit(client_ip: str) -> None:
    """Raise HTTPException if rate limit exceeded."""
    now = time.time()
    if client_ip not in rate_limit_store:
        rate_limit_store[client_ip] = []

    # Remove old entries outside the window
    rate_limit_store[client_ip] = [
        t for t in rate_limit_store[client_ip]
        if now - t < RATE_LIMIT_WINDOW_SECONDS
    ]

    if len(rate_limit_store[client_ip]) >= RATE_LIMIT_MAX_REQUESTS:
        logger.warning(f"Rate limit exceeded for {client_ip}")
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests. Try again in {RATE_LIMIT_WINDOW_SECONDS} seconds.",
        )

    rate_limit_store[client_ip].append(now)


# ------------------------------------------------------------------
# Ollama HTTP caller (using httpx instead of curl subprocess)
# ------------------------------------------------------------------
def _call_ollama(url: str, data: dict, timeout: int = OLLAMA_TIMEOUT) -> dict:
    """Send a POST request to Ollama and return the JSON response."""
    headers = {"Content-Type": "application/json"}
    try:
        with httpx.Client() as client:
            response = client.post(url, json=data, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.json() if response.content else {}
    except httpx.TimeoutError:
        raise HTTPException(status_code=408, detail="Ollama request timed out")
    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
        logger.error(f"Ollama call failed: {error_msg}")
        raise HTTPException(status_code=502, detail=f"Ollama error: {error_msg}")
    except Exception as e:
        logger.error(f"Ollama call exception: {e}")
        raise HTTPException(status_code=502, detail=f"Ollama communication error: {str(e)}")


# ------------------------------------------------------------------
# FastAPI app
# ------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown hooks."""
    logger.info("Secure Ollama API starting up...")
    # Check Ollama connectivity
    try:
        tags = _call_ollama(OLLAMA_API_TAGS, {})
        logger.info(f"Ollama models available: {tags}")
    except Exception as e:
        logger.warning(f"Ollama not reachable at startup: {e}")
    yield
    logger.info("Secure Ollama API shutting down.")


app = FastAPI(
    title="Secure Ollama API",
    description="A secure REST wrapper around Ollama with input validation and rate limiting.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response


@app.get("/api/tags")
async def list_models() -> TagsResponse:
    """List available Ollama models."""
    try:
        result = _call_ollama(OLLAMA_API_TAGS, {})
        return TagsResponse(models=result.get("models", []))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch models: {str(e)}")


@app.post("/query")
async def query_ollama(req: QueryRequest, request: Request):
    """Generate a response from Ollama.

    - Validates input against dangerous patterns
    - Enforces rate limiting
    - Returns structured JSON response
    """
    client_ip = request.client.host
    _check_rate_limit(client_ip)

    logger.info(f"Query from {client_ip}: model={req.model}, prompt={req.prompt[:100]}...")

    data = {
        "model": req.model,
        "prompt": req.prompt,
        "stream": req.stream,
    }

    try:
        result = _call_ollama(OLLAMA_API_GENERATE, data)
        return {"response": result.get("response", ""), "model": req.model}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Generation error: {str(e)}")


@app.post("/chat")
async def chat_ollama(req: ChatRequest, request: Request):
    """Chat with Ollama.

    - Validates each message against dangerous patterns
    - Enforces rate limiting
    - Returns structured JSON response
    """
    client_ip = request.client.host
    _check_rate_limit(client_ip)

    logger.info(f"Chat from {client_ip}: model={req.model}, messages={len(req.messages)}")

    data = {
        "model": req.model,
        "messages": req.messages,
        "stream": req.stream,
    }

    try:
        result = _call_ollama(OLLAMA_API_CHAT, data)
        return {"message": result.get("message", {}), "model": req.model}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Chat error: {str(e)}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        _call_ollama(OLLAMA_API_TAGS, {})
        return {"status": "healthy", "ollama": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "ollama": str(e)}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Custom HTTP exception handler for structured error responses."""
    return ErrorResponse(
        detail=exc.detail,
        code=exc.status_code,
        reason="HTTP error",
    )


if __name__ == "__main__":
    uvicorn.run(
        __file__,
        host="127.0.0.1",
        port=8080,
        reload=False,
        log_level="info",
    )
