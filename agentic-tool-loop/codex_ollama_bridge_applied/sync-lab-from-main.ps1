param(
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

$Main = "C:\Users\carmi\ProjectsDir\blender-audio-project"
$Lab  = "C:\Users\carmi\AI\lab-worktrees\blender-audio-project-lab"

$PatchDir = "C:\Users\carmi\AI\lab-patches"
$Patch = Join-Path $PatchDir "master-working-tree-to-lab.diff"

$LogDir = "C:\Users\carmi\AI\logs"
$LogFile = Join-Path $LogDir "lab-mirror-sync.log"
$LockFile = Join-Path $LogDir "lab-mirror-sync.lock"

New-Item -ItemType Directory -Force -Path $PatchDir, $LogDir | Out-Null

function Write-Log {
    param([string]$Message)

    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Add-Content -Path $LogFile -Value $line -Encoding UTF8

    if (-not $Quiet) {
        Write-Host $line
    }
}


function Add-IntentToAddForUntrackedMainFiles {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Repo
    )

    $hardExcludes = @(
        '^\.git/',
        '^\.venv/',
        '^venv/',
        '^node_modules/',
        '^output/',
        '^logs/',
        '^cache/',
        '^dist/',
        '^build/',
        '__pycache__/',
        '\.pyc$',
        '\.pyo$',
        '\.bak-',
        '\.tmp$',
        '\.log$'
    )

    $untracked = git -C $Repo ls-files --others --exclude-standard

    $added = 0
    $skipped = 0

    foreach ($rel in $untracked) {
        if ([string]::IsNullOrWhiteSpace($rel)) {
            continue
        }

        $normalized = $rel.Replace("\", "/")
        $skip = $false

        foreach ($pattern in $hardExcludes) {
            if ($normalized -match $pattern) {
                $skip = $true
                break
            }
        }

        if ($skip) {
            $skipped++
            Write-Log "Intent-add skipped: $normalized"
            continue
        }

        git -C $Repo add -N -- $rel

        if ($LASTEXITCODE -ne 0) {
            throw "git add -N fallito per: $rel"
        }

        $added++
        Write-Log "Intent-add: $normalized"
    }

    Write-Log "Intent-add summary: added=$added skipped=$skipped"
}

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Repo,

        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )

    & git -C $Repo @Args

    if ($LASTEXITCODE -ne 0) {
        throw "git -C `"$Repo`" $($Args -join ' ') failed with exit code $LASTEXITCODE"
    }
}

if (Test-Path $LockFile) {
    $age = (Get-Date) - (Get-Item $LockFile).LastWriteTime

    if ($age.TotalMinutes -lt 10) {
        Write-Log "Sync già in corso, lock attivo: $LockFile"
        exit 0
    }

    Write-Log "Lock stale rimosso: $LockFile"
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
}

New-Item -ItemType File -Path $LockFile -Force | Out-Null

try {
    if (-not (Test-Path $Main)) {
        throw "Repo MAIN non trovata: $Main"
    }

    if (-not (Test-Path $Lab)) {
        throw "Repo LAB non trovata: $Lab"
    }

    Write-Log "DIFF-ONLY sync start MAIN -> LAB"
    Write-Log "Main: $Main"
    Write-Log "Lab:  $Lab"

    $mainBranch = (git -C $Main branch --show-current).Trim()
    $labBranch = (git -C $Lab branch --show-current).Trim()

    Write-Log "MAIN branch: $mainBranch"
    Write-Log "LAB branch:  $labBranch"

    Write-Log "Reset LAB al master locale committato."
    Invoke-Git -Repo $Lab -Args @("reset", "--hard", "master")
    Invoke-Git -Repo $Lab -Args @("clean", "-fdx")

        Write-Log "Auto intent-add dei file nuovi non ignorati nel MAIN."
    Add-IntentToAddForUntrackedMainFiles -Repo $Main
    Write-Log "Creo diff tracked/staged/unstaged dal MAIN. Nessuna copia file, nessun robocopy."
    Remove-Item $Patch -Force -ErrorAction SilentlyContinue

    cmd.exe /d /c "git -C `"$Main`" diff --binary HEAD > `"$Patch`""

    if ($LASTEXITCODE -ne 0) {
        throw "Creazione patch fallita con exit code $LASTEXITCODE"
    }

    $patchSize = 0
    if (Test-Path $Patch) {
        $patchSize = (Get-Item $Patch).Length
    }

    Write-Log "Patch file: $Patch"
    Write-Log "Patch size: $patchSize bytes"

    if ($patchSize -gt 0) {
        Write-Log "Verifico patch su LAB."
        Invoke-Git -Repo $Lab -Args @("apply", "--check", $Patch)

        Write-Log "Applico patch su LAB."
        Invoke-Git -Repo $Lab -Args @("apply", $Patch)
    }
    else {
        Write-Log "Nessun diff tracked/staged/unstaged da applicare."
    }

    $untracked = git -C $Main ls-files --others --exclude-standard
    $untrackedCount = @($untracked | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }).Count

    if ($untrackedCount -gt 0) {
        Write-Log "UNTRACKED MAIN ignorati in modalità diff-only: $untrackedCount"
        Write-Log "Per includere un nuovo file nel diff usa: git -C `"$Main`" add -N <file>"
    }

    $mainStatus = git -C $Main status --short --branch | Out-String
    $labStatus = git -C $Lab status --short --branch | Out-String
    $mainDiff = git -C $Main diff --stat HEAD | Out-String
    $labDiff = git -C $Lab diff --stat HEAD | Out-String

    Write-Log "MAIN status:`n$mainStatus"
    Write-Log "LAB status:`n$labStatus"
    Write-Log "MAIN diff:`n$mainDiff"
    Write-Log "LAB diff:`n$labDiff"

    Write-Log "DIFF-ONLY sync complete."
}
catch {
    Write-Log "Sync ERROR: $($_.Exception.Message)"
    throw
}
finally {
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
}

