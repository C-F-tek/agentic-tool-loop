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

$MainRepo = "C:\Users\carmi\ProjectsDir\blender-audio-project"
$LabRepo  = "C:\Users\carmi\AI\lab-worktrees\blender-audio-project-lab"
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

$stdout = Join-Path $RunDir "stdout.txt"
$stderr = Join-Path $RunDir "stderr.txt"
$report = Join-Path $RunDir "report.json"

$wrapped = "Set-Location `"$EffectiveRepo`"; `$ErrorActionPreference='Continue'; $Command"

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "powershell.exe"
$psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -Command `"$wrapped`""
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true

$proc = New-Object System.Diagnostics.Process
$proc.StartInfo = $psi

$stdoutBuilder = New-Object System.Text.StringBuilder
$stderrBuilder = New-Object System.Text.StringBuilder

$stdoutHandler = [System.Diagnostics.DataReceivedEventHandler]{
    param($sender, $eventArgs)
    if ($null -ne $eventArgs.Data) {
        [void]$stdoutBuilder.AppendLine($eventArgs.Data)
    }
}

$stderrHandler = [System.Diagnostics.DataReceivedEventHandler]{
    param($sender, $eventArgs)
    if ($null -ne $eventArgs.Data) {
        [void]$stderrBuilder.AppendLine($eventArgs.Data)
    }
}

$proc.add_OutputDataReceived($stdoutHandler)
$proc.add_ErrorDataReceived($stderrHandler)

$startedAt = Get-Date
$proc.Start() | Out-Null
$proc.BeginOutputReadLine()
$proc.BeginErrorReadLine()

$timedOut = $false

if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
    $timedOut = $true
    try {
        $proc.Kill($true)
    } catch {
        try { $proc.Kill() } catch {}
    }
}

# Ensure async output handlers flush before collecting text.
try { $proc.WaitForExit() } catch {}

$outText = $stdoutBuilder.ToString()
$errText = $stderrBuilder.ToString()

$outText | Set-Content -Path $stdout -Encoding UTF8
$errText | Set-Content -Path $stderr -Encoding UTF8

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
    ok = (-not $timedOut -and $proc.ExitCode -eq 0)
    command = $Command
    repo_mode = $RepoMode
    repo = $EffectiveRepo
    run_dir = $RunDir
    started_at = $startedAt.ToString("s")
    finished_at = (Get-Date).ToString("s")
    timeout_seconds = $TimeoutSeconds
    timed_out = $timedOut
    exit_code = if ($timedOut) { -1 } else { $proc.ExitCode }
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
