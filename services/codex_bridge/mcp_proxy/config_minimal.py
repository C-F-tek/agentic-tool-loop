from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.resolve()

DEFAULT_SERVER = "aicarmine-agentic-loop"

ACTIVE_SERVERS: List[str] = [
    "aicarmine-agentic-loop",
    "aicarmine-repo-code",
]

SERVER_SCRIPTS: Dict[str, Path] = {
    "aicarmine-agentic-loop": PROJECT_ROOT / "services" / "codex_bridge" / "agentic_loop_client_mcp_server.py",
    "aicarmine-repo-code": PROJECT_ROOT / "services" / "codex_bridge" / "repo_code_mcp_server.py",
}

ROUTE_MAP: Dict[str, str] = {
    "get_health": "aicarmine-agentic-loop",
    "get_capabilities": "aicarmine-agentic-loop",
    "run_agent": "aicarmine-agentic-loop",
    "get_status": "aicarmine-agentic-loop",
    "get_result": "aicarmine-agentic-loop",
    "get_file": "aicarmine-repo-code",
    "read_file": "aicarmine-repo-code",
    "list_dir": "aicarmine-repo-code",
}

DEFAULT_ENV = {
    "AICARMINE_CODEX_MCP_REPO_ROOT": ".",
    "AICARMINE_LAB_REPO": ".",
    "AICARMINE_MCP_GZIP_ENABLED": "1",
}
