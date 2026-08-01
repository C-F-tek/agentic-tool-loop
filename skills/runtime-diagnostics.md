# Runtime Diagnostics Skill

## Skill ID
`runtime-diagnostics`

## Description
Competenza di diagnostica runtime: verificare processo, porta, log, sorgente in ordine per diagnosticare guasti runtime.

## MCP Tools Used

| Tool | Purpose |
|------|---------|
| `aicarmine_codex_ops_health` | Verifica salute MCP |
| `aicarmine_service_state_ports` | Verifica porte |
| `aicarmine_service_state_processes` | Verifica processi |
| `aicarmine_service_state_logs` | Verifica log |
| `aicarmine_service_state_snapshot` | Snapshot completo |

## Runtime Workflow

```
Symptom → Check process → Check port → Check log → Check source → Confirm cause
```

## Runtime Checklist

- [ ] Process identity verified
- [ ] Port connectivity confirmed
- [ ] Log state examined
- [ ] Source state checked
- [ ] Configuration validated

## Principles

1. **Process first**: Verificare l'identitа del processo prima di tutto.
2. **Port second**: Confermare la connettivita porta dopo.
3. **Log third**: Esaminare lo stato log dopo.
4. **Source fourth**: Controllare lo stato sorgente dopo.
5. **Configuration fifth**: Validare la configurazione alla fine.