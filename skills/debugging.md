# Debugging Skill

## Skill ID
`debugging`

## Description
Competenza di debugging scientifico basata sul metodo forense: Sintomo → Evidenza → Causa confermata → Fix minimo → Verifica.

## MCP Tools Used

| Tool | Purpose |
|------|---------|
| `aicarmine_git_readonly_log` | Revisione commit history |
| `aicarmine_git_readonly_diff` | Ispezione modifiche |
| `aicarmine_git_readonly_blame` | Line-level blame |
| `aicarmine_service_state_logs` | Lettura log file |
| `aicarmine_service_state_processes` | Verifica processi |
| `aicarmine_service_state_ports` | Verifica porte |
| `aicarmine_job_view_render` | Render job view |
| `aicarmine_job_artifact_events` | Lettura eventi job |

## Debugging Workflow

```
Symptom → Evidence → Confirmed cause → Minimal fix → Verification
```

## Checklist

- [ ] Symptom clearly documented
- [ ] Multiple hypotheses considered
- [ ] Evidence gathered from runtime/source/Git
- [ ] Cause confirmed, not just hypothesized
- [ ] Fix is minimal and reversible
- [ ] Original symptom verified as resolved
- [ ] Residual risks documented

## Principles

1. **Evidence over speculation**: Preferire evidenza dimostrata da spiegazioni plausibili.
2. **Multiple hypotheses**: Considerare tutte le cause plausibili prima di agire.
3. **Discriminating tests**: Ogni test dovrebbe eliminare almeno un'ipotesi.
4. **Minimal intervention**: Fare la piu piccola correzione possibile.
5. **Reversibility**: Tutte le modifiche devono essere reversibili.
6. **Verification**: Confermare il fix risolve il sintomo.