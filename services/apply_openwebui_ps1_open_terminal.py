#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patch openwebui.ps1 so Open Terminal replaces JupyterLab at launcher level.

Use cases:
  python apply_openwebui_ps1_open_terminal.py --zip "proggetto aggiornato.zip"
  python apply_openwebui_ps1_open_terminal.py --root "C:\\path\\to\\extracted\\project"
  python apply_openwebui_ps1_open_terminal.py --ps1 "C:\\path\\to\\openwebui.ps1"

What it does:
  - finds openwebui.ps1;
  - creates a timestamped backup;
  - injects an idempotent PowerShell helper;
  - replaces Jupyter/JupyterLab launcher lines with Start-AICOpenTerminal;
  - if no Jupyter line exists, inserts Start-AICOpenTerminal before OpenWebUI startup;
  - for zip input, writes a new "*-open-terminal-patched.zip" unless --in-place is used.

The generated PowerShell block:
  - uses the same token if it can read it from the old Jupyter command or env vars;
  - starts in AICARMINE_LAB_REPO, matching the repo tool workspace;
  - starts open-terminal directly, not JupyterLab.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable, Optional, Tuple


MARK_START = "# >>> AIC_OPEN_TERMINAL_REPLACES_JUPYTER"
MARK_END = "# <<< AIC_OPEN_TERMINAL_REPLACES_JUPYTER"


PS1_BLOCK = f"""
{MARK_START}
# Launch Open Terminal instead of JupyterLab.
# This block is idempotent and is intentionally launcher-level, not planner/controller logic.
$script:AICOpenTerminalStarted = $false

function Get-AICFirstNonEmpty {{
    param([object[]]$Values)
    foreach ($v in $Values) {{
        if ($null -eq $v) {{ continue }}
        $s = [string]$v
        if (-not [string]::IsNullOrWhiteSpace($s)) {{
            $s = $s.Trim()
            if (($s.StartsWith('"') -and $s.EndsWith('"')) -or ($s.StartsWith("'") -and $s.EndsWith("'"))) {{
                $s = $s.Substring(1, $s.Length - 2)
            }}
            if (-not [string]::IsNullOrWhiteSpace($s)) {{ return $s }}
        }}
    }}
    return $null
}}

function Start-AICOpenTerminal {{
    param(
        [object]$ApiKeyCandidate = $null,
        [object]$PortCandidate = $null,
        [object]$HostCandidate = $null
    )

    if ($script:AICOpenTerminalStarted) {{
        Write-Host "[open-terminal-replaces-jupyter] already started in this launcher session."
        return
    }}

    $token = Get-AICFirstNonEmpty @(
        $ApiKeyCandidate,
        $env:OPEN_TERMINAL_API_KEY,
        $env:JUPYTER_TOKEN,
        $env:JUPYTER_SERVER_TOKEN,
        $env:NOTEBOOK_TOKEN,
        $env:OPENWEBUI_JUPYTER_TOKEN,
        $env:OPENWEBUI_CODE_EXECUTION_JUPYTER_TOKEN,
        $env:CODE_EXECUTION_JUPYTER_AUTH_TOKEN,
        $env:WEBUI_JUPYTER_TOKEN
    )

    if ([string]::IsNullOrWhiteSpace($token)) {{
        throw "[open-terminal-replaces-jupyter] Missing token. Set OPEN_TERMINAL_API_KEY or the same JUPYTER_TOKEN previously used by JupyterLab."
    }}

    $portRaw = Get-AICFirstNonEmpty @($PortCandidate, $env:OPEN_TERMINAL_PORT)
    $port = 8000
    if (-not [string]::IsNullOrWhiteSpace($portRaw)) {{
        try {{ $port = [int]$portRaw }} catch {{ throw "[open-terminal-replaces-jupyter] Invalid port: $portRaw" }}
    }}

    $hostAddress = Get-AICFirstNonEmpty @($HostCandidate, $env:OPEN_TERMINAL_HOST, "127.0.0.1")
    $labRepoForTerminal = Get-AICFirstNonEmpty @(
        $env:AICARMINE_LAB_REPO,
        [Environment]::GetEnvironmentVariable("AICARMINE_LAB_REPO", "User"),
        "C:\\Users\\someo\\agentic-tool-loop"
    )
    $cwd = Get-AICFirstNonEmpty @($labRepoForTerminal, $env:OPEN_TERMINAL_CWD)
    if ([string]::IsNullOrWhiteSpace($cwd) -or -not (Test-Path -LiteralPath $cwd)) {{
        throw "[open-terminal-replaces-jupyter] AICARMINE_LAB_REPO/Open Terminal cwd non valido: $cwd"
    }}

    $cmd = Get-Command open-terminal -ErrorAction SilentlyContinue
    if (-not $cmd) {{
        throw "[open-terminal-replaces-jupyter] open-terminal not found in PATH. Activate the openwebui venv or run: pip install open-terminal"
    }}

    $env:OPEN_TERMINAL_API_KEY = $token
    $env:OPEN_TERMINAL_CWD = $cwd

    Write-Host "[open-terminal-replaces-jupyter] launching Open Terminal"
    Write-Host "[open-terminal-replaces-jupyter] cwd=$cwd"
    Write-Host "[open-terminal-replaces-jupyter] host=$hostAddress port=$port token_source=same-jupyter-token-or-env"
    Write-Host "[open-terminal-replaces-jupyter] Jupyter/JupyterLab will not be started."

    $args = @("run", "--host", $hostAddress, "--port", "$port", "--api-key", "$token")
    Start-Process -FilePath $cmd.Source -ArgumentList $args -WorkingDirectory $cwd -WindowStyle Normal

    $script:AICOpenTerminalStarted = $true
}}
{MARK_END}
""".lstrip()


def _current_ps1_block() -> str:
    """Read the canonical launcher block from the local openwebui.ps1 when present."""
    source = Path(__file__).with_name("openwebui.ps1")
    try:
        text = source.read_text(encoding="utf-8")
    except OSError:
        return PS1_BLOCK

    pattern = re.compile(
        re.escape(MARK_START) + r".*?" + re.escape(MARK_END) + r"\s*",
        re.S,
    )
    match = pattern.search(text)
    if not match:
        return PS1_BLOCK
    return match.group(0).rstrip() + "\n"


JUPYTER_CMD_TOKEN = r"""(?:
    (?:"[^"]*(?:[\\\\/])?jupyter(?:-lab|-notebook)?(?:\\.exe)?")
    |
    (?:'[^']*(?:[\\\\/])?jupyter(?:-lab|-notebook)?(?:\\.exe)?')
    |
    (?:(?:[\\w.:-]+[\\\\/])?jupyter(?:-lab|-notebook)?(?:\\.exe)?)
)"""

JUPYTER_LINE_RE = re.compile(
    rf"""(?ix)
    ^(?P<prefix>\\s*)
    (?!
        \\#|
        .*open-terminal-replaces-jupyter|
        .*Start-AICOpenTerminal
    )
    (?P<line>
        (?:
            (?:&\\s*)?
            {JUPYTER_CMD_TOKEN}
            (?=\\s|$)
            .*
        )
        |
        (?:
            (?:python(?:\\.exe)?|py(?:\\.exe)?)\\s+-m\\s+jupyter\\b.*
        )
        |
        (?:
            Start-Process\\b.*\\bjupyter(?:-lab|-notebook)?(?:\\.exe)?\\b.*
        )
    )
    $
    """
)

OPENWEBUI_START_RE = re.compile(
    r"""(?ix)
    ^(?!\s*\#).*
    (
        \bopen-webui\b
        |
        \bopen_webui\b
        |
        \buvicorn\b.*open_webui
        |
        \bpython(?:\.exe)?\s+-m\s+open_webui\b
    )
    """
)

TOKEN_PATTERNS = [
    re.compile(r'(?i)--(?:ServerApp|NotebookApp|LabApp)\.token(?:=|\s+)(?P<value>"[^"]+"|\'[^\']+\'|\S+)'),
    re.compile(r'(?i)--token(?:=|\s+)(?P<value>"[^"]+"|\'[^\']+\'|\S+)'),
]
PORT_PATTERNS = [
    re.compile(r'(?i)--(?:ServerApp|NotebookApp|LabApp)\.port(?:=|\s+)(?P<value>\d+|\$[\w:]+)'),
    re.compile(r'(?i)--port(?:=|\s+)(?P<value>\d+|\$[\w:]+)'),
]
HOST_PATTERNS = [
    re.compile(r'(?i)--(?:ServerApp|NotebookApp|LabApp)\.ip(?:=|\s+)(?P<value>"[^"]+"|\'[^\']+\'|\S+)'),
    re.compile(r'(?i)--ip(?:=|\s+)(?P<value>"[^"]+"|\'[^\']+\'|\S+)'),
    re.compile(r'(?i)--host(?:=|\s+)(?P<value>"[^"]+"|\'[^\']+\'|\S+)'),
]


def _leading_ws(line: str) -> str:
    return re.match(r"\s*", line).group(0)


def _first_token(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("&"):
        stripped = stripped[1:].strip()
    m = re.match(r'(?:"(?P<dq>[^"]+)"|\'(?P<sq>[^\']+)\'|(?P<bare>\S+))', stripped)
    if not m:
        return ""
    return (m.group("dq") or m.group("sq") or m.group("bare") or "").strip()


def _basename_token(token: str) -> str:
    return token.replace("\\\\", "/").split("/")[-1].lower()


def is_jupyter_launch_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return False
    low = stripped.lower()
    if "open-terminal-replaces-jupyter" in low or "start-aicopenterminal" in low:
        return False
    # Do not treat env/local variable references such as $env:JUPYTER_TOKEN as commands.
    if stripped.startswith("$"):
        return False
    if re.match(r"^(?:python(?:\.exe)?|py(?:\.exe)?)\s+-m\s+jupyter\b", stripped, re.I):
        return True
    if re.match(r"^start-process\b", stripped, re.I) and re.search(r"\bjupyter(?:-lab|-notebook)?(?:\.exe)?\b", stripped, re.I):
        return True
    cmd = _basename_token(_first_token(stripped))
    return cmd in {
        "jupyter",
        "jupyter.exe",
        "jupyter-lab",
        "jupyter-lab.exe",
        "jupyter-notebook",
        "jupyter-notebook.exe",
    }


def is_openwebui_start_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return False
    low = stripped.lower()
    if "start-aicopenterminal" in low or "open-terminal-replaces-jupyter" in low:
        return False
    return (
        re.search(r"\bopen-webui\b", stripped, re.I) is not None
        or re.search(r"\bopen_webui\b", stripped, re.I) is not None
        or re.search(r"\buvicorn\b.*open_webui", stripped, re.I) is not None
        or re.search(r"\bpython(?:\.exe)?\s+-m\s+open_webui\b", stripped, re.I) is not None
    )

def _extract(patterns: Iterable[re.Pattern[str]], line: str) -> Optional[str]:
    for pat in patterns:
        m = pat.search(line)
        if m:
            return m.group("value")
    return None


def _call_from_old_jupyter_line(line: str) -> str:
    token = _extract(TOKEN_PATTERNS, line)
    port = _extract(PORT_PATTERNS, line)
    host = _extract(HOST_PATTERNS, line)

    parts = ["Start-AICOpenTerminal"]
    if token:
        parts.append(f"-ApiKeyCandidate {token}")
    if port:
        parts.append(f"-PortCandidate {port}")
    if host:
        parts.append(f"-HostCandidate {host}")
    return " ".join(parts)


def _strip_existing_block(text: str) -> str:
    if MARK_START not in text:
        return text
    pattern = re.compile(re.escape(MARK_START) + r".*?" + re.escape(MARK_END) + r"\s*", re.S)
    return pattern.sub("", text)


def _insert_block_after_param_or_top(text: str) -> str:
    ps1_block = _current_ps1_block()
    lines = text.splitlines(keepends=True)
    if not lines:
        return ps1_block + "\n"

    start_idx = 0
    while start_idx < len(lines) and lines[start_idx].strip() == "":
        start_idx += 1

    if start_idx < len(lines) and re.match(r"^\s*param\s*\(", lines[start_idx], re.I):
        depth = 0
        for i in range(start_idx, len(lines)):
            depth += lines[i].count("(") - lines[i].count(")")
            if depth <= 0 and ")" in lines[i]:
                insert_at = i + 1
                return "".join(lines[:insert_at]) + "\n" + ps1_block + "\n" + "".join(lines[insert_at:])

    return ps1_block + "\n" + text


def patch_ps1_text(text: str) -> Tuple[str, dict]:
    original = text
    work = _strip_existing_block(text)

    lines = work.splitlines()
    out = []
    replaced_jupyter = 0
    inserted_before_openwebui = False

    for line in lines:
        if is_jupyter_launch_line(line):
            replaced_jupyter += 1
            prefix = _leading_ws(line)
            call = _call_from_old_jupyter_line(line)
            out.append(f"{prefix}# [open-terminal-replaces-jupyter] Disabled old Jupyter/JupyterLab launcher:")
            out.append(f"{prefix}# ORIGINAL: {line.strip()}")
            if replaced_jupyter == 1:
                out.append(f"{prefix}{call}")
            continue

        if replaced_jupyter == 0 and not inserted_before_openwebui and is_openwebui_start_line(line):
            out.append("Start-AICOpenTerminal")
            inserted_before_openwebui = True

        out.append(line)

    if replaced_jupyter == 0 and not inserted_before_openwebui:
        out.append("")
        out.append("# [open-terminal-replaces-jupyter] No Jupyter/OpenWebUI launcher line was detected automatically.")
        out.append("# Starting Open Terminal here so openwebui.ps1 still launches it.")
        out.append("Start-AICOpenTerminal")
        inserted_before_openwebui = True

    new_text_without_block = "\n".join(out)
    if work.endswith("\n"):
        new_text_without_block += "\n"

    new_text = _insert_block_after_param_or_top(new_text_without_block)

    return new_text, {
        "changed": new_text != original,
        "replaced_jupyter_lines": replaced_jupyter,
        "inserted_before_openwebui": inserted_before_openwebui,
        "marker_present": MARK_START in new_text,
    }

def read_text_guess(path: Path) -> Tuple[str, str]:
    data = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace"), "utf-8"


def write_text_preserve(path: Path, text: str, encoding: str) -> None:
    enc = "utf-8-sig" if encoding == "utf-8-sig" else encoding
    path.write_text(text, encoding=enc, newline="\n")


def patch_ps1_file(path: Path) -> dict:
    text, enc = read_text_guess(path)
    new_text, meta = patch_ps1_text(text)
    if not meta["changed"]:
        meta["path"] = str(path)
        meta["backup"] = None
        return meta

    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(path.name + f".bak-open-terminal-{stamp}")
    shutil.copy2(path, backup)
    write_text_preserve(path, new_text, enc)
    meta["path"] = str(path)
    meta["backup"] = str(backup)
    meta["encoding"] = enc
    return meta


def find_ps1(root: Path) -> list[Path]:
    matches = []
    for p in root.rglob("*.ps1"):
        if p.name.lower() == "openwebui.ps1" or "openwebui" in p.name.lower():
            matches.append(p)
    return sorted(matches, key=lambda p: (p.name.lower() != "openwebui.ps1", len(str(p)), str(p).lower()))


def patch_root(root: Path) -> list[dict]:
    matches = find_ps1(root)
    if not matches:
        raise FileNotFoundError(f"No openwebui*.ps1 found under {root}")
    exact = [p for p in matches if p.name.lower() == "openwebui.ps1"]
    targets = exact or matches
    return [patch_ps1_file(p) for p in targets]


def patch_zip(zip_path: Path, in_place: bool = False) -> Tuple[Path, list[dict]]:
    if not zip_path.exists():
        raise FileNotFoundError(zip_path)
    if not zipfile.is_zipfile(zip_path):
        raise ValueError(f"Not a zip file: {zip_path}")

    with tempfile.TemporaryDirectory(prefix="openwebui_ps1_patch_") as td:
        work = Path(td) / "work"
        work.mkdir()
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(work)

        results = patch_root(work)

        out_path = zip_path if in_place else zip_path.with_name(zip_path.stem + "-open-terminal-patched.zip")
        tmp_out = zip_path.with_name(zip_path.stem + ".tmp-open-terminal-patched.zip")
        if tmp_out.exists():
            tmp_out.unlink()

        with zipfile.ZipFile(tmp_out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for p in sorted(work.rglob("*")):
                if p.is_file():
                    zf.write(p, p.relative_to(work).as_posix())

        if in_place:
            backup = zip_path.with_name(zip_path.name + f".bak-open-terminal-{_dt.datetime.now().strftime('%Y%m%d-%H%M%S')}")
            shutil.copy2(zip_path, backup)
            tmp_out.replace(zip_path)
            for r in results:
                r["zip_backup"] = str(backup)
        else:
            tmp_out.replace(out_path)

    return out_path, results


def autodetect_zip_or_root() -> Tuple[str, Path]:
    cwd = Path.cwd()
    candidates = []
    for pat in ("*aggiornato*.zip", "*aggiornata*.zip", "*progetto*.zip", "*proggetto*.zip", "*.zip"):
        candidates.extend(cwd.glob(pat))
    candidates = sorted(set(candidates), key=lambda p: (p.name.lower(), p.stat().st_mtime if p.exists() else 0), reverse=True)
    if candidates:
        return "zip", candidates[0]
    if find_ps1(cwd):
        return "root", cwd
    raise FileNotFoundError("No zip and no openwebui*.ps1 found in current directory. Pass --zip, --root or --ps1.")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Patch openwebui.ps1 to launch Open Terminal instead of JupyterLab.")
    ap.add_argument("--zip", dest="zip_path", help="Path to project zip, e.g. 'proggetto aggiornato.zip'.")
    ap.add_argument("--root", dest="root_path", help="Path to extracted project root.")
    ap.add_argument("--ps1", dest="ps1_path", help="Direct path to openwebui.ps1.")
    ap.add_argument("--in-place", action="store_true", help="For --zip, modify zip in place after creating a backup.")
    ap.add_argument("--scan-only", action="store_true", help="Only report what would be patched.")
    args = ap.parse_args(argv)

    try:
        if args.ps1_path:
            ps1 = Path(args.ps1_path).expanduser().resolve()
            if args.scan_only:
                print(f"[scan] ps1={ps1}")
                text, _ = read_text_guess(ps1)
                print("[scan] contains marker:", MARK_START in text)
                print("[scan] jupyter launch lines:", sum(1 for line in text.splitlines() if is_jupyter_launch_line(line)))
                print("[scan] openwebui launch lines:", sum(1 for line in text.splitlines() if is_openwebui_start_line(line)))
                return 0
            print(patch_ps1_file(ps1))
            return 0

        if args.root_path:
            root = Path(args.root_path).expanduser().resolve()
            if args.scan_only:
                print(f"[scan] root={root}")
                for p in find_ps1(root):
                    print(f"[scan] candidate={p}")
                return 0
            for result in patch_root(root):
                print(result)
            return 0

        if args.zip_path:
            zp = Path(args.zip_path).expanduser().resolve()
            if args.scan_only:
                with tempfile.TemporaryDirectory(prefix="openwebui_ps1_scan_") as td:
                    work = Path(td) / "work"
                    work.mkdir()
                    with zipfile.ZipFile(zp, "r") as zf:
                        zf.extractall(work)
                    print(f"[scan] zip={zp}")
                    for p in find_ps1(work):
                        rel = p.relative_to(work)
                        text, _ = read_text_guess(p)
                        print(f"[scan] candidate={rel} marker={MARK_START in text} jupyter_lines={sum(1 for line in text.splitlines() if is_jupyter_launch_line(line))} openwebui_lines={sum(1 for line in text.splitlines() if is_openwebui_start_line(line))}")
                return 0
            out, results = patch_zip(zp, in_place=args.in_place)
            print(f"[ok] output_zip={out}")
            for r in results:
                print(r)
            return 0

        kind, path = autodetect_zip_or_root()
        print(f"[auto] detected {kind}: {path}")
        if args.scan_only:
            if kind == "zip":
                return main(["--zip", str(path), "--scan-only"])
            return main(["--root", str(path), "--scan-only"])
        if kind == "zip":
            out, results = patch_zip(path, in_place=args.in_place)
            print(f"[ok] output_zip={out}")
            for r in results:
                print(r)
        else:
            for result in patch_root(path):
                print(result)
        return 0

    except Exception as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
