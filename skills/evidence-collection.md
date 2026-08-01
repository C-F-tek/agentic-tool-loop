# Evidence Collection Skill

## Skill ID
`evidence-collection`

## Description
Competenza di raccolta evidenze forensi: raccogliere, preservare, e analizzare evidenze da source, runtime, Git, e MCP tools.

## MCP Tools Used

| Tool | Purpose |
|------|---------|
| `aicarmine_git_readonly_log` | Commit history evidence |
| `aicarmine_git_readonly_show` | Commit diff evidence |
| `aicarmine_git_readonly_diff` | Working tree diff evidence |
| `aicarmine_git_readonly_blame` | Line blame evidence |
| `aicarmine_repo_read` | Multi-file read evidence |
| `aicarmine_repo_search` | Content search evidence |
| `aicarmine_service_state_snapshot` | Full runtime snapshot |

## Evidence Workflow

```
Identify need → Collect evidence → Preserve evidence → Analyze evidence → Document findings
```

## Evidence Types

| Type | Description | Source |
|------|-------------|--------|
| Source evidence | Code, configuration, comments | Repository files |
| Runtime evidence | Process, port, log state | Running services |
| Git evidence | Commits, diffs, blame | Git history |
| MCP evidence | Tool outputs, schemas | MCP tools |
| Database evidence | Query results | SQLite databases |

## Evidence Checklist

- [ ] Evidence identified as source/runtime/Git/MCP
- [ ] Evidence collected from authoritative source
- [ ] Evidence preserved with timestamp
- [ ] Evidence analyzed without modification
- [ ] Findings documented with evidence references

## Principles

1. **Authoritative source only**: Usare solo fonti authoritative per le evidenze.
2. **Preserve evidence**: Preservare le evidenze senza modificarle.
3. **Timestamp evidence**: Documentare quando le evidenze sono state raccolte.
4. **Multiple evidence types**: Combinare source, runtime, Git, e MCP evidence.
5. **Evidence over speculation**: Preferire evidenza dimostrata su spiegazioni plausibili.