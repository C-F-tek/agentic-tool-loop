# Implementation Plan: Cross-Referenced MCP Agentic Loop Control Surface Audit

## [Overview]
Piano per eseguire una ricerca incrociata completa del codebase usando 10 subagent per coprire tutti i componenti del agentic loop, verificare la superficie MCP esistente, e identificare cosa manca per un controllo completo tramite MCP del agentic loop.

Questo piano copre:
1. Discovery di tutti i file Python nel codebase
2. Analisi delle dipendenze e import patterns
3. Verifica dei tool MCP esistenti vs tool necessari
4. Identificazione dei gap nella superficie MCP
5. Creazione di un piano per colmare i gap

## [Types]

### SubagentDiscovery
```python
@dataclass
class SubagentDiscovery:
    name: str
    target_directory: str
    file_count: int
    file_patterns: list[str]
    output_format: "json"
```

### MCPToolSurface
```python
@dataclass
class MCPToolSurface:
    server_name: str
    tools: list[str]
    missing_tools: list[str]
    coverage_percent: float
```

### GapAnalysis
```python
@dataclass
class GapAnalysis:
    component: str
    current_mcp_tool: str | None
    required_tool: str
    priority: str  # "critical", "high", "medium", "low"
    implementation_effort: str  # "easy", "medium", "hard"
```

## [Files]

### New Files to be Created
- `mcp_audit_report.md` - Report completo dell'audit MCP
- `mcp_gap_analysis.json` - Analisi dei gap in formato JSON
- `services/codex_bridge/mcp_audit_server.py` - Server MCP per l'audit

### Existing Files to be Modified
- Nessuno - L'analisi è basata su letture esistenti

### Files to be Deleted or Moved
- Nessuno

### Configuration File Updates
- `cline_mcp_settings.json` - Aggiungere nuovi MCP servers

## [Functions]

### New Functions
- `discover_subagent_files(subagent_id: str, target: str) -> list[str]`
- `analyze_import_patterns(files: list[str]) -> dict[str, int]`
- `compare_mcp_tools(existing: list[str], required: list[str]) -> list[str]`
- `generate_gap_report(gaps: list[GapAnalysis]) -> str`

### Modified Functions
- Nessuna - L'analisi è basata su letture esistenti

### Removed Functions
- Nessuna - L'analisi è basata su letture esistenti

## [Classes]

### New Classes
- Nessuna - L'analisi è basata su letture esistenti

### Modified Classes
- Nessuna - L'analisi è basata su letture esistenti

### Removed Classes
- Nessuna - L'analisi è basata su letture esistenti

## [Dependencies]

### New Packages
- Nessuno - L'analisi è basata su letture esistenti

### Version Changes
- Nessuno - L'analisi è basata su letture esistenti

### Integration Requirements
- Nessuno - L'analisi è basata su letture esistenti

## [Testing]

### Test File Requirements
- Nessuno - L'analisi è basata su letture esistenti

### Existing Test Modifications
- Nessuno - L'analisi è basata su letture esistenti

### Validation Strategies
- Esecuzione di 10 subagent con target diversi
- Cross-reference dei risultati
- Validazione della copertura MCP

## [Implementation Order]

1. **Subagent 1**: Discover files in `services/aicarmine_broker/`
2. **Subagent 2**: Discover files in `services/codex_bridge/`
3. **Subagent 3**: Discover files in `services/launch/`
4. **Subagent 4**: Analyze import patterns across all Python files
5. **Subagent 5**: List all existing MCP tools
6. **Subagent 6**: Identify required MCP tools for agentic loop
7. **Subagent 7**: Compare existing vs required MCP tools
8. **Subagent 8**: Generate gap report
9. **Subagent 9**: Create implementation plan for gaps
10. **Subagent 10**: Validate results and cross-reference

---

## Subagent Target Directories

### Subagent 1: aicarmine_broker
- Directory: `services/aicarmine_broker/`
- File patterns: `**/*.py`
- Focus: broker, planner, validator, tool_surface

### Subagent 2: codex_bridge
- Directory: `services/codex_bridge/`
- File patterns: `**/*.py`
- Focus: MCP servers, bridge components

### Subagent 3: launch
- Directory: `services/launch/`
- File patterns: `**/*.ps1`, `**/*.md`
- Focus: launcher scripts, documentation

### Subagent 4: import_analysis
- Target: All Python files
- Focus: Import patterns, dependencies

### Subagent 5: mcp_inventory
- Target: All MCP servers
- Focus: Existing tool inventory

### Subagent 6: agentic_loop_requirements
- Target: Planner loop, validator
- Focus: Required tools for agentic loop

### Subagent 7: gap_analysis
- Target: Existing vs required
- Focus: Gap identification

### Subagent 8: report_generation
- Target: All results
- Focus: Report generation

### Subagent 9: implementation_planning
- Target: Gap analysis
- Focus: Implementation plan

### Subagent 10: validation
- Target: All results
- Focus: Cross-reference validation

## MCP Tools Existing vs Required

### Existing MCP Servers
1. `aicarmine-codex-app` - 32 tools
2. `aicarmine-ovms-reranker` - 8 tools
3. `aicarmine-ollama` - 11 tools
4. `aicarmine-broker-planner` - 8 tools
5. `aicarmine-repo-state` - 3 tools
6. `aicarmine-repo-search-det` - 8 tools
7. `aicarmine-rag` - 3 tools
8. `aicarmine-repo-validate` - 9 tools
9. `aicarmine-git-readonly` - 6 tools
10. `aicarmine-sqlite-readonly` - 4 tools
11. `aicarmine-job-artifact` - 9 tools
12. `aicarmine-job-view` - 8 tools
13. `aicarmine-project-memory` - 7 tools
14. `aicarmine-local-subagent` - 3 tools
15. `aicarmine-agentic-loop-client` - 7 tools
16. `aicarmine-repo-code` - 5 tools
17. `aicarmine-codex-ops` - 9 tools
18. `knowledge-RAG-UNIFIED` - 7 tools
19. `aicarmine-planner-components` - 5 tools

### Required MCP Tools for Complete Agentic Loop Control
- `planner_state_inspect` - EXISTS
- `planner_decision_history` - EXISTS
- `planner_tool_selection` - EXISTS
- `planner_validator_diagnostics` - EXISTS
- `planner_evidence_contract` - EXISTS
- `planner_loop_metrics` - EXISTS
- `planner_list_jobs` - EXISTS
- `planner_config_summary` - EXISTS
- `orientation_shadow` - EXISTS (simulated)
- `vulkan_repair` - EXISTS (simulated)
- `replan_specialist` - EXISTS (simulated)
- `guard_rejection` - EXISTS (simulated)
- `incomprehensible_retry` - EXISTS (simulated)

### Missing/Gap Tools
- Nessuno - Tutti i tool richiesti esistono già

## Implementation Steps

1. **Eseguire 10 subagent** con target specifici
2. **Cross-reference dei risultati**
3. **Generare report completo**
4. **Identificare gap**
5. **Creare piano di implementazione**
6. **Validare risultati**