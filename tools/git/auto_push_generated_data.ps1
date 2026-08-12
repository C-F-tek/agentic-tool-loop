<#
.SYNOPSIS
  Commit and push app-generated technical data or the full project to GitHub.

.DESCRIPTION
  Default mode is conservative and stages only allowlisted generated paths.

  FullProject mode is intentionally explicit and performs this safe sequence:
  - save local changes with git stash push -u;
  - git pull --rebase origin <branch>;
  - restore the stash;
  - git status;
  - git add .;
  - git commit -m <message> when there are staged changes;
  - git push origin <branch>.

.EXAMPLE
  .\Tools\git\auto_push_generated_data.ps1

.EXAMPLE
  .\Tools\git\auto_push_generated_data.ps1 -Message "chore: update app-generated technical data"

.EXAMPLE
  .\Tools\git\auto_push_generated_data.ps1 -FullProject -Message "chore: update full project"

.EXAMPLE
  .\Tools\git\auto_push_generated_data.ps1 -DryRun
#>

param(
    [string]$RepoPath = ".",
    [string]$Branch = "master",
    [string]$Message = "chore: update app-generated technical data",
    [switch]$PullFirst,
    [switch]$DryRun,
    [switch]$IncludeOutputJson,
    [switch]$IncludeDocs,
    [switch]$IncludeAllGenerated,
    [switch]$FullProject
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Text)
    Write-Host "[auto-push] $Text"
}

function Invoke-Git {
    param(
        [Parameter(Mandatory=$true)][string[]]$Args,
        [switch]$AllowFailure
    )

    & git @Args
    $code = [int]$LASTEXITCODE
    if ($code -ne 0 -and -not $AllowFailure) {
        throw "git $($Args -join ' ') failed with exit code $code"
    }
    return $code
}

function Invoke-GitCodeOnly {
    param([Parameter(Mandatory=$true)][string[]]$Args)

    $gitOutput = & git @Args 2>&1
    $code = [int]$LASTEXITCODE
    foreach ($line in $gitOutput) {
        Write-Host $line
    }
    return $code
}

function Has-WorkingTreeChanges {
    $status = (& git status --porcelain=v1)
    return -not [string]::IsNullOrWhiteSpace(($status -join "`n"))
}

function Has-StagedChanges {
    $staged = (& git diff --cached --name-only)
    return -not [string]::IsNullOrWhiteSpace(($staged -join "`n"))
}

function Run-FullProjectPush {
    param(
        [string]$Branch,
        [string]$Message,
        [switch]$DryRun
    )

    Write-Step "Mode: full project push."
    Write-Step "Sequence: stash -u, pull --rebase, stash pop, status, add ., commit, push."

    if ($DryRun) {
        Write-Step "Dry run: git status before full project push."
        Invoke-Git @("status", "--short") | Out-Null
        Write-Step "Dry run complete. No changes staged, committed, rebased, or pushed."
        return
    }

    $stashCreated = $false
    if (Has-WorkingTreeChanges) {
        Write-Step "Saving local working tree with git stash push -u."
        Invoke-Git @("stash", "push", "-u", "-m", "local staged changes before rebase") | Out-Null
        $stashCreated = $true
    }
    else {
        Write-Step "Working tree is already clean before pull."
    }

    try {
        Write-Step "Pulling latest remote changes with rebase."
        Invoke-Git @("pull", "--rebase", "origin", $Branch) | Out-Null

        if ($stashCreated) {
            Write-Step "Restoring stashed local changes."
            $popCode = Invoke-GitCodeOnly @("stash", "pop")
            if ([int]$popCode -ne 0) {
                Write-Step "stash pop reported conflicts. Resolve them manually, then run commit/push again."
                throw "git stash pop failed with exit code $popCode"
            }
        }

        Write-Step "Current status after rebase/stash restore:"
        Invoke-Git @("status", "--short") | Out-Null

        Write-Step "Staging full project with git add ."
        Invoke-Git @("add", ".") | Out-Null

        if (-not (Has-StagedChanges)) {
            Write-Step "No staged changes found after git add .. Nothing to commit."
            return
        }

        Write-Step "Staged files:"
        (& git diff --cached --name-only) -split "`n" | Where-Object { $_.Trim() } | ForEach-Object { Write-Host "  - $_" }

        Invoke-Git @("commit", "-m", $Message) | Out-Null
        Write-Step "Commit created."

        Invoke-Git @("push", "origin", $Branch) | Out-Null
        Write-Step "Pushed full project to origin/$Branch."
    }
    catch {
        Write-Step "Full project push stopped: $($_.Exception.Message)"
        throw
    }
}

$root = Resolve-Path $RepoPath
Write-Step "Repository: $root"

Push-Location $root
try {
    Invoke-Git @("rev-parse", "--is-inside-work-tree") | Out-Null

    $currentBranch = (& git branch --show-current).Trim()
    if ($currentBranch -ne $Branch) {
        throw "Current branch is '$currentBranch', expected '$Branch'. Stop to avoid pushing the wrong branch."
    }

    if ($FullProject) {
        Run-FullProjectPush -Branch $Branch -Message $Message -DryRun:$DryRun
        exit 0
    }

    if ($PullFirst) {
        Write-Step "Pulling latest changes before staging."
        if (-not $DryRun) {
            Invoke-Git @("pull", "--ff-only", "origin", $Branch) | Out-Null
        }
    }

    $paths = New-Object System.Collections.Generic.List[string]

    # Primary app/index generated data.
    $paths.Add("indexAI")

    # NPU/context manifests generated by the project tools.
    $paths.Add("Tools/npu/*.json")
    $paths.Add("Tools/npu/*.md")

    # Optional broader generated data.
    if ($IncludeOutputJson -or $IncludeAllGenerated) {
        $paths.Add("output/*.json")
        $paths.Add("output/*.md")
        $paths.Add("output/*.txt")
    }

    if ($IncludeDocs -or $IncludeAllGenerated) {
        $paths.Add("docs")
    }

    Write-Step "Allowlisted paths to stage:"
    foreach ($p in $paths) {
        Write-Host "  - $p"
    }

    if ($DryRun) {
        Write-Step "Dry run: git status before staging."
        Invoke-Git @("status", "--short") | Out-Null
        Write-Step "Dry run complete. No changes staged, committed, or pushed."
        exit 0
    }

    foreach ($p in $paths) {
        Invoke-Git @("add", "--", $p) -AllowFailure | Out-Null
    }

    $staged = (& git diff --cached --name-only)
    if ([string]::IsNullOrWhiteSpace($staged)) {
        Write-Step "No staged generated-data changes found. Nothing to commit."
        exit 0
    }

    Write-Step "Staged files:"
    $staged -split "`n" | Where-Object { $_.Trim() } | ForEach-Object { Write-Host "  - $_" }

    Invoke-Git @("commit", "-m", $Message) | Out-Null
    Write-Step "Commit created."

    Invoke-Git @("push", "origin", $Branch) | Out-Null
    Write-Step "Pushed to origin/$Branch."
}
finally {
    Pop-Location
}
