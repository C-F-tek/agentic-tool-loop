# Dedicated tests for AICarmine Cline PostToolUse correlation-only observer

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$userPromptPath = Join-Path $repoRoot '.clinerules\hooks\UserPromptSubmit.ps1'
$preToolPath = Join-Path $repoRoot '.clinerules\hooks\PreToolUse.ps1'
$postToolPath = Join-Path $repoRoot '.clinerules\hooks\PostToolUse.ps1'
$preHelperPath = Join-Path $repoRoot '.clinerules\hooks\lib\aicarmine_cline_pretool_observer.ps1'
$powershellPath = [IO.Path]::GetFullPath((Get-Command powershell.exe -ErrorAction Stop).Source)
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('aicarmine-cline-posttool-test-{0}' -f [Guid]::NewGuid().ToString('N'))
$originalTemp = $env:TEMP
$originalTmp = $env:TMP
[void][IO.Directory]::CreateDirectory($testRoot)
$env:TEMP = $testRoot
$env:TMP = $testRoot

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

function Start-AICarmineHookProcess {
    param([string]$ScriptPath, [string]$RawInput)

    $psi = New-Object Diagnostics.ProcessStartInfo
    $psi.FileName = $powershellPath
    $psi.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f ([IO.Path]::GetFullPath($ScriptPath))
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $psi.EnvironmentVariables['TEMP'] = $testRoot
    $psi.EnvironmentVariables['TMP'] = $testRoot
    $process = [Diagnostics.Process]::Start($psi)
    $process.StandardInput.Write($RawInput)
    $process.StandardInput.Close()
    return $process
}

function Complete-AICarmineHookProcess {
    param($Process)
    try {
        $stdout = $Process.StandardOutput.ReadToEnd()
        $stderr = $Process.StandardError.ReadToEnd()
        $Process.WaitForExit()
        return [pscustomobject]@{ ExitCode = $Process.ExitCode; Stdout = $stdout; Stderr = $stderr }
    }
    finally { $Process.Dispose() }
}

function ConvertFrom-AICarmineHookOutput {
    param([string]$Stdout)
    $lines = @($Stdout.Replace([string][char]13, '').Split([char]10) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    Assert-AICarmine ($lines.Count -eq 1) 'Hook stdout must contain exactly one non-empty line.'
    return $lines[0] | ConvertFrom-Json -ErrorAction Stop
}

function Invoke-AICarmineHook {
    param([string]$ScriptPath, [string]$RawInput)
    $result = Complete-AICarmineHookProcess -Process (Start-AICarmineHookProcess -ScriptPath $ScriptPath -RawInput $RawInput)
    Assert-AICarmine ($result.ExitCode -eq 0) ('Hook exit code was non-zero: {0}' -f $ScriptPath)
    Assert-AICarmine ([string]::IsNullOrEmpty($result.Stderr)) ('Hook stderr was not empty: {0}' -f $ScriptPath)
    $contract = ConvertFrom-AICarmineHookOutput -Stdout $result.Stdout
    Assert-AICarmine (-not $contract.cancel) ('Hook returned cancel=true: {0}' -f $ScriptPath)
    Assert-AICarmine ($contract.errorMessage -eq '') ('Hook returned errorMessage: {0}' -f $ScriptPath)
    return [pscustomobject]@{ Contract = $contract; Stdout = $result.Stdout; Stderr = $result.Stderr }
}

function ConvertTo-AICarmineJson {
    param($Value)
    return $Value | ConvertTo-Json -Compress -Depth 12
}

function Invoke-AICarmineUserPrompt {
    param([string]$TaskId, [string]$Prompt)
    return Invoke-AICarmineHook -ScriptPath $userPromptPath -RawInput (ConvertTo-AICarmineJson ([ordered]@{ taskId = $TaskId; prompt = $Prompt }))
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

function Get-AICarmineState {
    param([string]$TaskId)
    $path = Join-Path (Get-AICarmineObserverRootPath) ('routing-{0}.json' -f (Get-AICarmineTestSha256 $TaskId))
    Assert-AICarmine (Test-Path -LiteralPath $path -PathType Leaf) ('Routing state missing for task {0}.' -f $TaskId)
    return [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8) | ConvertFrom-Json -ErrorAction Stop
}

function Get-AICarmineLatestObservation {
    param([string]$TaskId, [ValidateSet('pre', 'post')][string]$Kind)
    $directory = if ($Kind -eq 'pre') {
        Join-Path (Get-AICarmineObserverRootPath) 'observations'
    }
    else {
        Join-Path (Get-AICarmineObserverRootPath) 'post-observations'
    }
    $taskKey = Get-AICarmineTestSha256 $TaskId
    $matches = [Collections.Generic.List[object]]::new()
    if (Test-Path -LiteralPath $directory -PathType Container) {
        foreach ($file in @(Get-ChildItem -LiteralPath $directory -Filter '*.json' -File | Sort-Object LastWriteTimeUtc, Name)) {
            $value = [IO.File]::ReadAllText($file.FullName, [Text.Encoding]::UTF8) | ConvertFrom-Json -ErrorAction Stop
            if ($value.task_key_sha256 -eq $taskKey) { [void]$matches.Add($value) }
        }
    }
    Assert-AICarmine ($matches.Count -gt 0) ('No {0} observation for task {1}.' -f $Kind, $TaskId)
    return $matches[$matches.Count - 1]
}

function Assert-AICarmineCode {
    param($Observation, [string]$Code, [bool]$Expected)
    $actual = @($Observation.advisory_codes) -contains $Code
    Assert-AICarmine ($actual -eq $Expected) ('Unexpected advisory code {0}: expected {1}.' -f $Code, $Expected)
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
    param([string]$TaskId, [string]$InvocationId, [string]$ToolName, $ToolInput)
    $payload = [ordered]@{ taskId = $TaskId; toolName = $ToolName }
    if (-not [string]::IsNullOrEmpty($InvocationId)) { $payload.toolUseId = $InvocationId }
    if ($null -ne $ToolInput) { $payload.toolInput = $ToolInput }
    return $payload
}

function New-AICarminePostPayload {
    param([string]$TaskId, [string]$InvocationId, [string]$ToolName, $ToolInput, $ToolResult, $Success)
    $payload = [ordered]@{ taskId = $TaskId; toolName = $ToolName }
    if (-not [string]::IsNullOrEmpty($InvocationId)) { $payload.toolUseId = $InvocationId }
    if ($null -ne $ToolInput) { $payload.toolInput = $ToolInput }
    if ($null -ne $ToolResult) { $payload.toolResult = $ToolResult }
    if ($null -ne $Success) { $payload.success = $Success }
    return $payload
}

function Start-AICarmineMutexHolder {
    param([string]$TaskId, [int]$HoldMilliseconds, [bool]$Abandon)

    $mutexName = 'Local\AICarmineClinePreTool-{0}' -f (Get-AICarmineTestSha256 $TaskId)
    $holderCode = @'
$mutex = New-Object Threading.Mutex($false, '__MUTEX__')
[void]$mutex.WaitOne()
[Console]::Out.WriteLine('LOCKED')
[Console]::Out.Flush()
Start-Sleep -Milliseconds __HOLD__
if (__ABANDON__) { exit 0 }
$mutex.ReleaseMutex()
$mutex.Dispose()
'@
    $holderCode = $holderCode.Replace('__MUTEX__', $mutexName).Replace('__HOLD__', [string]$HoldMilliseconds)
    $holderCode = $holderCode.Replace('__ABANDON__', $(if ($Abandon) { '$true' } else { '$false' }))
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($holderCode))
    $psi = New-Object Diagnostics.ProcessStartInfo
    $psi.FileName = $powershellPath
    $psi.Arguments = '-NoProfile -EncodedCommand {0}' -f $encoded
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
        $rest = $Process.StandardOutput.ReadToEnd()
        $stderr = $Process.StandardError.ReadToEnd()
        $Process.WaitForExit()
        Assert-AICarmine ($Process.ExitCode -eq 0) 'Mutex holder exit code was non-zero.'
        $allowedProgress = -not [string]::IsNullOrEmpty($stderr) -and
            $stderr.StartsWith('#< CLIXML', [StringComparison]::Ordinal) -and
            $stderr.Contains('S="progress"') -and
            -not $stderr.Contains('S="Error"')
        Assert-AICarmine ([string]::IsNullOrEmpty($stderr) -or $allowedProgress) 'Mutex holder stderr contained a non-progress record.'
    }
    finally { $Process.Dispose() }
}

try {
    # Case 1: success correlated by invocation ID.
    $task1 = 'post-success-invocation'
    [void](Invoke-AICarmineUserPrompt $task1 'Cerca la definizione del simbolo case1')
    $input1 = New-AICarmineMcpInput 'case1'
    [void](Invoke-AICarminePre (New-AICarminePrePayload $task1 'invocation-case-1' 'use_mcp_tool' $input1))
    $post1 = Invoke-AICarminePost (New-AICarminePostPayload $task1 'invocation-case-1' 'use_mcp_tool' $null ([ordered]@{ status = 'ok' }) $true)
    $obs1 = Get-AICarmineLatestObservation $task1 post
    Assert-AICarmineCode $obs1 'correlated_by_invocation_id' $true
    Assert-AICarmine ($obs1.outcome -eq 'success') 'Case 1 outcome was not success.'
    Assert-AICarmine (@((Get-AICarmineState $task1).pending_tool_calls).Count -eq 0) 'Case 1 pending was not removed.'
    Assert-AICarmine ($post1.Contract.contextModification -eq '') 'Case 1 emitted contextModification.'
    Assert-AICarmine (-not ([IO.File]::ReadAllText((Join-Path (Get-AICarmineObserverRootPath) ('routing-{0}.json' -f (Get-AICarmineTestSha256 $task1)))).Contains('invocation-case-1'))) 'Case 1 persisted raw invocation ID.'

    # Case 2: failure correlated by invocation ID.
    $task2 = 'post-failure-invocation'
    [void](Invoke-AICarmineUserPrompt $task2 'Cerca la definizione del simbolo case2')
    $input2 = New-AICarmineMcpInput 'case2'
    [void](Invoke-AICarminePre (New-AICarminePrePayload $task2 'invocation-case-2' 'use_mcp_tool' $input2))
    $post2Payload = New-AICarminePostPayload $task2 'invocation-case-2' 'use_mcp_tool' $null ([ordered]@{ status = 'failed' }) $false
    $post2Payload.errorMessage = 'fixture-secret-error'
    $post2 = Invoke-AICarminePost $post2Payload
    $obs2 = Get-AICarmineLatestObservation $task2 post
    Assert-AICarmine ($obs2.outcome -eq 'failure' -and $obs2.failure_signal -eq 'success_false') 'Case 2 failure priority was incorrect.'
    Assert-AICarmine ($post2.Contract.contextModification.Contains('observed failure')) 'Case 2 failure advisory missing.'
    Assert-AICarmine ($obs2.error_message_sha256 -match '^[0-9a-f]{64}$') 'Case 2 error message hash missing.'

    # Case 3: correlation by complete tool-call digest.
    $task3 = 'post-tool-call-digest'
    [void](Invoke-AICarmineUserPrompt $task3 'Cerca la definizione del simbolo case3')
    $input3 = New-AICarmineMcpInput 'case3'
    [void](Invoke-AICarminePre (New-AICarminePrePayload $task3 '' 'use_mcp_tool' $input3))
    [void](Invoke-AICarminePost (New-AICarminePostPayload $task3 '' 'use_mcp_tool' $input3 ([ordered]@{ status = 'ok' }) $true))
    $obs3 = Get-AICarmineLatestObservation $task3 post
    Assert-AICarmine ($obs3.correlation_method -eq 'tool_call_sha256') 'Case 3 did not correlate by tool-call digest.'
    Assert-AICarmine (@((Get-AICarmineState $task3).pending_tool_calls).Count -eq 0) 'Case 3 pending was not removed.'

    # Case 4: unique identity fallback.
    $task4 = 'post-unique-identity'
    [void](Invoke-AICarmineUserPrompt $task4 'Cerca la definizione del simbolo case4')
    [void](Invoke-AICarminePre (New-AICarminePrePayload $task4 '' 'aicarmine_repo_search_rg' ([ordered]@{ query = 'case4' })))
    [void](Invoke-AICarminePost (New-AICarminePostPayload $task4 '' 'aicarmine_repo_search_rg' $null ([ordered]@{ status = 'ok' }) $true))
    $obs4 = Get-AICarmineLatestObservation $task4 post
    Assert-AICarmine ($obs4.correlation_method -eq 'unique_identity') 'Case 4 did not use unique identity.'
    Assert-AICarmine (@((Get-AICarmineState $task4).pending_tool_calls).Count -eq 0) 'Case 4 pending was not removed.'

    # Case 5: ambiguous identity is never guessed.
    $task5 = 'post-ambiguous-identity'
    [void](Invoke-AICarmineUserPrompt $task5 'Cerca la definizione del simbolo case5')
    [void](Invoke-AICarminePre (New-AICarminePrePayload $task5 '' 'aicarmine_repo_search_rg' ([ordered]@{ query = 'case5-a' })))
    [void](Invoke-AICarminePre (New-AICarminePrePayload $task5 '' 'aicarmine_repo_search_rg' ([ordered]@{ query = 'case5-b' })))
    $before5 = Get-AICarmineState $task5
    [void](Invoke-AICarminePost (New-AICarminePostPayload $task5 '' 'aicarmine_repo_search_rg' $null ([ordered]@{ status = 'ok' }) $true))
    $obs5 = Get-AICarmineLatestObservation $task5 post
    $after5 = Get-AICarmineState $task5
    Assert-AICarmineCode $obs5 'correlation_ambiguous' $true
    Assert-AICarmine (@($after5.pending_tool_calls).Count -eq @($before5.pending_tool_calls).Count) 'Case 5 removed an ambiguous pending.'
    Assert-AICarmine (@($after5.recent_tool_outcomes).Count -eq 0) 'Case 5 added an outcome.'
    Assert-AICarmine (-not $obs5.context_modification_emitted) 'Case 5 emitted contextModification.'

    # Case 6: missing PreToolUse.
    $task6 = 'post-missing-pretool'
    [void](Invoke-AICarmineUserPrompt $task6 'Cerca la definizione del simbolo case6')
    [void](Invoke-AICarminePost (New-AICarminePostPayload $task6 '' 'aicarmine_repo_search_rg' $null ([ordered]@{ status = 'ok' }) $true))
    $obs6 = Get-AICarmineLatestObservation $task6 post
    Assert-AICarmineCode $obs6 'pretool_observation_missing' $true
    Assert-AICarmine (@((Get-AICarmineState $task6).recent_tool_outcomes).Count -eq 0) 'Case 6 inserted an uncorrelated outcome.'

    # Case 7: error string marker.
    $task7 = 'post-error-string'
    [void](Invoke-AICarmineUserPrompt $task7 'Cerca la definizione del simbolo case7')
    [void](Invoke-AICarminePre (New-AICarminePrePayload $task7 'invocation-case-7' 'aicarmine_repo_search_rg' ([ordered]@{ query = 'case7' })))
    [void](Invoke-AICarminePost (New-AICarminePostPayload $task7 'invocation-case-7' 'aicarmine_repo_search_rg' $null 'Error: fixture failure body' $null))
    $obs7 = Get-AICarmineLatestObservation $task7 post
    Assert-AICarmine ($obs7.outcome -eq 'failure' -and $obs7.failure_signal -eq 'result_error_prefix') 'Case 7 error prefix not classified.'

    # Case 8: unknown result.
    $task8 = 'post-unknown-result'
    [void](Invoke-AICarmineUserPrompt $task8 'Cerca la definizione del simbolo case8')
    [void](Invoke-AICarminePre (New-AICarminePrePayload $task8 'invocation-case-8' 'aicarmine_repo_search_rg' ([ordered]@{ query = 'case8' })))
    $post8 = Invoke-AICarminePost (New-AICarminePostPayload $task8 'invocation-case-8' 'aicarmine_repo_search_rg' $null ([ordered]@{ value = 7 }) $null)
    $obs8 = Get-AICarmineLatestObservation $task8 post
    Assert-AICarmine ($obs8.outcome -eq 'unknown') 'Case 8 was not unknown.'
    Assert-AICarmine ($post8.Contract.contextModification -eq '') 'Case 8 emitted contextModification.'

    # Case 9: identical retry after correlated failure.
    $task9 = 'pre-identical-after-failure'
    [void](Invoke-AICarmineUserPrompt $task9 'Cerca la definizione del simbolo case9')
    $input9 = New-AICarmineMcpInput 'case9'
    [void](Invoke-AICarminePre (New-AICarminePrePayload $task9 'invocation-case-9a' 'use_mcp_tool' $input9))
    [void](Invoke-AICarminePost (New-AICarminePostPayload $task9 'invocation-case-9a' 'use_mcp_tool' $null ([ordered]@{ status = 'failed' }) $false))
    $pre9 = Invoke-AICarminePre (New-AICarminePrePayload $task9 'invocation-case-9b' 'use_mcp_tool' $input9)
    $preObs9 = Get-AICarmineLatestObservation $task9 pre
    Assert-AICarmineCode $preObs9 'identical_tool_call_after_observed_failure' $true
    Assert-AICarmine ($pre9.Contract.contextModification.Contains('previously produced an observed failure')) 'Case 9 specific advisory missing.'
    Assert-AICarmine (-not $pre9.Contract.contextModification.Contains('already observed for this task')) 'Case 9 emitted generic repeated message.'

    # Case 10: identical call after success is not failure-specific.
    $task10 = 'pre-identical-after-success'
    [void](Invoke-AICarmineUserPrompt $task10 'Cerca la definizione del simbolo case10')
    $input10 = New-AICarmineMcpInput 'case10'
    [void](Invoke-AICarminePre (New-AICarminePrePayload $task10 'invocation-case-10a' 'use_mcp_tool' $input10))
    [void](Invoke-AICarminePost (New-AICarminePostPayload $task10 'invocation-case-10a' 'use_mcp_tool' $null ([ordered]@{ status = 'ok' }) $true))
    [void](Invoke-AICarminePre (New-AICarminePrePayload $task10 'invocation-case-10b' 'use_mcp_tool' $input10))
    Assert-AICarmineCode (Get-AICarmineLatestObservation $task10 pre) 'identical_tool_call_after_observed_failure' $false

    # Case 11: native selected after observed MCP failure.
    $task11 = 'native-after-mcp-failure'
    [void](Invoke-AICarmineUserPrompt $task11 'Cerca la definizione del simbolo case11')
    [void](Invoke-AICarminePre (New-AICarminePrePayload $task11 'invocation-case-11' 'use_mcp_tool' (New-AICarmineMcpInput 'case11')))
    [void](Invoke-AICarminePost (New-AICarminePostPayload $task11 'invocation-case-11' 'use_mcp_tool' $null ([ordered]@{ status = 'failed' }) $false))
    $pre11 = Invoke-AICarminePre (New-AICarminePrePayload $task11 '' 'execute_command' ([ordered]@{ command = 'case11-native' }))
    $preObs11 = Get-AICarmineLatestObservation $task11 pre
    Assert-AICarmineCode $preObs11 'native_after_observed_mcp_failure' $true
    Assert-AICarmine (-not $pre11.Contract.contextModification.ToLowerInvariant().Contains('justified')) 'Case 11 used forbidden fallback wording.'
    Assert-AICarmine (-not $pre11.Contract.contextModification.Contains('repository MCP recommendations')) 'Case 11 emitted generic native warning.'

    # Case 12: native without failure retains generic observation.
    $task12 = 'native-without-failure'
    [void](Invoke-AICarmineUserPrompt $task12 'Cerca la definizione del simbolo case12')
    $pre12 = Invoke-AICarminePre (New-AICarminePrePayload $task12 '' 'execute_command' ([ordered]@{ command = 'case12-native' }))
    $preObs12 = Get-AICarmineLatestObservation $task12 pre
    Assert-AICarmineCode $preObs12 'native_used_while_mcp_recommended' $true
    Assert-AICarmineCode $preObs12 'native_after_observed_mcp_failure' $false
    Assert-AICarmine ($pre12.Contract.contextModification.Contains('repository MCP recommendations')) 'Case 12 generic advisory missing.'

    # Case 13: no sensitive raw values persist.
    $task13 = 'sensitive-post-data'
    $secrets = @('token-H3-SECRET', 'password-H3-SECRET', 'authorization-H3-SECRET', 'result-H3-SECRET', 'error-H3-SECRET', 'invocation-H3-SECRET', 'command-H3-SECRET')
    [void](Invoke-AICarmineUserPrompt $task13 'Cerca la definizione del simbolo case13')
    $sensitiveInput = [ordered]@{ token = $secrets[0]; password = $secrets[1]; authorization = $secrets[2]; command = $secrets[6] }
    [void](Invoke-AICarminePre (New-AICarminePrePayload $task13 $secrets[5] 'execute_command' $sensitiveInput))
    $sensitivePost = New-AICarminePostPayload $task13 $secrets[5] 'execute_command' $null $secrets[3] $false
    $sensitivePost.errorMessage = $secrets[4]
    $sensitiveResult = Invoke-AICarminePost $sensitivePost
    $persisted = [string]::Join([Environment]::NewLine, @(Get-ChildItem -LiteralPath $testRoot -Recurse -File | ForEach-Object {
        [IO.File]::ReadAllText($_.FullName, [Text.Encoding]::UTF8)
    }))
    foreach ($secret in $secrets) {
        Assert-AICarmine (-not $persisted.Contains($secret)) ('Case 13 persisted secret: {0}' -f $secret)
        Assert-AICarmine (-not $sensitiveResult.Stdout.Contains($secret)) ('Case 13 stdout exposed secret: {0}' -f $secret)
        Assert-AICarmine (-not $sensitiveResult.Stderr.Contains($secret)) ('Case 13 stderr exposed secret: {0}' -f $secret)
    }

    # Case 14: invalid JSON is fail-open.
    $invalid = Invoke-AICarmineHook -ScriptPath $postToolPath -RawInput '{invalid'
    Assert-AICarmine ($invalid.Contract.contextModification -eq '') 'Case 14 emitted contextModification.'

    # Case 15: failure overrides contradictory success.
    $task15 = 'contradictory-outcome'
    [void](Invoke-AICarmineUserPrompt $task15 'Cerca la definizione del simbolo case15')
    [void](Invoke-AICarminePre (New-AICarminePrePayload $task15 'invocation-case-15' 'aicarmine_repo_search_rg' ([ordered]@{ query = 'case15' })))
    $contradictory = New-AICarminePostPayload $task15 'invocation-case-15' 'aicarmine_repo_search_rg' $null ([ordered]@{ value = 1 }) $true
    $contradictory.isError = $true
    [void](Invoke-AICarminePost $contradictory)
    $obs15 = Get-AICarmineLatestObservation $task15 post
    Assert-AICarmine ($obs15.outcome -eq 'failure' -and $obs15.failure_signal -eq 'is_error_true') 'Case 15 failure did not override success.'

    # Case 16: duplicate invocation ID is idempotent.
    $task16 = 'duplicate-invocation'
    [void](Invoke-AICarmineUserPrompt $task16 'Cerca la definizione del simbolo case16')
    $payload16 = New-AICarminePrePayload $task16 'invocation-case-16' 'aicarmine_repo_search_rg' ([ordered]@{ query = 'case16' })
    [void](Invoke-AICarminePre $payload16)
    [void](Invoke-AICarminePre $payload16)
    $invocationHash16 = Get-AICarmineTestSha256 'invocation-case-16'
    Assert-AICarmine (@((Get-AICarmineState $task16).pending_tool_calls | Where-Object { $_.invocation_key_sha256 -eq $invocationHash16 }).Count -eq 1) 'Case 16 duplicated pending invocation.'

    # Mutex A: wait about 2 seconds and preserve update.
    $mutexTaskA = 'mutex-wait-2s'
    [void](Invoke-AICarmineUserPrompt $mutexTaskA 'Cerca la definizione del simbolo mutexA')
    $holderA = Start-AICarmineMutexHolder $mutexTaskA 2000 $false
    $watchA = [Diagnostics.Stopwatch]::StartNew()
    [void](Invoke-AICarminePre (New-AICarminePrePayload $mutexTaskA 'mutex-a' 'execute_command' ([ordered]@{ command = 'mutex-a' })))
    $watchA.Stop()
    Complete-AICarmineMutexHolder $holderA
    $mutexObsA = Get-AICarmineLatestObservation $mutexTaskA pre
    Assert-AICarmine ($mutexObsA.state_lock_status -eq 'acquired') 'Mutex A status was not acquired.'
    Assert-AICarmine ($watchA.ElapsedMilliseconds -ge 1500 -and $watchA.ElapsedMilliseconds -lt 5500) 'Mutex A wait was outside bounds.'
    Assert-AICarmine (@((Get-AICarmineState $mutexTaskA).pending_tool_calls).Count -eq 1) 'Mutex A lost update.'

    # Mutex B: wait about 4 seconds and preserve update.
    $mutexTaskB = 'mutex-wait-4s'
    [void](Invoke-AICarmineUserPrompt $mutexTaskB 'Cerca la definizione del simbolo mutexB')
    $holderB = Start-AICarmineMutexHolder $mutexTaskB 4000 $false
    $watchB = [Diagnostics.Stopwatch]::StartNew()
    [void](Invoke-AICarminePre (New-AICarminePrePayload $mutexTaskB 'mutex-b' 'execute_command' ([ordered]@{ command = 'mutex-b' })))
    $watchB.Stop()
    Complete-AICarmineMutexHolder $holderB
    Assert-AICarmine ((Get-AICarmineLatestObservation $mutexTaskB pre).state_lock_status -eq 'acquired') 'Mutex B status was not acquired.'
    Assert-AICarmine ($watchB.ElapsedMilliseconds -ge 3500 -and $watchB.ElapsedMilliseconds -lt 5500) 'Mutex B wait was outside bounds.'
    Assert-AICarmine (@((Get-AICarmineState $mutexTaskB).pending_tool_calls).Count -eq 1) 'Mutex B lost update.'

    # Mutex C: timeout at about 5 seconds and no mutation.
    $mutexTaskC = 'mutex-timeout-5s'
    [void](Invoke-AICarmineUserPrompt $mutexTaskC 'Cerca la definizione del simbolo mutexC')
    $statePathC = Join-Path (Get-AICarmineObserverRootPath) ('routing-{0}.json' -f (Get-AICarmineTestSha256 $mutexTaskC))
    $beforeC = [Convert]::ToBase64String([IO.File]::ReadAllBytes($statePathC))
    $holderC = Start-AICarmineMutexHolder $mutexTaskC 6500 $false
    $watchC = [Diagnostics.Stopwatch]::StartNew()
    $timeoutC = Invoke-AICarminePre (New-AICarminePrePayload $mutexTaskC 'mutex-c' 'execute_command' ([ordered]@{ command = 'mutex-c' }))
    $watchC.Stop()
    Complete-AICarmineMutexHolder $holderC
    $afterC = [Convert]::ToBase64String([IO.File]::ReadAllBytes($statePathC))
    $obsC = Get-AICarmineLatestObservation $mutexTaskC pre
    Assert-AICarmine ($watchC.ElapsedMilliseconds -ge 4700 -and $watchC.ElapsedMilliseconds -lt 6000) 'Mutex C timeout was outside bounds.'
    Assert-AICarmine ($timeoutC.Contract.contextModification -eq '' -and $obsC.state_lock_status -eq 'timeout') 'Mutex C was not fail-open timeout.'
    Assert-AICarmine ($beforeC -eq $afterC) 'Mutex C mutated routing state.'

    # Mutex D: abandoned mutex is recovered.
    $mutexTaskD = 'mutex-abandoned'
    [void](Invoke-AICarmineUserPrompt $mutexTaskD 'Cerca la definizione del simbolo mutexD')
    $holderD = Start-AICarmineMutexHolder $mutexTaskD 1000 $true
    [void](Invoke-AICarminePre (New-AICarminePrePayload $mutexTaskD 'mutex-d' 'execute_command' ([ordered]@{ command = 'mutex-d' })))
    Complete-AICarmineMutexHolder $holderD
    $obsD = Get-AICarmineLatestObservation $mutexTaskD pre
    Assert-AICarmine ($obsD.state_lock_status -eq 'abandoned_acquired') 'Mutex D did not report abandoned_acquired.'
    Assert-AICarmine (@((Get-AICarmineState $mutexTaskD).pending_tool_calls).Count -eq 1) 'Mutex D lost update.'

    # Mutex E: interruption before commit preserves the old destination.
    . $preHelperPath
    $atomicRoot = Get-AICarmineObserverRoot
    $atomicPath = Join-Path $atomicRoot ('atomic-fixture-{0}.json' -f [Guid]::NewGuid().ToString('N'))
    Write-AICarmineObserverJsonAtomic -Root $atomicRoot -Path $atomicPath -Value ([ordered]@{ schema = 'old'; value = 1 })
    $oldAtomic = [Convert]::ToBase64String([IO.File]::ReadAllBytes($atomicPath))
    $script:AICarmineObserverBeforeAtomicCommitTestHook = { throw 'atomic_test_interrupt' }
    $interrupted = $false
    try {
        Write-AICarmineObserverJsonAtomic -Root $atomicRoot -Path $atomicPath -Value ([ordered]@{ schema = 'new'; value = 2 })
    }
    catch { $interrupted = $true }
    finally { $script:AICarmineObserverBeforeAtomicCommitTestHook = $null }
    Assert-AICarmine $interrupted 'Mutex E seam did not interrupt commit.'
    Assert-AICarmine ($oldAtomic -eq [Convert]::ToBase64String([IO.File]::ReadAllBytes($atomicPath))) 'Mutex E changed the old destination.'
    [void]([IO.File]::ReadAllText($atomicPath, [Text.Encoding]::UTF8) | ConvertFrom-Json -ErrorAction Stop)
    Assert-AICarmine (@(Get-ChildItem -LiteralPath $atomicRoot -Filter '.aicarmine-state-*.tmp' -File).Count -eq 0) 'Mutex E left a temp file.'

    # Mutex F: 16 concurrent Pre/Post pairs.
    $mutexTaskF = 'mutex-concurrent-16'
    [void](Invoke-AICarmineUserPrompt $mutexTaskF 'Cerca la definizione del simbolo mutexF')
    $preProcesses = [Collections.Generic.List[object]]::new()
    for ($index = 0; $index -lt 16; $index++) {
        $payload = New-AICarminePrePayload $mutexTaskF ('mutex-f-{0}' -f $index) 'aicarmine_repo_search_rg' ([ordered]@{ query = 'mutex-f-{0}' -f $index })
        [void]$preProcesses.Add((Start-AICarmineHookProcess -ScriptPath $preToolPath -RawInput (ConvertTo-AICarmineJson $payload)))
    }
    foreach ($process in $preProcesses) {
        $completed = Complete-AICarmineHookProcess $process
        Assert-AICarmine ($completed.ExitCode -eq 0 -and [string]::IsNullOrEmpty($completed.Stderr)) 'Mutex F Pre process failed.'
        Assert-AICarmine (-not (ConvertFrom-AICarmineHookOutput $completed.Stdout).cancel) 'Mutex F Pre returned cancel=true.'
    }
    $postProcesses = [Collections.Generic.List[object]]::new()
    for ($index = 0; $index -lt 16; $index++) {
        $payload = New-AICarminePostPayload $mutexTaskF ('mutex-f-{0}' -f $index) 'aicarmine_repo_search_rg' $null ([ordered]@{ status = 'ok'; index = $index }) $true
        [void]$postProcesses.Add((Start-AICarmineHookProcess -ScriptPath $postToolPath -RawInput (ConvertTo-AICarmineJson $payload)))
    }
    foreach ($process in $postProcesses) {
        $completed = Complete-AICarmineHookProcess $process
        Assert-AICarmine ($completed.ExitCode -eq 0 -and [string]::IsNullOrEmpty($completed.Stderr)) 'Mutex F Post process failed.'
        Assert-AICarmine (-not (ConvertFrom-AICarmineHookOutput $completed.Stdout).cancel) 'Mutex F Post returned cancel=true.'
    }
    $stateF = Get-AICarmineState $mutexTaskF
    Assert-AICarmine ($stateF.schema -eq 'aicarmine.cline.task-routing-state.v1') 'Mutex F state schema invalid.'
    Assert-AICarmine (@($stateF.pending_tool_calls).Count -eq 0) 'Mutex F left pending calls.'
    Assert-AICarmine (@($stateF.recent_tool_outcomes).Count -eq 16) 'Mutex F lost or duplicated outcomes.'
    Assert-AICarmine (@($stateF.recent_tool_call_sha256).Count -le 32 -and @($stateF.recent_tool_outcomes).Count -le 32) 'Mutex F exceeded ledger bounds.'
    Assert-AICarmine (@($stateF.recent_tool_outcomes.invocation_key_sha256 | Sort-Object -Unique).Count -eq 16) 'Mutex F duplicated invocation outcomes.'
    $taskKeyF = Get-AICarmineTestSha256 $mutexTaskF
    $lockTimeoutsF = 0
    foreach ($directory in @('observations', 'post-observations')) {
        foreach ($file in @(Get-ChildItem -LiteralPath (Join-Path (Get-AICarmineObserverRootPath) $directory) -Filter '*.json' -File)) {
            $value = [IO.File]::ReadAllText($file.FullName, [Text.Encoding]::UTF8) | ConvertFrom-Json -ErrorAction Stop
            if ($value.task_key_sha256 -eq $taskKeyF -and $value.state_lock_status -eq 'timeout') { $lockTimeoutsF++ }
        }
    }
    Assert-AICarmine ($lockTimeoutsF -eq 0) 'Mutex F had lock timeouts under normal load.'

    Write-Host 'ALL AICARMINE CLINE POSTTOOL OBSERVER TESTS PASSED'
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
        $resolved -match 'aicarmine-cline-posttool-test-') {
        Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction SilentlyContinue
    }
}
