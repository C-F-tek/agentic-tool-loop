# MCP Tool Routing Skill

## Skill ID
`mcp-tool-routing`

## Description
Competenza di routing MCP: preferire lo strumento specializzato che possiede l'operazione, trattare la superficie esposta corrente come autoritativa, documentare i fallback.

## MCP Tools Used

| Tool | Purpose |
|------|---------|
| `aicarmine_codex_ops_health` | Verifica salute MCP |
| `aicarmine_service_state_ports` | Verifica porte |
| `aicarmine_service_state_processes` | Verifica processi |
| `aicarmine_service_state_logs` | Verifica log |
| `aicarmine_service_state_snapshot` | Snapshot completo |

## MCP Servers

| Server | Purpose | Key Tools |
|--------|---------|-----------|
| `aicarmine-codex-app` | Bridge principale | Health, search, read, apply |
| `aicarmine-repo-state` | Stato repository | Status, capabilities |
| `aicarmine-repo-search-det` | Ricerca deterministica | FD, ripgrep, ast-grep |
| `aicarmine-rag` | Conoscenza semantica | Context search, index status |
| `aicarmine-repo-validate` | Validazione | Diffcheck, ruff, pyright |
| `aicarmine-git-readonly` | Operazioni Git | Log, show, diff, blame |
| `aicarmine-sqlite-readonly` | Query database | Schema, query |
| `aicarmine-job-artifact` | Ispezione job | Events, final output |
| `aicarmine-job-view` | Rendering job | Dashboard, events, IA |
| `aicarmine-project-memory` | Memoria persistente | Search, get, upsert |
| `aicarmine-agentic-loop-client` | Agentic loop | Run, status, result |

## Tool Selection Rules

1. **Prefer the specialized tool**: Usare lo strumento MCP che possiede l'operazione.
2. **Treat current surface as authoritative**: Usare lo schema esposto corrente, non conoscenza storica.
3. **No tool invention**: Non assumere che esistano strumenti non presenti nello schema corrente.
4. **Fallback preservation**: Documentare strumenti falliti, argomenti, errori, e motivi del fallback.

## Workflow

```
Task → Identify owner tool → Verify tool availability → Execute → Verify result
```

## Checklist

- [ ] Owner tool identified
- [ ] Tool availability verified
- [ ] Tool executed successfully
- [ ] Result verified
- [ ] Fallback documented if applicable