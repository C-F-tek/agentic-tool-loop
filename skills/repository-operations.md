# Repository Operations Skill

## Skill ID
`repository-operations`

## Description
Competenza di operazioni repository: confermare lo stato prima di modificare, verificare dopo, identificare il repository root effettivo.

## MCP Tools Used

| Tool | Purpose |
|------|---------|
| `aicarmine_repo_list_files` | Listatura file |
| `aicarmine_repo_search` | Ricerca contenuti |
| `aicarmine_repo_read` | Lettura file |
| `aicarmine_repo_apply_patch` | Applicazione patch |
| `aicarmine_repo_validate` | Validazione repository |
| `aicarmine_repo_git_apply_check` | Verifica applicazione |

## Repository Startup Checklist

- [ ] Effective repository root identified
- [ ] Root AGENTS.md read
- [ ] Directory-specific AGENTS.md checked
- [ ] Required contracts read
- [ ] Branch, commit, working-tree state confirmed
- [ ] Runtime environment verified

## Workflow

```
Identify root → Read AGENTS.md → Check contracts → Confirm state → Execute → Verify
```

## Principles

1. **Repository root first**: Identificare sempre il repository root effettivo.
2. **State before editing**: Confermare lo stato prima di modificare.
3. **Line count after**: Riportare il conteggio linee dopo ogni modifica.
4. **Diff before apply**: Ispezionare il diff prima di applicare.