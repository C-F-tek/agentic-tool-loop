# MCP SERVER DA CREARE PER MIGLIORARE LA CONOSCENZA DELL'AI ASSISTANT

## ANALISI DEGLI STRUMENTI ESISTENTI

### Server MCP che forniscono già conoscenza
| Server | Strumenti | Scopo | Limiti |
|--------|-----------|-------|--------|
| `aicarmine-rag` | search, index_status, reindex | Ricerca semantica su chunk di codice | Non valuta qualità, solo indicizzazione |
| `aicarmine-repo-symbol-index` | symbol_index, symbol_query, symbol_summary | SQLite-based symbol indexing | Solo estrazione simboli, nessuna valutazione |
| `aicarmine-enhanced-analysis` | code_summarize_module, api_surface, config_validator | Code summarizer, API surface, config validation | Strumenti base, nessuna analisi approfondita |
| `aicarmine-code-dep-graph` | build_dep_graph, find_import_chains, detect_circular_deps | Dependency graph analysis | Solo dipendenze import, nessuna analisi semantica |
| `aicarmine-wily` | wily_report, wily_rank, ast_complexity_report | Complessità ciclomatica | Solo metriche, nessun contesto business |
| `aicarmine-project-memory` | search, get, upsert_verified, mark_stale | Memoria persistente | Dipende da input umano, non auto-generata |
| `aicarmine-index-bridge` | build_bridge, query_unified, persist_memory | Cross-reference RAG + Symbol Index | Solo unione database, nessuna analisi |

## MCP SERVER DA CREARE (SIMILI A RAG MA CON STRUMENTI AGGIUNTIVI)

### 1. DOCUMENTATION QUALITY SCANNER MCP SERVER

**Differenza dal RAG:** Il RAG indicizza tutto il codice sorgente. Questo server indicizzerebbe SOLO la documentazione tecnica, valutando qualità e consistenza.

**Strumenti proposti:**
```
- doc_quality_scan(path, min_docstring_coverage=0.8)
  → Valuta: completezza docstrings, consistenza formattazione, link rotti, content outdated
- doc_coverage_map(module)
  → Mappa: quali moduli/classi/functions hanno documentazione e quali no
- doc_api_sync(api_surface, code_base)
  → Confronta docstrings con codice reale, identifica discrepanze
- doc_search(query, scope="all")
  → Ricerca semantica nella documentazione (simile a RAG ma solo docs)
- doc_recommendations(module)
  → Suggerimenti specifici per migliorare documentazione
```

**Output strutturato:**
```json
{
  "file": "services/aicarmine_broker/app.py",
  "docstring_coverage": 0.65,
  "missing_docs": ["AppConfig", "main()"],
  "inconsistent_formatting": 3,
  "broken_links": 1,
  "outdated_content": 2,
  "quality_score": 6.2,
  "recommendations": [
    "Add docstring to AppConfig class",
    "Fix inconsistent parameter documentation in main()",
    "Update outdated example in README.md"
  ]
}
```

### 2. TEST COVERAGE ANALYZER MCP SERVER

**Differenza da test_discovery:** Esiste già `test_discovery_mcp_server.py` ma manca l'analisi di copertura e dei gap.

**Strumenti proposti:**
```
- test_coverage_report(module, format="json")
  → Genera report di copertura per file/moduli
- test_gap_finder(module, min_coverage=0.8)
  → Identifica codice non testato o poco testato
- test_pattern_discovery(test_dir)
  → Scopre pattern di test nel progetto
- test_uncovered_search(query, module)
  → Cerca codice specifico non coperto da test
- test_scaffold_generator(module, style="pytest")
  → Genera scaffold di test per codice non testato
```

**Output strutturato:**
```json
{
  "module": "services/aicarmine_broker/tools/",
  "file_coverage": {
    "repo_list_files.py": {"lines": 85, "functions": 60},
    "repo_search.py": {"lines": 70, "functions": 40},
    "repo_tree.py": {"lines": 90, "functions": 75}
  },
  "untested_functions": [
    {"file": "repo_list_files.py", "function": "_validate_config", "reason": "no_test_found"},
    {"file": "repo_search.py", "function": "_extract_matches", "reason": "coverage_below_threshold"}
  ],
  "coverage_gap_score": 3.2,
  "recommended_tests": [
    {"file": "test_repo_list_files.py", "tests": ["test_valid_path", "test_invalid_path", "test_gitignore_respected"]},
    {"file": "test_repo_search.py", "tests": ["test_rg_mode", "test_fd_mode", "test_no_matches"]}
  ]
}
```

### 3. SECURITY AUDIT SCANNER MCP SERVER

**Differenza da security_mcp_server:** Esiste `security_mcp_server.py` ma va verificata la completezza degli strumenti.

**Strumenti proposti:**
```
- security_scan(module, severity="medium")
  → Scansiona per hardcoded secrets, SQL injection, XSS, path traversal
- secret_detector(file_patterns=["*.py", "*.env", "*.json"])
  → Cerca chiavi API, token, password in chiaro
- dependency_audit(requirements_file="requirements.txt")
  → Analizza dipendenze per vulnerabilità note
- permission_analysis(entry_points)
  → Mappa permessi e accessi nel codice
- secure_code_review(code_product)
  → Review automatica di code product proposals per security
```

**Output strutturato:**
```json
{
  "scan_result": {
    "hardcoded_secrets": [
      {"file": "services/config/settings.py", "line": 42, "type": "API_KEY", "severity": "high"}
    ],
    "sql_injection_risks": [
      {"file": "services/aicarmine_broker/tools/repo_search.py", "line": 150, "query": "f-string in SQL"}
    ],
    "xss_risks": [],
    "path_traversal_risks": [
      {"file": "services/codex_bridge/mcp_server.py", "line": 300, "path": "user_input"}
    ],
    "dependency_vulnerabilities": [
      {"package": "requests", "version": "2.28.0", "vulnerability": "CVE-2023-xxxx", "severity": "medium"}
    ],
    "overall_security_score": 7.5
  }
}
```

### 4. KNOWLEDGE GRAPH BUILDER MCP SERVER

**Differenza dal RAG:** Il RAG fa ricerca semantica su chunk di codice. Questo costruisce un GRAFO STRUTTURATO di concetti e relazioni per navigazione concettuale.

**Strumenti proposti:**
```
- knowledge_graph_build(repo_root, output_format="sqlite")
  → Costruisce grafo di concetti, relazioni, dipendenze
- knowledge_graph_query(graph_id, query)
  → Query sul grafo della conoscenza
- concept_map(module)
  → Mappa concetti principali del progetto
- relationship_finder(module, depth=2)
  → Trova relazioni tra moduli/classi/funzioni
- knowledge_summary(project)
  → Genera summary della conoscenza del progetto
```

**Output strutturato:**
```json
{
  "knowledge_graph": {
    "nodes": [
      {"id": "broker", "type": "module", "label": "AICarmine Broker"},
      {"id": "planner", "type": "module", "label": "Planner Loop"},
      {"id": "mcp_server", "type": "module", "label": "MCP Server"},
      {"id": "ToolResult", "type": "class", "label": "ToolResult"}
    ],
    "edges": [
      {"from": "planner", "to": "broker", "relation": "depends_on"},
      {"from": "mcp_server", "to": "broker", "relation": "imports"},
      {"from": "planner", "to": "ToolResult", "relation": "uses"}
    ],
    "concept_clusters": [
      {"cluster": "tool_execution", "modules": ["dispatcher", "tool_result", "decision"]},
      {"cluster": "mcp_infrastructure", "modules": ["mcp_server", "repo_mcp_common", "jsonrpc"]}
    ]
  }
}
```

### 5. API SURFACE ANALYZER MCP SERVER

**Differenza da enhanced_analysis:** Esiste `APISurfaceManager` in `enhanced_analysis_mcp_server.py` ma va integrato come server standalone con più strumenti.

**Strumenti proposti:**
```
- api_surface_extract(entry_point, include_private=False)
  → Estrae tutte le API pubbliche da FastAPI, MCP, HTTP endpoints
- api_relationship_map(api_surface)
  → Mappa relazioni tra API
- api_deprecation_tracker(code_base)
  → Traccia API deprecate e migration path
- api_contract_validator(api_surface, docs)
  → Valida contratti API contro documentazione
- breaking_change_detector(current_api, previous_api)
  → Identifica potenziali breaking changes
```

**Output strutturato:**
```json
{
  "api_surface": {
    "public_endpoints": [
      {"name": "aicarmine_repo_list_files", "type": "MCP tool", "params": ["path", "max_files"], "returns": "dict"},
      {"name": "aicarmine_repo_search", "type": "MCP tool", "params": ["query", "mode", "path"], "returns": "dict"}
    ],
    "internal_apis": [
      {"name": "_validate_config", "module": "repo_list_files.py", "visibility": "private"}
    ],
    "deprecated_apis": [],
    "api_consistency_score": 8.5
  }
}
```

### 6. CONFIGURATION VALIDATOR MCP SERVER

**Differenza da enhanced_analysis:** Esiste `ConfigValidatorManager` in `enhanced_analysis_mcp_server.py` ma va estratto come server standalone.

**Strumenti proposti:**
```
- config_validate(config_files)
  → Valida JSON, YAML, TOML, env files
- config_consistency_check(config_set)
  → Controlla consistenza tra config files
- config_env_audit(env_file, code_usage)
  → Audit variabili ambiente vs uso reale
- config_migration_helper(old_config, new_schema)
  → Genera migration per config updates
- config_template_generator(config_type)
  → Genera template per nuove configurazioni
```

**Output strutturato:**
```json
{
  "validation_result": {
    "valid_files": ["services/config/settings.json", ".venvmapping.env"],
    "invalid_files": [
      {"file": "services/config/broken.yaml", "errors": ["missing_required_field", "invalid_type"]}
    ],
    "consistency_issues": [
      {"config1": "settings.json", "config2": "env.json", "issue": "different_port_values"}
    ],
    "environment_audit": {
      "defined_but_unused": ["AICARMINE_UNUSED_VAR"],
      "used_but_not_defined": ["AICARMINE_MISSING_VAR"]
    }
  }
}
```

### 7. PERFORMANCE PROFILER MCP SERVER

**Differenza da wily:** Esiste `wily_mcp_server.py` per complessità ma manca il profiling runtime.

**Strumenti proposti:**
```
- performance_profile(function_path, iterations=100)
  → Profila funzioni per tempo di esecuzione
- memory_leak_detector(object_tracking=True)
  → Identifica potenziali memory leak
- slow_query_finder(db_connections)
  → Trova query/database operations lente
- complexity_report(module, include_nesting=True)
  → Report di complessità ciclomatica (simile a Wily ma più dettagliato)
- optimization_suggestions(code_base)
  → Suggerimenti di ottimizzazione basati su pattern
```

**Output strutturato:**
```json
{
  "performance_report": {
    "slow_functions": [
      {"function": "repo_search", "module": "services/codex_bridge/", "avg_time_ms": 45.2, "p99_time_ms": 120.5},
      {"function": "build_dep_graph", "module": "code_dep_graph_mcp_server.py", "avg_time_ms": 89.7, "p99_time_ms": 250.3}
    ],
    "memory_leak_risks": [
      {"file": "rag_mcp_server.py", "line": 200, "issue": "unbounded_cache_growth"}
    ],
    "optimization_suggestions": [
      {"file": "planner/loop.py", "suggestion": "Replace linear search with binary search in _find_matching_events"},
      {"file": "mcp_server.py", "suggestion": "Add caching for _resolve_project_root calls"}
    ]
  }
}
```

## PRIORITÀ DI IMPLEMENTAZIONE

| Priorità | Server | Impatto sulla Conoscenza | Tempo Stimato |
|----------|--------|-------------------------|---------------|
| 1 | Knowledge Graph Builder | Alta — Navigazione concettuale strutturata | 2-3 giorni |
| 2 | Documentation Quality Scanner | Alta — Migliora comprensione architetturale | 1-2 giorni |
| 3 | Test Coverage Analyzer | Alta — Identifica aree non testate | 1-2 giorni |
| 4 | Security Audit Scanner | Media — Sicurezza del codice | 2-3 giorni |
| 5 | API Surface Analyzer | Media — Documentazione API | 1 giorno |
| 6 | Configuration Validator | Media — Validazione config | 1 giorno |
| 7 | Performance Profiler | Bassa — Ottimizzazione | 2-3 giorni |

## CONFRONTO CON RAG ESISTENTE

| Aspetto | RAG Esistente | Nuovi Server |
|---------|--------------|--------------|
| Scopo | Ricerca semantica su chunk di codice | Valutazione, analisi, navigazione |
| Output | Testi indicizzati | Metriche, grafici, report |
| Qualità | Nessuna valutazione | Valutazione automatica |
| Struttura | Chunk flat | Grafi, mappe, relazioni |
| Azione | Ricerca passiva | Raccomandazioni attive |

## IMPLEMENTAZIONE TECNICA

Ognuno di questi server può essere implementato come MCP stdio server simile a `rag_mcp_server.py`:

```python
# services/codex_bridge/knowledge_graph_mcp_server.py
#!/usr/bin/env python3
"""MCP server for knowledge graph construction and querying."""

from repo_mcp_common import (
    ToolSpec,
    health_payload,
    object_schema,
    serve,
)

SERVER_NAME = "aicarmine-knowledge-graph-mcp"
SERVER_VERSION = "1.0.0"

def _tools() -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}
    
    def health(args: dict[str, Any], root):
        return health_payload(SERVER_NAME, list(tools))
    
    tools["aicarmine_knowledge_graph_build"] = ToolSpec(
        name="aicarmine_knowledge_graph_build",
        description="Build knowledge graph from repository",
        input_schema=object_schema("graph_id", "repo_root"),
        handler=_build_graph,
    )
    
    tools["aicarmine_knowledge_graph_query"] = ToolSpec(
        name="aicarmine_knowledge_graph_query",
        description="Query knowledge graph",
        input_schema=object_schema("graph_id", "query"),
        handler=_query_graph,
    )
    
    return tools

def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    tools = _tools()
    return serve(SERVER_NAME, SERVER_VERSION, tools)

if __name__ == "__main__":
    raise SystemExit(main())
```

## SINTESI

Il server RAG attuale indicizza il codice sorgente per ricerca semantica. I server proposti sopra complementano il RAG fornendo:
- **Valutazione qualità** (non solo indicizzazione)
- **Analisi strutturale** (test coverage, security, config)
- **Navigazione concettuale** (knowledge graph)
- **Documentazione focalizzata** (doc-specific search)
- **Performance analysis** (profiling runtime)

Ognuno di questi può essere implementato come MCP stdio server simile a `rag_mcp_server.py`, con tool specifici e output strutturato JSON.