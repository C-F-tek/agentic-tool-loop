# AICarmine Cline TaskStart Bootstrap Tests

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$resolvedScriptRoot = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($resolvedScriptRoot)) {
    $scriptPath = $MyInvocation.MyCommand.Path
    if (-not [string]::IsNullOrWhiteSpace($scriptPath)) {
        $resolvedScriptRoot = Split-Path -Parent $scriptPath
    }
}
if ([string]::IsNullOrWhiteSpace($resolvedScriptRoot)) {
    throw 'Cannot resolve the test directory.'
}

$hooksRoot = [System.IO.Path]::GetFullPath((Join-Path $resolvedScriptRoot '..'))
$taskStartPath = Join-Path $hooksRoot 'TaskStart.ps1'
if (-not (Test-Path -LiteralPath $taskStartPath -PathType Leaf)) {
    throw 'TaskStart.ps1 is missing.'
}

$powerShellPath = (Get-Command powershell.exe -ErrorAction Stop).Source
if ([string]::IsNullOrWhiteSpace($powerShellPath) -or
    -not (Test-Path -LiteralPath $powerShellPath -PathType Leaf)) {
    throw 'Cannot resolve an absolute powershell.exe path.'
}

$tempParent = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$testTempRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $tempParent ('aicarmine-cline-task-bootstrap-tests-' + [guid]::NewGuid().ToString('N')))
)
if (-not $testTempRoot.StartsWith($tempParent, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'The isolated test TEMP path escaped the system TEMP directory.'
}
[void][System.IO.Directory]::CreateDirectory($testTempRoot)

function Assert-Condition {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function ConvertTo-WindowsCommandLineArgument {
    param([Parameter(Mandatory = $true)][string]$Value)

    if ($Value.Contains('"')) {
        throw 'A Windows file path cannot contain a double quote.'
    }
    if ($Value -notmatch '\s') {
        return $Value
    }
    return '"' + $Value + '"'
}

function Invoke-TaskStart {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$RawInput
    )

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $powerShellPath
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    $startInfo.Arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File {0}' -f (
        ConvertTo-WindowsCommandLineArgument -Value $taskStartPath
    )
    $startInfo.EnvironmentVariables['TEMP'] = $testTempRoot
    $startInfo.EnvironmentVariables['TMP'] = $testTempRoot

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    try {
        Assert-Condition -Condition $process.Start() -Message 'Process.Start() returned false.'
        $process.StandardInput.Write($RawInput)
        $process.StandardInput.Close()
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        $exitCode = $process.ExitCode
    }
    finally {
        $process.Dispose()
    }

    return [pscustomobject]@{
        ExitCode = $exitCode
        Stdout = $stdout
        Stderr = $stderr
    }
}

function Get-TaskStartContract {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Invocation
    )

    Assert-Condition -Condition ($Invocation.ExitCode -eq 0) -Message 'TaskStart returned a non-zero exit code.'
    Assert-Condition -Condition ([string]::IsNullOrEmpty($Invocation.Stderr)) -Message 'TaskStart wrote to stderr.'
    $nonEmptyLines = @(
        $Invocation.Stdout -split '\r\n|\n|\r' |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
    Assert-Condition -Condition ($nonEmptyLines.Count -eq 1) -Message 'TaskStart stdout was not exactly one non-empty line.'
    try {
        $contract = $nonEmptyLines[0] | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        throw 'TaskStart stdout was not valid JSON.'
    }
    Assert-Condition -Condition ($contract.cancel -is [bool] -and $contract.cancel -eq $false) -Message 'TaskStart returned cancel=true or a non-boolean cancel.'
    Assert-Condition -Condition ($contract.errorMessage -eq '') -Message 'TaskStart returned a non-empty errorMessage.'
    Assert-Condition -Condition ($contract.contextModification -is [string]) -Message 'TaskStart contextModification was not a string.'
    return $contract
}

function Invoke-ValidBootstrap {
    param([Parameter(Mandatory = $true)][hashtable]$Payload)

    $rawInput = $Payload | ConvertTo-Json -Compress -Depth 10
    $invocation = Invoke-TaskStart -RawInput $rawInput
    $contract = Get-TaskStartContract -Invocation $invocation
    Assert-Condition -Condition $contract.contextModification.StartsWith(
        'AICARMINE TASK BOOTSTRAP',
        [System.StringComparison]::Ordinal
    ) -Message 'The TaskStart bootstrap header is missing.'
    Assert-Condition -Condition ($contract.contextModification.Length -le 1800) -Message 'The TaskStart bootstrap exceeds 1800 characters.'
    return [pscustomobject]@{
        Invocation = $invocation
        Contract = $contract
        Bootstrap = [string]$contract.contextModification
    }
}

function Assert-FailOpen {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$RawInput
    )

    $invocation = Invoke-TaskStart -RawInput $RawInput
    $contract = Get-TaskStartContract -Invocation $invocation
    Assert-Condition -Condition ($contract.contextModification -eq '') -Message 'An invalid TaskStart payload emitted a bootstrap.'
}

function Assert-TextAbsent {
    param(
        [Parameter(Mandatory = $true)][string]$Text,
        [Parameter(Mandatory = $true)][string]$Forbidden,
        [Parameter(Mandatory = $true)][string]$Message
    )

    Assert-Condition -Condition ($Text.IndexOf($Forbidden, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) -Message $Message
}

try {
    $case1 = Invoke-ValidBootstrap -Payload @{
        taskId = 'fixture-task'
        workspace = 'fixture-workspace'
    }
    Assert-TextAbsent -Text $case1.Invocation.Stdout -Forbidden 'fixture-task' -Message 'The raw taskId leaked to stdout.'
    Assert-TextAbsent -Text $case1.Invocation.Stdout -Forbidden 'fixture-workspace' -Message 'The raw workspace leaked to stdout.'

    $case2 = Invoke-ValidBootstrap -Payload @{ task_id = 'fixture-task-alias-underscore' }
    $case3 = Invoke-ValidBootstrap -Payload @{ taskID = 'fixture-task-alias-uppercase' }

    Assert-FailOpen -RawInput (@{ workspace = 'missing-task-identity' } | ConvertTo-Json -Compress)
    Assert-FailOpen -RawInput (@{ taskId = 42 } | ConvertTo-Json -Compress)
    Assert-FailOpen -RawInput (@{ taskId = '   ' } | ConvertTo-Json -Compress)
    Assert-FailOpen -RawInput '{invalid'

    $privacyMarkers = @(
        'TASK-ID-PRIVATE-MARKER',
        'WORKSPACE-PRIVATE-MARKER',
        'MODEL-PRIVATE-MARKER',
        'PROMPT-PRIVATE-MARKER',
        'SESSION-PRIVATE-MARKER',
        'ENDPOINT-PRIVATE-MARKER'
    )
    $beforePrivacyFiles = @(
        Get-ChildItem -LiteralPath $testTempRoot -Recurse -File -ErrorAction SilentlyContinue |
            ForEach-Object { $_.FullName }
    )
    $privacyCase = Invoke-ValidBootstrap -Payload @{
        taskId = $privacyMarkers[0]
        workspace = $privacyMarkers[1]
        model = $privacyMarkers[2]
        prompt = $privacyMarkers[3]
        session = $privacyMarkers[4]
        endpoint = $privacyMarkers[5]
    }
    foreach ($marker in $privacyMarkers) {
        Assert-TextAbsent -Text $privacyCase.Invocation.Stdout -Forbidden $marker -Message 'A private marker leaked to TaskStart stdout.'
        Assert-TextAbsent -Text $privacyCase.Bootstrap -Forbidden $marker -Message 'A private marker leaked to the bootstrap.'
    }
    $afterPrivacyFiles = @(
        Get-ChildItem -LiteralPath $testTempRoot -Recurse -File -ErrorAction SilentlyContinue |
            ForEach-Object { $_.FullName }
    )
    $newPrivacyFiles = @($afterPrivacyFiles | Where-Object { $beforePrivacyFiles -notcontains $_ })
    Assert-Condition -Condition ($newPrivacyFiles.Count -eq 1) -Message 'TaskStart created files outside the single bounded contract probe.'
    $expectedProbeRoot = [System.IO.Path]::GetFullPath(
        (Join-Path $testTempRoot 'aicarmine-cline-hooks\contract-probe')
    )
    foreach ($newFile in $newPrivacyFiles) {
        Assert-Condition -Condition $newFile.StartsWith(
            $expectedProbeRoot,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -Message 'TaskStart created a file outside the contract probe directory.'
        $fileText = [System.IO.File]::ReadAllText($newFile, [System.Text.Encoding]::UTF8)
        foreach ($marker in $privacyMarkers) {
            Assert-TextAbsent -Text $fileText -Forbidden $marker -Message 'A private marker was persisted by the contract probe.'
        }
    }

    $bootstrap = $case1.Bootstrap
    $families = @(
        'aicarmine_repo_state',
        'aicarmine_repo_search_det',
        'aicarmine_repo_code',
        'aicarmine_repo_validate',
        'aicarmine_git_readonly',
        'aicarmine_project_memory',
        'aicarmine_job_artifact',
        'aicarmine_job_view',
        'aicarmine_rag',
        'aicarmine_sqlite_readonly',
        'aicarmine_codex_ops'
    )
    foreach ($family in $families) {
        Assert-Condition -Condition $bootstrap.Contains($family) -Message ('Missing MCP family: ' + $family)
    }

    Assert-Condition -Condition ([regex]::Matches($bootstrap, 'agentic loop', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase).Count -eq 1) -Message 'agentic loop must appear only in the restricted-activation boundary.'
    Assert-Condition -Condition ([regex]::Matches($bootstrap, 'local subagent', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase).Count -eq 1) -Message 'local subagent must appear only in the restricted-activation boundary.'
    Assert-Condition -Condition ($bootstrap -notmatch '(?i)\bendpoints?\b|\bports?\b|\b\d{2,5}\b') -Message 'The bootstrap contains an endpoint or port.'
    Assert-Condition -Condition ($bootstrap -notmatch '(?i)\bpowershell\b|\bcmd\.exe\b|\bbash\b|\brestart\b|\breload\b') -Message 'The bootstrap contains a shell command or automatic restart instruction.'
    Assert-TextAbsent -Text $bootstrap -Forbidden 'cancel=true' -Message 'The bootstrap mentions cancel=true.'

    Assert-Condition -Condition $bootstrap.Contains('Editing discipline:') -Message 'Editing discipline is missing.'
    Assert-Condition -Condition $bootstrap.Contains('Choose the editing mechanism that best fits the current task and the tools actually exposed by the client.') -Message 'Editing-method neutrality guidance is missing.'
    Assert-Condition -Condition $bootstrap.Contains('minimal, scoped and reversible') -Message 'Minimal scoped reversible editing guidance is missing.'
    Assert-Condition -Condition $bootstrap.Contains('preserve architecture, contracts and unrelated modifications') -Message 'Preservation guidance is missing.'
    Assert-Condition -Condition $bootstrap.Contains('inspect the result') -Message 'Result inspection guidance is missing.'
    Assert-Condition -Condition $bootstrap.Contains('targeted verification') -Message 'Targeted verification guidance is missing.'
    Assert-Condition -Condition $bootstrap.Contains('current Cline tool schema') -Message 'Current client schema guidance is missing.'

    $forbiddenEditingTerms = @(
        'structured_edit',
        'unified_diff',
        'unified diff',
        'change_set_id',
        'apply-check',
        'git_apply_check',
        'manual .diff',
        'whole-file',
        'whole file'
    )
    foreach ($forbiddenTerm in $forbiddenEditingTerms) {
        Assert-TextAbsent -Text $bootstrap -Forbidden $forbiddenTerm -Message ('A prescribed editing term is present: ' + $forbiddenTerm)
    }

    Assert-Condition -Condition $bootstrap.Contains('Hooks are advisory and observational.') -Message 'Advisory hook separation is missing.'
    Assert-Condition -Condition $bootstrap.Contains('Cline auto-approval and MCP write guards remain authoritative.') -Message 'Auto-approval separation is missing.'

    $forbiddenRoutingTerms = @(
        'Task classes:',
        'Preferred sequence:',
        'routing score',
        'regex',
        'negation window',
        'recent_tool_outcomes',
        'pending_tool_calls'
    )
    foreach ($forbiddenTerm in $forbiddenRoutingTerms) {
        Assert-TextAbsent -Text $bootstrap -Forbidden $forbiddenTerm -Message ('Task-specific routing was duplicated: ' + $forbiddenTerm)
    }

    Assert-Condition -Condition ($case1.Bootstrap -eq $case2.Bootstrap) -Message 'Bootstrap output changed with a different task identity alias.'
    Assert-Condition -Condition ($case1.Bootstrap -eq $case3.Bootstrap) -Message 'Bootstrap output changed with a different task identity value.'
    Assert-Condition -Condition ($bootstrap -notmatch '(?i)\btimestamp\b|\bnonce\b|\bpath\b') -Message 'The deterministic bootstrap contains task-specific metadata.'
}
finally {
    if (Test-Path -LiteralPath $testTempRoot -PathType Container) {
        $resolvedCleanup = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $testTempRoot).Path)
        if ($resolvedCleanup.StartsWith($tempParent, [System.StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $resolvedCleanup -Recurse -Force
        }
    }
}

[Console]::Out.WriteLine('ALL AICARMINE CLINE TASK BOOTSTRAP TESTS PASSED')
