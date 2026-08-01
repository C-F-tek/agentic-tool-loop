# Hypothesis Testing Skill

## Skill ID
`hypothesis-testing`

## Description
Competenza di testing ipotesi: formulare, testare, e confermare ipotesi con test discriminanti.

## MCP Tools Used

| Tool | Purpose |
|------|---------|
| `aicarmine_repo_search_fd` | File discovery test |
| `aicarmine_repo_search_rg` | Content search test |
| `aicarmine_repo_search_ast_grep` | AST semantic test |
| `aicarmine_repo_search_ctags` | Symbol extraction test |
| `aicarmine_repo_read` | Multi-file read test |

## Hypothesis Workflow

```
Form hypothesis → Design discriminating test → Execute test → Analyze results → Confirm/reject hypothesis
```

## Hypothesis Types

| Type | Description | Test Method |
|------|-------------|-------------|
| Code hypothesis | Code behavior hypothesis | Source analysis |
| Runtime hypothesis | Runtime behavior hypothesis | Process/port/log checks |
| Git hypothesis | Git history hypothesis | Log/diff/blame analysis |
| MCP hypothesis | MCP tool availability hypothesis | Tool schema verification |

## Hypothesis Checklist

- [ ] Hypothesis clearly stated
- [ ] At least 2 hypotheses considered
- [ ] Each hypothesis has a discriminating test
- [ ] Test executed without modifying source
- [ ] Results analyzed against hypothesis
- [ ] Hypothesis confirmed or rejected with evidence
- [ ] Next hypothesis identified if needed

## Principles

1. **Multiple hypotheses**: Considerare almeno 2 ipotesi prima di agire.
2. **Discriminating tests**: Ogni test dovrebbe eliminare almeno un'ipotesi.
3. **No source modification**: Non modificare la sorgente durante il testing.
4. **Evidence over speculation**: Preferire evidenza dimostrata su spiegazioni plausibili.
5. **Iterative testing**: Continuare con la prossima ipotesi se necessaria.