param(
    [Parameter(Mandatory = $true)]
    [string]$Command,

    [int]$TimeoutSeconds = 180,

    [ValidateSet("lab", "main", "custom")]
    [string]$RepoMode = "lab",

    [string]$Repo = "",

    [string]$UserConsent = ""
)

$ErrorActionPreference = "Stop"

$MainRepo = [Environment]::GetEnvironmentVariable("AICARMINE_REAL_REPO", "User")
if ([string]::IsNullOrWhiteSpace($MainRepo)) {
    $MainRepo = "C:\Users\carmi\ProjectsDir\blender-audio-project"
}
$LabRepo  = [Environment]::GetEnvironmentVariable("AICARMINE_LAB_REPO", "User")
if ([string]::IsNullOrWhiteSpace($LabRepo)) {
    $LabRepo = "C:\Users\carmi\AI\lab-worktrees\blender-audio-project-lab"
}
$OutRoot  = "C:\Users\carmi\AI\executor-runs"
$Stamp    = Get-Date -Format "yyyyMMdd-HHmmss"
$RunDir   = Join-Path $OutRoot $Stamp

New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

if ($RepoMode -eq "lab") {
    $EffectiveRepo = $LabRepo
}
elseif ($RepoMode -eq "main") {
    $EffectiveRepo = $MainRepo
}
else {
    if ([string]::IsNullOrWhiteSpace($Repo)) {
        throw "RepoMode=custom richiede -Repo"
    }
    $EffectiveRepo = $Repo
}

if (-not (Test-Path $EffectiveRepo)) {
    throw "Repo non trovata: $EffectiveRepo"
}

$ConsentPhrase = [Environment]::GetEnvironmentVariable("AICARMINE_CODEX_CONSENT_PHRASE", "User")
if ([string]::IsNullOrWhiteSpace($ConsentPhrase)) {
    $ConsentPhrase = "APPROVED_BY_CARMINE"
}

$DeniedAlwaysPatterns = @(
    'Set-ExecutionPolicy',
    'Invoke-WebRequest\s+.*\|\s*iex',
    'irm\s+.*\|\s*iex',
    'curl\s+.*\|\s*iex',
    'shutdown',
    'Restart-Computer',
    'Stop-Computer',
    'format\s+',
    'diskpart',
    'bcdedit',
    'reg\s+delete',
    'Remove-Service',
    'sc\s+delete',
    'takeown\s+',
    'icacls\s+.*\s+/grant',
    'net\s+user',
    'net\s+localgroup'
)

$ConsentRequiredPatterns = @(
    'git\s+push',
    'git\s+merge',
    'git\s+rebase',
    'git\s+reset\s+--hard',
    'git\s+clean\s+-fdx?',
    'Remove-Item\s+.*-Recurse',
    'Remove-Item\s+.*-Force',
    '\brmdir\b',
    '\bdel\b',
    '\berase\b'
)

foreach ($Pattern in $DeniedAlwaysPatterns) {
    if ($Command -match $Pattern) {
        $blocked = [pscustomobject]@{
            schema_version = 2
            kind = "aicarmine_codex_command_report"
            ok = $false
            blocked = $true
            reason = "denied_always"
            matched_pattern = $Pattern
            command = $Command
            repo_mode = $RepoMode
            repo = $EffectiveRepo
            requires_user_consent = $false
        }
        $blocked | ConvertTo-Json -Depth 8
        exit 2
    }
}

$ConsentMatches = @()
foreach ($Pattern in $ConsentRequiredPatterns) {
    if ($Command -match $Pattern) {
        $ConsentMatches += $Pattern
    }
}

if ($ConsentMatches.Count -gt 0 -and $UserConsent -ne $ConsentPhrase) {
    $needsConsent = [pscustomobject]@{
        schema_version = 2
        kind = "aicarmine_codex_command_report"
        ok = $false
        blocked = $false
        reason = "requires_user_consent"
        command = $Command
        repo_mode = $RepoMode
        repo = $EffectiveRepo
        requires_user_consent = $true
        consent_phrase = $ConsentPhrase
        matched_patterns = $ConsentMatches
        next_step = "Riesegui lo stesso comando passando UserConsent=$ConsentPhrase dopo conferma esplicita dell'utente."
    }
    $needsConsent | ConvertTo-Json -Depth 8
    exit 3
}

function Stop-AICProcessTree {
    param([System.Diagnostics.Process]$Process)

    if ($null -eq $Process -or $Process.HasExited) {
        return
    }

    $taskkill = Get-Command taskkill.exe -ErrorAction SilentlyContinue
    if ($taskkill) {
        try {
            & $taskkill.Source /PID ([string]$Process.Id) /T /F | Out-Null
            return
        }
        catch {
            # Fall through to single-process kill.
        }
    }

    try {
        if (-not $Process.HasExited) {
            $Process.Kill()
        }
    }
    catch {}
}

$stdout = Join-Path $RunDir "stdout.txt"
$stderr = Join-Path $RunDir "stderr.txt"
$report = Join-Path $RunDir "report.json"
$exitCodePath = Join-Path $RunDir "exitcode.txt"

function ConvertTo-AICPowerShellLiteral {
    param([string]$Value)
    return "'" + ($Value -replace "'", "''") + "'"
}

$repoLiteral = ConvertTo-AICPowerShellLiteral $EffectiveRepo
$exitCodeLiteral = ConvertTo-AICPowerShellLiteral $exitCodePath
$wrapped = @"
Set-Location -LiteralPath $repoLiteral
`$ErrorActionPreference = 'Continue'
`$aicExitCode = 0
try {
$Command
    if (`$null -ne `$global:LASTEXITCODE) {
        `$aicExitCode = [int]`$global:LASTEXITCODE
    }
}
catch {
    Write-Error `$_
    `$aicExitCode = 1
}
Set-Content -LiteralPath $exitCodeLiteral -Value ([string]`$aicExitCode) -Encoding ASCII
exit `$aicExitCode
"@
$encodedCommand = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($wrapped))

$startedAt = Get-Date
$proc = Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encodedCommand) `
    -WorkingDirectory $EffectiveRepo `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -WindowStyle Hidden `
    -PassThru

$timedOut = $false

if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
    $timedOut = $true
    Stop-AICProcessTree -Process $proc
}

# Ensure redirected output files are released before collecting text.
try { $null = $proc.WaitForExit(2000) } catch {}
Start-Sleep -Milliseconds 100

$outText = if (Test-Path -LiteralPath $stdout) { Get-Content -LiteralPath $stdout -Raw -ErrorAction SilentlyContinue } else { "" }
$errText = if (Test-Path -LiteralPath $stderr) { Get-Content -LiteralPath $stderr -Raw -ErrorAction SilentlyContinue } else { "" }
$rawExitCode = if (Test-Path -LiteralPath $exitCodePath) { Get-Content -LiteralPath $exitCodePath -Raw -ErrorAction SilentlyContinue } else { "" }
$parsedExitCode = 1
if ($timedOut) {
    $processExitCode = -1
}
elseif ([int]::TryParse(($rawExitCode | Out-String).Trim(), [ref]$parsedExitCode)) {
    $processExitCode = $parsedExitCode
}
else {
    $processExitCode = 1
}

$gitStatus = ""
$gitDiffStat = ""

try {
    $gitStatus = git -C $EffectiveRepo status --short | Out-String
} catch {}

try {
    $gitDiffStat = git -C $EffectiveRepo diff --stat | Out-String
} catch {}

$result = [pscustomobject]@{
    schema_version = 2
    kind = "aicarmine_codex_command_report"
    ok = (-not $timedOut -and $processExitCode -eq 0)
    command = $Command
    repo_mode = $RepoMode
    repo = $EffectiveRepo
    run_dir = $RunDir
    started_at = $startedAt.ToString("s")
    finished_at = (Get-Date).ToString("s")
    timeout_seconds = $TimeoutSeconds
    timed_out = $timedOut
    exit_code = $processExitCode
    stdout_path = $stdout
    stderr_path = $stderr
    stdout_tail = ($outText -split "`n" | Select-Object -Last 160) -join "`n"
    stderr_tail = ($errText -split "`n" | Select-Object -Last 160) -join "`n"
    git_status_short = $gitStatus
    git_diff_stat = $gitDiffStat
    requires_user_consent = $false
}

$result | ConvertTo-Json -Depth 10 | Set-Content -Path $report -Encoding UTF8
Get-Content $report -Raw
if ($timedOut) {
    exit 124
}
exit $processExitCode
