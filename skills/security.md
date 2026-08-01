# Security Skill

## Skill ID
`security`

## Description
Competenza di sicurezza basata su autorizzazione esplicita, cambiamenti reversibili, e disciplina delle evidenze separate.

## MCP Tools Used

| Tool | Purpose |
|------|---------|
| `aicarmine_repo_validate_semgrep` | Scansione sicurezza statica |
| `aicarmine_repo_validate` | Validazione repository |
| `aicarmine_repo_search` | Ricerca contenuti sensibili |
| `aicarmine_git_readonly_log` | Audit trail Git |
| `aicarmine_git_readonly_diff` | Ispezione modifiche |

## Security Boundaries

| Action | Authorization Required |
|--------|----------------------|
| Deletion | Explicit |
| Force-push | Explicit |
| Merge to protected branch | Explicit |
| Production deployment | Explicit |
| Visibility changes | Explicit |
| Permission changes | Explicit |
| Secret/credential changes | Explicit |
| Billing changes | Explicit |

## Checklist

- [ ] No secrets or credentials in diffs
- [ ] No permission or visibility changes without approval
- [ ] No production deployment without approval
- [ ] All changes reversible via Git
- [ ] Security scan results documented

## Principles

1. **No explicit authorization = no sensitive operations**: Nessuna operazione sensibile senza esplicito consenso.
2. **Reversible changes only**: Tutte le modifiche devono essere reversibili.
3. **Evidence isolation**: Sintomi, ipotesi, e evidenze devono essere separati dalle decisioni di sicurezza.