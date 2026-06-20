# Dedicated tests for AICarmine Cline PreCompact continuity

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$userPromptPath = Join-Path $repoRoot '.clinerules\hooks\UserPromptSubmit.ps1'
$preToolPath = Join-Path $repoRoot '.clinerules\hooks\PreToolUse.ps1'
$postToolPath = Join-Path $repoRoot '.clinerules\hooks\PostToolUse.ps1'
$preCompactPath = Join-Path $repoRoot '.clinerules\hooks\PreCompact.ps1'
$contractTestPath = Join-Path $PSScriptRoot 'Test-AICarmineClineHookContract.ps1'
$preHelperPath = Join-Path $repoRoot '.clinerules\hooks\lib\aicarmine_cline_pretool_observer.ps1'
$continuityHelperPath = Join-Path $repoRoot '.clinerules\hooks\lib\aicarmine_cline_precompact_continuity.ps1'
$powershellPath = [IO.Path]::GetFullPath((Get-Command powershell.exe -ErrorAction Stop).Source)
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('aicarmine-cline-precompact-test-{0}' -f [Guid]::NewGuid().ToString('N'))
$originalTemp = $env:TEMP
$originalTmp = $env:TMP
[void][IO.Directory]::CreateDirectory($testRoot)
$env:TEMP = $testRoot
$env:TMP = $testRoot

. $preHelperPath
. $continuityHelperPath

function Assert-AICarmine {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Get-AICarmineTestSha256 {
    param([string]$Text)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = (New-Object Text.UTF8Encoding($false)).GetBytes($Text)
        return (($sha.ComputeHash($bytes) | ForEach-Object { '{0:x2}' -f $_ }) -join '')
    }
    finally { $sha.Dispose() }
}

function Get-AICarmineFileSha256 {
    param([string]$Path)
    $stream = [IO.File]::OpenRead($Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return (($sha.ComputeHash($stream) | ForEach-Object { '{0:x2}' -f $_ }) -join '')
    }
    finally {
        $stream.Dispose()
        $sha.Dispose()
    }
}

function ConvertTo-AICarmineJson {
    param($Value)
    return $Value | ConvertTo-Json -Compress -Depth 12
}

function ConvertFrom-AICarmineHookOutput {
    param([string]$Stdout)
    $lines = @($Stdout.Replace([string][char]13, '').Split([char]10) |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    Assert-AICarmine ($lines.Count -eq 1) 'Hook stdout must contain exactly one non-empty line.'
    return $lines[0] | ConvertFrom-Json -ErrorAction Stop
}

function Invoke-AICarmineProcess {
    param([string]$ScriptPath, [AllowEmptyString()][string]$RawInput)

    $psi = New-Object Diagnostics.ProcessStartInfo
    $psi.FileName = $powershellPath
    $psi.Arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f ([IO.Path]::GetFullPath($ScriptPath))
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $psi.EnvironmentVariables['TEMP'] = $testRoot
    $psi.EnvironmentVariables['TMP'] = $testRoot
    $process = [Diagnostics.Process]::Start($psi)
    $stopwatch = [Diagnostics.Stopwatch]::StartNew()
    try {
        $process.StandardInput.Write($RawInput)
        $process.StandardInput.Close()
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        $stopwatch.Stop()
        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            Stdout = $stdout
            Stderr = $stderr
            ElapsedMilliseconds = [int]$stopwatch.ElapsedMilliseconds
        }
    }
    finally { $process.Dispose() }
}

function Invoke-AICarmineHook {
    param([string]$ScriptPath, [AllowEmptyString()][string]$RawInput)
    $result = Invoke-AICarmineProcess -ScriptPath $ScriptPath -RawInput $RawInput
    Assert-AICarmine ($result.ExitCode -eq 0) ('Hook exit code was non-zero: {0}' -f $ScriptPath)
    Assert-AICarmine ([string]::IsNullOrEmpty($result.Stderr)) ('Hook stderr was not empty: {0}' -f $ScriptPath)
    $contract = ConvertFrom-AICarmineHookOutput -Stdout $result.Stdout
    Assert-AICarmine (-not $contract.cancel) ('Hook returned cancel=true: {0}' -f $ScriptPath)
    Assert-AICarmine ($contract.errorMessage -eq '') ('Hook returned errorMessage: {0}' -f $ScriptPath)
    return [pscustomobject]@{
        Contract = $contract
        Stdout = $result.Stdout
        Stderr = $result.Stderr
        ElapsedMilliseconds = $result.ElapsedMilliseconds
    }
}

function Invoke-AICarmineUserPrompt {
    param([string]$TaskId, [string]$Prompt)
    return Invoke-AICarmineHook -ScriptPath $userPromptPath -RawInput (
        ConvertTo-AICarmineJson ([ordered]@{ taskId = $TaskId; prompt = $Prompt })
    )
}

function Invoke-AICarminePreCompact {
    param([string]$TaskId)
    return Invoke-AICarmineHook -ScriptPath $preCompactPath -RawInput (
        ConvertTo-AICarmineJson ([ordered]@{ taskId = $TaskId })
    )
}

function New-AICarmineMcpInput {
    param([string]$Query)
    return [ordered]@{
        server_name = 'aicarmine_repo_search_det'
        tool_name = 'aicarmine_repo_search_rg'
        arguments = [ordered]@{ query = $Query }
    }
}

function New-AICarminePrePayload {
    param([string]$TaskId, [string]$InvocationId, $ToolInput)
    return [ordered]@{
        taskId = $TaskId
        toolUseId = $InvocationId
        toolName = 'use_mcp_tool'
        toolInput = $ToolInput
    }
}

function New-AICarminePostPayload {
    param([string]$TaskId, [string]$InvocationId, $ToolResult, $Success)
    return [ordered]@{
        taskId = $TaskId
        toolUseId = $InvocationId
        toolName = 'use_mcp_tool'
        toolResult = $ToolResult
        success = $Success
    }
}

function Invoke-AICarminePre {
    param($Payload)
    return Invoke-AICarmineHook -ScriptPath $preToolPath -RawInput (ConvertTo-AICarmineJson $Payload)
}

function Invoke-AICarminePost {
    param($Payload)
    return Invoke-AICarmineHook -ScriptPath $postToolPath -RawInput (ConvertTo-AICarmineJson $Payload)
}

function Get-AICarmineObserverRootPath {
    return Join-Path $testRoot 'aicarmine-cline-hooks\pretool-observer'
}

function Get-AICarmineStatePath {
    param([string]$TaskId)
    return Join-Path (Get-AICarmineObserverRootPath) ('routing-{0}.json' -f (Get-AICarmineTestSha256 $TaskId))
}

function Get-AICarmineState {
    param([string]$TaskId)
    $path = Get-AICarmineStatePath $TaskId
    Assert-AICarmine (Test-Path -LiteralPath $path -PathType Leaf) ('Routing state missing for task {0}.' -f $TaskId)
    return [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8) | ConvertFrom-Json -ErrorAction Stop
}

function Write-AICarmineState {
    param([string]$TaskId, $State)
    $json = $State | ConvertTo-Json -Compress -Depth 12
    [IO.File]::WriteAllText((Get-AICarmineStatePath $TaskId), $json, (New-Object Text.UTF8Encoding($false)))
}

function New-AICarminePending {
    param([int]$Index)
    $digest = Get-AICarmineTestSha256 ('pending-{0}' -f $Index)
    return [ordered]@{
        timestamp_utc = [DateTime]::UtcNow.ToString('o')
        invocation_key_sha256 = $digest
        tool_call_sha256 = $digest
        selected_tool_kind = 'mcp'
        selected_wrapper_tool_name = 'use_mcp_tool'
        selected_mcp_server_name = 'aicarmine_repo_search_det'
        selected_mcp_tool_name = 'aicarmine_repo_search_rg'
    }
}

function New-AICarmineOutcome {
    param([int]$Index, [DateTime]$Timestamp, [string]$Outcome, [string]$FailureSignal)
    $digest = Get-AICarmineTestSha256 ('outcome-{0}' -f $Index)
    return [ordered]@{
        timestamp_utc = $Timestamp.ToUniversalTime().ToString('o')
        invocation_key_sha256 = $digest
        tool_call_sha256 = $digest
        selected_tool_kind = 'mcp'
        selected_wrapper_tool_name = 'use_mcp_tool'
        selected_mcp_server_name = 'aicarmine_repo_search_det'
        selected_mcp_tool_name = 'aicarmine_repo_search_rg'
        outcome = $Outcome
        failure_signal = $FailureSignal
        correlation_method = 'invocation_id'
        result_sha256 = $digest
        error_type = ''
        error_message_sha256 = ''
    }
}

function Start-AICarmineMutexHolder {
    param([string]$TaskId, [int]$HoldMilliseconds)

    $mutexName = 'Local\AICarmineClinePreTool-{0}' -f (Get-AICarmineTestSha256 $TaskId)
    $holderCode = @'
$mutex = New-Object Threading.Mutex($false, '__MUTEX__')
[void]$mutex.WaitOne()
[Console]::Out.WriteLine('LOCKED')
[Console]::Out.Flush()
[Threading.Thread]::Sleep(__HOLD__)
$mutex.ReleaseMutex()
$mutex.Dispose()
'@
    $holderCode = $holderCode.Replace('__MUTEX__', $mutexName).Replace('__HOLD__', [string]$HoldMilliseconds)
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($holderCode))
    $psi = New-Object Diagnostics.ProcessStartInfo
    $psi.FileName = $powershellPath
    $psi.Arguments = '-NoProfile -NonInteractive -EncodedCommand {0}' -f $encoded
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $process = [Diagnostics.Process]::Start($psi)
    $ready = $process.StandardOutput.ReadLine()
    Assert-AICarmine ($ready -eq 'LOCKED') 'Mutex holder did not acquire the lock.'
    return $process
}

function Complete-AICarmineMutexHolder {
    param($Process)
    try {
        [void]$Process.StandardOutput.ReadToEnd()
        $stderr = $Process.StandardError.ReadToEnd()
        $Process.WaitForExit()
        Assert-AICarmine ($Process.ExitCode -eq 0) 'Mutex holder exit code was non-zero.'
        $allowedProgress = -not [string]::IsNullOrEmpty($stderr) -and
            $stderr.StartsWith('#< CLIXML', [StringComparison]::Ordinal) -and
            $stderr.Contains('S="progress"') -and -not $stderr.Contains('S="Error"')
        Assert-AICarmine ([string]::IsNullOrEmpty($stderr) -or $allowedProgress) 'Mutex holder stderr was not allowed.'
    }
    finally { $Process.Dispose() }
}

$sourcePaths = @($preCompactPath, $preHelperPath, $continuityHelperPath, $PSCommandPath)
$sourceHashes = [ordered]@{}
foreach ($path in $sourcePaths) { $sourceHashes[$path] = Get-AICarmineFileSha256 $path }

try {
    $case1 = Invoke-AICarminePreCompact 'precompact-no-state'
    Assert-AICarmine ($case1.Contract.contextModification -eq '') 'Case 1 emitted a packet.'

    $task2 = 'precompact-base'
    $prompt2 = 'Trova la definizione e i caller del simbolo.'
    [void](Invoke-AICarmineUserPrompt $task2 $prompt2)
    $case2 = Invoke-AICarminePreCompact $task2
    $packet2 = [string]$case2.Contract.contextModification
    Assert-AICarmine ($packet2.Contains('AICARMINE COMPACTION CONTINUITY')) 'Case 2 missing packet header.'
    Assert-AICarmine ($packet2.Contains('- primary: repository_search')) 'Case 2 primary class incorrect.'
    Assert-AICarmine ($packet2.Contains('aicarmine_repo_search_')) 'Case 2 missing preferred search MCP.'
    Assert-AICarmine (-not $packet2.Contains($prompt2)) 'Case 2 exposed the raw prompt.'

    $task3 = 'precompact-primary-secondary'
    [void](Invoke-AICarmineUserPrompt $task3 'Verifica il reviewed probe e controlla branch e working tree.')
    $packet3 = [string](Invoke-AICarminePreCompact $task3).Contract.contextModification
    Assert-AICarmine ($packet3.Contains('- primary: repository_validation')) 'Case 3 primary class incorrect.'
    Assert-AICarmine ($packet3.Contains('repository_state')) 'Case 3 missing repository_state secondary.'
    Assert-AICarmine ($packet3.IndexOf('aicarmine_repo_validate_probe_profiles') -lt $packet3.IndexOf('aicarmine_repo_state_health')) 'Case 3 probe flow was not first.'
    $secondaryLine3 = @($packet3 -split '\r?\n' | Where-Object { $_ -like '- secondary:*' })[0]
    Assert-AICarmine (@($secondaryLine3.Substring(12).Split(',') | Where-Object { $_.Trim() -ne 'none' }).Count -le 3) 'Case 3 exceeded secondary bound.'

    $task4 = 'precompact-constraints'
    $prompt4 = 'Esegui il reviewed probe orientation.selector.contract.v1.' +
        [Environment]::NewLine + 'MODE: READ_ONLY'
    [void](Invoke-AICarmineUserPrompt $task4 $prompt4)
    $state4 = Get-AICarmineState $task4
    $packet4 = [string](Invoke-AICarminePreCompact $task4).Contract.contextModification
    Assert-AICarmine ([bool]$state4.read_only) 'Case 4 state did not preserve structured read_only.'
    Assert-AICarmine (@($state4.constraints).Count -eq 1 -and $state4.constraints[0] -eq 'read_only') 'Case 4 state constraints were not structured-only.'
    Assert-AICarmine ($packet4.Contains('- read_only')) 'Case 4 packet missing structured read_only.'
    Assert-AICarmine (-not ($packet4 -match 'no_source_write|no_memory_write|no_commit|no_push|explicit_source_write|explicit_memory_write')) 'Case 4 propagated linguistic policy.'

    $task4b = 'precompact-natural-readonly'
    [void](Invoke-AICarmineUserPrompt $task4b 'Esegui il reviewed probe. Audit read-only, non modificare file.')
    $state4b = Get-AICarmineState $task4b
    $packet4b = [string](Invoke-AICarminePreCompact $task4b).Contract.contextModification
    Assert-AICarmine (-not [bool]$state4b.read_only) 'Case 4b inferred state read_only from natural language.'
    Assert-AICarmine (@($state4b.constraints).Count -eq 0) 'Case 4b persisted linguistic constraints.'
    Assert-AICarmine (-not $packet4b.Contains('- read_only')) 'Case 4b propagated natural-language read_only.'

    $task5 = 'precompact-existing-diff'
    [void](Invoke-AICarmineUserPrompt $task5 'Non applicare la patch; valida soltanto la unified diff esistente.')
    $packet5 = [string](Invoke-AICarminePreCompact $task5).Contract.contextModification
    Assert-AICarmine ($packet5.Contains('aicarmine_repo_code_unidiff_validate')) 'Case 5 missing validation tool.'
    Assert-AICarmine (-not $packet5.Contains('aicarmine_repo_code_apply_patch')) 'Case 5 included apply_patch.'
    Assert-AICarmine (-not $packet5.Contains('existing_diff_only')) 'Case 5 propagated existing diff as a policy constraint.'

    $task6 = 'precompact-failure'
    [void](Invoke-AICarmineUserPrompt $task6 'Cerca la definizione del simbolo failure.')
    $input6 = New-AICarmineMcpInput 'failure-query'
    [void](Invoke-AICarminePre (New-AICarminePrePayload $task6 'failure-invocation' $input6))
    $post6 = New-AICarminePostPayload $task6 'failure-invocation' ([ordered]@{ status = 'failed'; detail = 'raw-result-case6' }) $false
    $post6.errorMessage = 'raw-error-case6'
    [void](Invoke-AICarminePost $post6)
    $packet6 = [string](Invoke-AICarminePreCompact $task6).Contract.contextModification
    Assert-AICarmine ($packet6.Contains('Observed recent failures:')) 'Case 6 missing failure section.'
    Assert-AICarmine ($packet6.Contains('aicarmine_repo_search_rg | success_false | less_than_1m')) 'Case 6 failure summary incorrect.'
    Assert-AICarmine (-not ($packet6 -match 'raw-result-case6|raw-error-case6|[0-9a-f]{64}')) 'Case 6 exposed raw data or a digest.'

    $task7 = 'precompact-success'
    [void](Invoke-AICarmineUserPrompt $task7 'Cerca la definizione del simbolo success.')
    $input7 = New-AICarmineMcpInput 'success-query'
    [void](Invoke-AICarminePre (New-AICarminePrePayload $task7 'success-invocation' $input7))
    [void](Invoke-AICarminePost (New-AICarminePostPayload $task7 'success-invocation' ([ordered]@{ status = 'ok' }) $true))
    $packet7 = [string](Invoke-AICarminePreCompact $task7).Contract.contextModification
    Assert-AICarmine (-not $packet7.Contains('Observed recent failures:')) 'Case 7 included success as failure.'

    $task8 = 'precompact-stale-failure'
    [void](Invoke-AICarmineUserPrompt $task8 'Cerca la definizione del simbolo stale.')
    $state8 = Get-AICarmineState $task8
    $state8.recent_tool_outcomes = @(
        New-AICarmineOutcome 8 ([DateTime]::UtcNow.AddSeconds(-700)) 'failure' 'status_failure'
    )
    Write-AICarmineState $task8 $state8
    $packet8 = [string](Invoke-AICarminePreCompact $task8).Contract.contextModification
    Assert-AICarmine (-not $packet8.Contains('Observed recent failures:')) 'Case 8 included a stale failure.'

    $task9 = 'precompact-pending'
    [void](Invoke-AICarmineUserPrompt $task9 'Cerca la definizione del simbolo pending.')
    [void](Invoke-AICarminePre (New-AICarminePrePayload $task9 'pending-one' (New-AICarmineMcpInput 'pending-one')))
    [void](Invoke-AICarminePre (New-AICarminePrePayload $task9 'pending-two' (New-AICarmineMcpInput 'pending-two')))
    $packet9 = [string](Invoke-AICarminePreCompact $task9).Contract.contextModification
    Assert-AICarmine ($packet9.Contains('- count: 2')) 'Case 9 pending count was not two.'
    Assert-AICarmine (-not ($packet9 -match 'pending-one|pending-two|[0-9a-f]{64}')) 'Case 9 exposed pending identity or digest.'

    Assert-AICarmine (-not $packet9.Contains('Observed recent failures:')) 'Case 10 interpreted pending as failure.'
    Assert-AICarmine (-not $packet9.Contains('retry after failure')) 'Case 10 invented retry-after-failure semantics.'

    $task11 = 'precompact-bounded'
    [void](Invoke-AICarmineUserPrompt $task11 'Cerca la definizione del simbolo bounded.')
    $state11 = Get-AICarmineState $task11
    $state11.classes = @('repository_validation', 'repository_patch', 'repository_search', 'project_memory')
    $state11.preferred_tools = @(
        'aicarmine_repo_validate_probe_profiles',
        'aicarmine_repo_validate_probe_run',
        'aicarmine_repo_code_health',
        'aicarmine_repo_code_propose_edit',
        'aicarmine_repo_code_unidiff_validate',
        'aicarmine_repo_code_git_apply_check'
    )
    $state11.constraints = @('read_only', 'no_source_write', 'no_memory_write', 'no_service_mutation', 'no_commit', 'no_push', 'existing_diff_only', 'explicit_memory_write', 'explicit_source_write')
    $pending11 = @()
    for ($index = 0; $index -lt 32; $index++) { $pending11 += New-AICarminePending $index }
    $state11.pending_tool_calls = @($pending11)
    $state11.recent_tool_outcomes = @(
        New-AICarmineOutcome 110 ([DateTime]::UtcNow.AddSeconds(-10)) 'failure' 'success_false'
        New-AICarmineOutcome 111 ([DateTime]::UtcNow.AddSeconds(-120)) 'failure' 'status_failure'
        New-AICarmineOutcome 112 ([DateTime]::UtcNow.AddSeconds(-400)) 'failure' 'is_error_true'
    )
    Write-AICarmineState $task11 $state11
    $case11 = Invoke-AICarminePreCompact $task11
    $packet11 = [string]$case11.Contract.contextModification
    Assert-AICarmine ($packet11.Length -le 1800) 'Case 11 packet exceeded 1800 characters.'
    Assert-AICarmine ($packet11.Contains('- read_only')) 'Case 11 lost structured read_only.'
    Assert-AICarmine (-not ($packet11 -match 'no_source_write|no_memory_write|no_service_mutation|no_commit|no_push|existing_diff_only|explicit_memory_write|explicit_source_write')) 'Case 11 propagated legacy policy constraints.'
    Assert-AICarmine ($packet11.EndsWith('- Preserve only explicitly structured task constraints after compaction.')) 'Case 11 packet ended on a partial line.'
    [void](ConvertFrom-AICarmineHookOutput $case11.Stdout)

    $case12Result = Invoke-AICarmineHook -ScriptPath $preCompactPath -RawInput '{invalid'
    Assert-AICarmine ($case12Result.Contract.contextModification -eq '') 'Case 12 invalid JSON emitted a packet.'

    $task13A = 'precompact-task-a'
    [void](Invoke-AICarmineUserPrompt $task13A 'Cerca la definizione del simbolo taskA.')
    $case13 = Invoke-AICarminePreCompact 'precompact-task-b'
    Assert-AICarmine ($case13.Contract.contextModification -eq '') 'Case 13 fell back to another task state.'

    $sensitive = @(
        'PROMPT-PRIVATE-H5',
        'TOKEN-PRIVATE-H5',
        'PASSWORD-PRIVATE-H5',
        'COMMAND-PRIVATE-H5',
        'ERROR-PRIVATE-H5',
        'RESULT-PRIVATE-H5',
        'TASK-ID-PRIVATE-H5',
        'INVOCATION-ID-PRIVATE-H5'
    )
    $task14 = $sensitive[6]
    [void](Invoke-AICarmineUserPrompt $task14 ('Cerca la definizione del simbolo {0}.' -f $sensitive[0]))
    $input14 = [ordered]@{
        server_name = 'aicarmine_repo_search_det'
        tool_name = 'aicarmine_repo_search_rg'
        arguments = [ordered]@{ token = $sensitive[1]; password = $sensitive[2]; command = $sensitive[3] }
    }
    [void](Invoke-AICarminePre (New-AICarminePrePayload $task14 $sensitive[7] $input14))
    $post14 = New-AICarminePostPayload $task14 $sensitive[7] ([ordered]@{ status = 'failed'; detail = $sensitive[5] }) $false
    $post14.errorMessage = $sensitive[4]
    [void](Invoke-AICarminePost $post14)
    $case14 = Invoke-AICarminePreCompact $task14
    $persisted14 = [string]::Join([Environment]::NewLine, @(
        Get-ChildItem -LiteralPath $testRoot -File -Recurse | ForEach-Object {
            [IO.File]::ReadAllText($_.FullName, [Text.Encoding]::UTF8)
        }
    ))
    foreach ($marker in $sensitive) {
        Assert-AICarmine (-not $case14.Stdout.Contains($marker)) ('Case 14 stdout exposed {0}.' -f $marker)
        Assert-AICarmine (-not $persisted14.Contains($marker)) ('Case 14 persisted {0}.' -f $marker)
    }

    $task15 = 'precompact-mutex-wait'
    [void](Invoke-AICarmineUserPrompt $task15 'Cerca la definizione del simbolo mutex.')
    $holder15 = Start-AICarmineMutexHolder $task15 2000
    $case15 = Invoke-AICarminePreCompact $task15
    Complete-AICarmineMutexHolder $holder15
    Assert-AICarmine ($case15.ElapsedMilliseconds -ge 1500) 'Case 15 did not wait for the mutex.'
    Assert-AICarmine (-not [string]::IsNullOrEmpty($case15.Contract.contextModification)) 'Case 15 lost the packet after waiting.'

    $task16 = 'precompact-mutex-timeout'
    [void](Invoke-AICarmineUserPrompt $task16 'Cerca la definizione del simbolo timeout.')
    $statePath16 = Get-AICarmineStatePath $task16
    $hash16Before = Get-AICarmineFileSha256 $statePath16
    $holder16 = Start-AICarmineMutexHolder $task16 6500
    $case16 = Invoke-AICarminePreCompact $task16
    Complete-AICarmineMutexHolder $holder16
    Assert-AICarmine ($case16.ElapsedMilliseconds -ge 4500 -and $case16.ElapsedMilliseconds -lt 6500) 'Case 16 mutex timeout was not bounded near five seconds.'
    Assert-AICarmine ($case16.Contract.contextModification -eq '') 'Case 16 emitted a partial packet.'
    Assert-AICarmine ($hash16Before -eq (Get-AICarmineFileSha256 $statePath16)) 'Case 16 modified state.'

    $task17 = 'precompact-legacy-state'
    [void](Invoke-AICarmineUserPrompt $task17 'Cerca la definizione del simbolo legacy.')
    $state17 = Get-AICarmineState $task17
    $state17.read_only = $true
    $state17.explicit_existing_diff = $true
    $state17.PSObject.Properties.Remove('constraints')
    Write-AICarmineState $task17 $state17
    $packet17 = [string](Invoke-AICarminePreCompact $task17).Contract.contextModification
    Assert-AICarmine (-not $packet17.Contains('- read_only')) 'Case 17 trusted legacy read_only without a structured constraint.'
    Assert-AICarmine (-not $packet17.Contains('existing_diff_only')) 'Case 17 propagated legacy existing_diff_only as policy.'

    $task18 = 'precompact-legacy-constraints'
    [void](Invoke-AICarmineUserPrompt $task18 'Cerca la definizione del simbolo legacy constraints.')
    $state18 = Get-AICarmineState $task18
    $state18.constraints = @('no_source_write', 'no_memory_write', 'no_commit', 'no_push')
    Write-AICarmineState $task18 $state18
    $packet18 = [string](Invoke-AICarminePreCompact $task18).Contract.contextModification
    Assert-AICarmine (-not ($packet18 -match 'no_source_write|no_memory_write|no_commit|no_push')) 'Case 18 propagated legacy linguistic constraints.'
    $state18.constraints = @('read_only', 'no_source_write', 'no_memory_write', 'no_service_mutation', 'no_commit', 'no_push', 'existing_diff_only', 'explicit_memory_write', 'explicit_source_write', 'read_only')
    Write-AICarmineState $task18 $state18
    Assert-AICarmine ((Invoke-AICarminePreCompact $task18).Contract.contextModification -eq '') 'Case 18 accepted an over-bound constraint array.'

    $task19 = 'precompact-no-state-mutation'
    [void](Invoke-AICarmineUserPrompt $task19 'Cerca la definizione del simbolo immutable.')
    $statePath19 = Get-AICarmineStatePath $task19
    $hash19Before = Get-AICarmineFileSha256 $statePath19
    $state19Before = [IO.File]::ReadAllText($statePath19, [Text.Encoding]::UTF8)
    [void](Invoke-AICarminePreCompact $task19)
    $state19After = [IO.File]::ReadAllText($statePath19, [Text.Encoding]::UTF8)
    Assert-AICarmine ($hash19Before -eq (Get-AICarmineFileSha256 $statePath19)) 'Case 19 state hash changed.'
    Assert-AICarmine ($state19Before -eq $state19After) 'Case 19 state content changed.'

    $contract = Invoke-AICarmineProcess -ScriptPath $contractTestPath -RawInput ''
    Assert-AICarmine ($contract.ExitCode -eq 0) 'Case 20 contract test failed.'
    Assert-AICarmine ([string]::IsNullOrEmpty($contract.Stderr)) 'Case 20 contract stderr was not empty.'
    Assert-AICarmine ($contract.Stdout.Contains('Total hooks tested: 5')) 'Case 20 hook count mismatch.'
    Assert-AICarmine ($contract.Stdout.Contains('Passed: 5')) 'Case 20 pass count mismatch.'
    Assert-AICarmine ($contract.Stdout.Contains('Failed: 0')) 'Case 20 failure count mismatch.'
    Assert-AICarmine ($contract.Stdout.Contains('ALL AICARMINE CLINE HOOK CONTRACT TESTS PASSED')) 'Case 20 success marker missing.'

    foreach ($path in $sourcePaths) {
        Assert-AICarmine ($sourceHashes[$path] -eq (Get-AICarmineFileSha256 $path)) ('Hook execution modified source: {0}' -f $path)
    }

    Write-Host 'ALL AICARMINE CLINE PRECOMPACT CONTINUITY TESTS PASSED'
    exit 0
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
finally {
    $env:TEMP = $originalTemp
    $env:TMP = $originalTmp
    $tempPrefix = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    $resolved = [IO.Path]::GetFullPath($testRoot)
    if ($resolved.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase) -and
        $resolved -match 'aicarmine-cline-precompact-test-') {
        Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction SilentlyContinue
    }
}
