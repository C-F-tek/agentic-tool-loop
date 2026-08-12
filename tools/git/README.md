# Tools/git

Utilities for local Git automation used by the project application.

## auto_push_generated_data.ps1

Script intended to be called after the local app regenerates technical data such as:

- `indexAI/` project indexes;
- `Tools/npu/*.json` manifests;
- `Tools/npu/*.md` generated context files;
- optional `output/*.json`, `output/*.md`, `output/*.txt` files;
- optional documentation updates.

## Basic usage

From repository root:

```powershell
.\Tools\git\auto_push_generated_data.ps1
```

## Dry run

```powershell
.\Tools\git\auto_push_generated_data.ps1 -DryRun
```

## Include output JSON files

```powershell
.\Tools\git\auto_push_generated_data.ps1 -IncludeOutputJson
```

## Include documentation updates

```powershell
.\Tools\git\auto_push_generated_data.ps1 -IncludeDocs
```

## Include all generated allowlisted areas

```powershell
.\Tools\git\auto_push_generated_data.ps1 -IncludeAllGenerated
```

## Pull before push

Use only when the local branch is expected to fast-forward cleanly:

```powershell
.\Tools\git\auto_push_generated_data.ps1 -PullFirst
```

## Suggested app integration

After the application regenerates indexes or technical JSON files, it can call:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\Tools\git\auto_push_generated_data.ps1 -IncludeOutputJson
```

or, if only `indexAI/` and `Tools/npu/` were updated:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\Tools\git\auto_push_generated_data.ps1
```

## Safety notes

- The script stages only allowlisted generated-data paths.
- The script does not commit if no generated-data changes are staged.
- The script refuses to push from a branch different from `master` unless `-Branch` is changed.
- The script does not perform broad `git add .`.
- Use `-DryRun` before integrating it permanently into the application.
