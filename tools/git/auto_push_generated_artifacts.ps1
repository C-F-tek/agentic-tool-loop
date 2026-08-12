<#
.SYNOPSIS
  Auto-commit and push app-generated technical artifacts.

.DESCRIPTION
  This script is intended to be called after the local app regenerates technical data,
  such as indexAI files, manifests, compact JSON contexts, reports, or workflow metadata.

  It does not generate indexes by itself. Generation remains owned by the app/local workflow.

  The script only stages configured generated-artifact paths, creates a commit if there
  are changes, and pushes the current branch.

.EXAMPLE
  .\Tools\git\auto_push_generated_artifacts.ps1

.EXAMPLE
  .\Tools\git\auto_push_generated_artifacts.ps1 -RepoPath "C:\Users\carmi\blender\blender-audio-project" -Message "chore: update generated AI artifacts"

.EXAMPLE
  .\Tools\git\auto_push_generated_artifacts.ps1 -DryRun
#>

param(
    [string]$RepoPath = ".",
    [string]$Message = "chore: update generated technical artifacts",
    [string[]]$Paths = @(
        "indexAI",
        "output/*_track_summary.json",
        "output/*_music_context.json",
        "output/*_analysis_ai_context.json",
        "output/*_dual_ai_scene_plan.json",
        "output/*_ai_implementation_draft.json",
        "Tools/npu/*_manifest.json",
        "Tools/npu/*_context.md",
        "Tools/npu/*_index.md",
        "Tools/npu/*_technical_notes.md",
        "Tools/npu/*_implementation_notes.md",
        "Tools/npu/npu_preflight_report.json"
    ),
    [switch]$IncludeFullAnalysisJson,
    [switch]$DryRun,
    [switch]$NoPush
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Text)
    Write-Host "[auto-push] $Text"
}

function Invoke-Git {
    param([string[]]$GitArgs)

    if ($DryRun) {
        Write-Host "DRY-RUN git $($GitArgs -join ' ')"
        return
    }

    & git @GitArgs
    if ($LASTEXITCODE -ne 0) {
        throw "git $($GitArgs -join ' ') failed with exit code $LASTEXITCODE"
    }
}

$repo = Resolve-Path $RepoPath
Write-Step "Repository: $repo"

Push-Location $repo
try {
    $inside = (& git rev-parse --is-inside-work-tree 2>$null).Trim()
    if ($inside -ne "true") {
        throw "RepoPath is not inside a Git repository: $repo"
    }

    $branch = (& git branch --show-current).Trim()
    if (-not $branch) {
        throw "Could not determine current Git branch."
    }
    Write-Step "Current branch: $branch"

    $upstream = (& git rev-parse --abbrev-ref --symbolic-full-name "@{u}" 2>$null)
    if (-not $upstream) {
        Write-Step "No upstream configured for branch '$branch'. Push may fail unless upstream is set."
    } else {
        Write-Step "Upstream: $($upstream.Trim())"
    }

    $pathsToStage = New-Object System.Collections.Generic.List[string]
    foreach ($path in $Paths) {
        $pathsToStage.Add($path)
    }

    if ($IncludeFullAnalysisJson) {
        Write-Step "Including full analysis/keyframe JSON files."
        $pathsToStage.Add("output/*_analysis.json")
        $pathsToStage.Add("output/*_analysis_blender_keyframes.json")
    } else {
        Write-Step "Full frame analysis JSON files are excluded by default. Use -IncludeFullAnalysisJson to include them."
    }

    foreach ($path in $pathsToStage) {
        Write-Step "Staging: $path"
        Invoke-Git @("add", "--", $path)
    }

    $staged = (& git diff --cached --name-only)
    if (-not $staged) {
        Write-Step "No generated artifact changes to commit."
        return
    }

    Write-Step "Staged files:"
    $staged | ForEach-Object { Write-Host "  $_" }

    Invoke-Git @("commit", "-m", $Message)

    if ($NoPush) {
        Write-Step "Commit created. Push skipped because -NoPush was specified."
        return
    }

    if ($upstream) {
        Invoke-Git @("push")
    } else {
        Invoke-Git @("push", "-u", "origin", $branch)
    }

    Write-Step "Done. Generated artifacts committed and pushed."
}
finally {
    Pop-Location
}
