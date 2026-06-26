# Config Module — Configuration Management

> **Purpose**: Configuration loading, parsing, validation, and type-safe config objects.

---

## Files

| File | Purpose | Key Types |
|------|---------|-----------|
| `__init__.py` | Package init, re-exports | Star import from submodules |
| `models.py` | BrokerConfig frozen dataclass | `BrokerConfig` with all fields |
| `env_loader.py` | Environment variable parsing | Parse `AICARMINE_*` vars |
| `compatibility.py` | Legacy constants | `FINAL_QUALITY_ROUTE_TOOLS` |
| `entry_points_config.py` | Entry point configuration | Entry point mappings |

---

## BrokerConfig (`config/models.py`)

```python
@dataclass(frozen=True)
class BrokerConfig:
    service_name: str
    app_title: str
    app_version: str
    app_description: str
    vulkan_agent_path: str
    jobs_index_path: str
    # ... all config fields typed
```

### Properties

| Property | Returns | Description |
|----------|---------|-------------|
| `health_endpoint` | `str` | Health check URL |
| `agent_public_base_url` | `str` | Base URL for agent |

---

## Documentation Index

| Document | Location |
|----------|----------|
| [Complete Services Index](../../docs/SERVICES_INDEX.md) | Full file-by-file documentation |
| [Python Refactoring Guide](../../docs/PYTHON_REFACTORING_GUIDE.md) | Config as dataclass pattern (§4) |

---

*Generated from analysis of the C:\Users\carmi\AI workspace.*