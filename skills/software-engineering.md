# Software Engineering Skill

## Skill ID
`software-engineering`

## Description
Competenza di ingegneria del software basata su evidenze concrete, modifiche minime reversibili, e disciplina del componente proprietario.

## MCP Tools Used

| Tool | Purpose |
|------|---------|
| `aicarmine_repo_code_propose_edit` | Proposta di modifica strutturata codice |
| `aicarmine_repo_code_unidiff_validate` | Validazione diff unificato |
| `aicarmine_repo_code_git_apply_check` | Verifica applicabilita diff senza applicare |
| `aicarmine_repo_code_apply_patch` | Applicazione patch validate |
| `aicarmine_repo_search_fd` | Ricerca file deterministica |
| `aicarmine_repo_search_rg` | Ricerca contenuti ripgrep |
| `aicarmine_repo_search_ast_grep` | Ricerca semantica AST |
| `aicarmine_repo_search_ctags` | Estrazione simboli ctags |
| `aicarmine_repo_search_tree_sitter_parse` | Parsing tree-sitter |

## Workflow

```
Requirement → Evidence gathering → Owner identification → Minimal change → Diff validation → Verification
```

## Checklist

- [ ] Change affects only the targeted component
- [ ] No unrelated code reformatting
- [ ] Diff validated before application
- [ ] Line count reported for modified files
- [ ] Original symptom verified after change

## Principles

1. **Evidence-first**: Ogni modifica deve essere backed da evidenza concreta source/runtime/Git.
2. **Minimal reversible correction**: Preferire la piu piccola correzione contract-preserving.
3. **Owner-component discipline**: Modificare l'implementazione owner esistente, non wrapper o workaround.
4. **Windows-first**: Assumere Windows/PowerShell salvo esplicita richiesta diversa.