# Launch — Launch Scripts

> **Purpose**: Launch scripts for starting broker, agent, and related services. PowerShell-based startup automation.

---

## Files

| File | Purpose | Key Types/Functions |
|------|---------|----------------------|
| `start-agent.ps1` | Start agent script | Starts broker on port 3571 |
| `run-agent.ps1` | Run agent script | Runs agent with configuration |
| `set_mcp_env_vars.ps1` | Set MCP env vars | Configures MCP environment |

---

## Quick Start

```powershell
# Start the agent
powershell -File services/launch/start-agent.ps1

# Set MCP environment variables
powershell -File services/launch/set_mcp_env_vars.ps1
```

---

## Documentation Index

| Document | Location |
|----------|----------|
| [Complete Services Index](../../docs/SERVICES_INDEX.md) | Full file-by-file documentation |

---

*Generated from analysis of the C:\Users\carmi\AI workspace.*