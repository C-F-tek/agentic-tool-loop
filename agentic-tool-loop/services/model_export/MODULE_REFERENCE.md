<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_START -->
Regole operative non negoziabili:
1. Il contratto non va modificato se non richiesto da Carmine esplicitamente.
2. Il prodotto finale puo' essere arricchito come gia' viene fatto; non cambiare logica senza richiesta esplicita.
3. Non devi presupporre nulla: non e' il tuo compito.
<!-- AICARMINE_NON_NEGOTIABLE_CONTRACT_END -->
# model_export Module Reference

Updated: 2026-06-01

`model_export` contains CLI-oriented model export implementation. It is not part
of the 3571/3572 agentic loop, but launcher/OpenVINO configuration can share the
same machine-wide environment. Keep export dependencies and runtime service
venvs separate.

## Module Map

| Module | Technical description |
| --- | --- |
| `__init__.py` | Package marker for export implementation. |
| `cli.py` | Main export CLI. It defines arguments and exporters for text generation, embeddings, rerank, text-to-speech, speech-to-text and image generation, plus tokenizer export and serving config updates. It owns most implementation detail. |
| `config.py` | Compatibility surface for config/parser helpers that still live in `cli.py`. Keep stable for old imports. |
| `exporters.py` | Lazy compatibility layer exposing historical exporter function names. It imports actual functions from `cli.py` on demand to avoid unnecessary import-time dependency cost. |

## Operational Notes

- Run through `export_model.py` or package CLI depending on the calling script.
- Export output paths can modify model directories and serving config. Verify
  target path before executing.
- OpenVINO/Python dependencies may differ from `venvs/labtools` and
  `venvs/openwebui`. Do not solve service runtime import bugs by changing model
  export env unless evidence points there.

## Safe Edit Checklist

1. Identify the exact exporter branch used by the requested model family.
2. Verify parser arguments and generated paths before modifying output logic.
3. Keep lazy compatibility exports intact.
4. Run syntax checks on `services\model_export` after edits.

