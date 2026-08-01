# Patch and Change Management Skill

## Skill ID
`patch-management`

## Description
Competenza di gestione patch: validare, apply-check, applicare, verificare workflow. Preferire structured_edit su unified_diff.

## MCP Tools Used

| Tool | Purpose |
|------|---------|
| `aicarmine_repo_code_propose_edit` | Proposta modifica strutturata |
| `aicarmine_repo_code_unidiff_validate` | Validazione diff unificato |
| `aicarmine_repo_code_git_apply_check` | Verifica applicabilita diff |
| `aicarmine_repo_code_apply_patch` | Applicazione patch |

## Patch Workflow

```
Proposal → Validation → Apply-check → Apply → Verify
```

## Patch Types

| Type | Use Case | Method |
|------|----------|--------|
| structured_edit | Multi-file changes | Preferred per la maggior parte delle modifiche |
| unified_diff | Complete file changes | Quando il diff completo esiste gia |
| old_text/new_text | Targeted replacements | Modifiche mirate piccole |

## Patch Checklist

- [ ] Change proposal documented
- [ ] Diff validated before application
- [ ] Apply-check passed
- [ ] Patch applied with confirmation
- [ ] Resulting diff inspected
- [ ] Line count reported
- [ ] Original symptom verified

## Principles

1. **Validate first**: Validare il diff prima di applicare.
2. **Apply-check second**: Passare apply-check prima dell'applicazione.
3. **Apply third**: Applicare la patch con conferma.
4. **Verify fourth**: Verificare il risultato dopo.
5. **Line count after**: Riportare il conteggio linee dopo ogni modifica.