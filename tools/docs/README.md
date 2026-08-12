# Tools/docs — Markdown/code coherence

Strumenti locali per confrontare documentazione Markdown e codice reale.

## Comandi

```powershell
python .\Tools\docs\build_code_aware_md_coherence.py --repo-root . --max-lines 400
python .\Tools\docs\apply_md_code_coherence_refactor.py --repo-root . --apply
python .\Tools\validation\check_md_code_coherence.py --repo-root . --max-high 0
```

Gli output completi vanno sotto `output/validation/**` e non devono essere committati.
