# AICarmine Cline PreToolUse observer dedicated tests

[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$hooksRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$userPromptPath = Join-Path $hooksRoot 'UserPromptSubmit.ps1'
$preToolPath = Join-Path $hooksRoot 'PreToolUse.ps1'
$contractTestPath = Join-Path $PSScriptRoot 'Test-AICarmineClineHookContract.ps1'
$powerShellPath = (Get-Command powershell.exe -ErrorAction Stop).Source
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('aicarmine-cline-pretool-test-' + [Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($testRoot)

function Assert-AICarmine {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) {
        throw $Message
    }
}

function Invoke-AICarmineProcess {
    param(
        [string]$ScriptPath,
        [AllowEmptyString()][string]$RawInput
    )

    $startInfo = New-Object Diagnostics.ProcessStartInfo
    $startInfo.FileName = $powerShellPath
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    $startInfo.Arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f $ScriptPath
    $startInfo.EnvironmentVariables['TEMP'] = $testRoot
    $startInfo.EnvironmentVariables['TMP'] = $testRoot

    $process = New-Object Diagnostics.Process
    $process.StartInfo = $startInfo
    try {
        Assert-AICarmine $process.Start() 'Process did not start.'
        $process.StandardInput.Write($RawInput)
        $process.StandardInput.Close()
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            Stdout = $stdout
            Stderr = $stderr
        }
    }
    finally {
        $process.Dispose()
    }
}

function ConvertFrom-AICarmineHookOutput {
    param([string]$Stdout)

    $lines = @($Stdout.Replace([string][char]13, '').Split([char]10) |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    Assert-AICarmine ($lines.Count -eq 1) 'Hook stdout must contain one non-empty line.'
    return $lines[0] | ConvertFrom-Json -ErrorAction Stop
}

function New-AICarminePayload {
    param(
        [string]$TaskId,
        [string]$ToolName,
        $ToolInput
    )

    return [ordered]@{
        taskId = $TaskId
        toolName = $ToolName
        toolInput = $ToolInput
    } | ConvertTo-Json -Compress -Depth 10
}

function Invoke-AICarmineUserPrompt {
    param([string]$TaskId, [string]$Prompt)

    $raw = [ordered]@{ taskId = $TaskId; prompt = $Prompt } | ConvertTo-Json -Compress
    $result = Invoke-AICarmineProcess -ScriptPath $userPromptPath -RawInput $raw
    Assert-AICarmine ($result.ExitCode -eq 0) 'UserPromptSubmit exit code was non-zero.'
    Assert-AICarmine ([string]::IsNullOrEmpty($result.Stderr)) 'UserPromptSubmit stderr was not empty.'
    $contract = ConvertFrom-AICarmineHookOutput -Stdout $result.Stdout
    Assert-AICarmine (-not $contract.cancel) 'UserPromptSubmit returned cancel=true.'
}

function Invoke-AICarminePreTool {
    param([string]$RawInput)

    $result = Invoke-AICarmineProcess -ScriptPath $preToolPath -RawInput $RawInput
    Assert-AICarmine ($result.ExitCode -eq 0) 'PreToolUse exit code was non-zero.'
    Assert-AICarmine ([string]::IsNullOrEmpty($result.Stderr)) 'PreToolUse stderr was not empty.'
    $contract = ConvertFrom-AICarmineHookOutput -Stdout $result.Stdout
    Assert-AICarmine (-not $contract.cancel) 'PreToolUse returned cancel=true.'
    Assert-AICarmine ($contract.errorMessage -eq '') 'PreToolUse returned an errorMessage.'
    return $contract
}

function Get-AICarmineLatestObservation {
    $directory = Join-Path $testRoot 'aicarmine-cline-hooks\pretool-observer\observations'
    $file = Get-ChildItem -LiteralPath $directory -Filter 'observation-*.json' -File |
        Sort-Object Name -Descending | Select-Object -First 1
    Assert-AICarmine ($null -ne $file) 'Observation file was not created.'
    return Get-Content -LiteralPath $file.FullName -Encoding UTF8 -Raw | ConvertFrom-Json
}

function Assert-AICarmineCode {
    param($Observation, [string]$Code, [bool]$Expected)
    $present = @($Observation.advisory_codes) -contains $Code
    Assert-AICarmine ($present -eq $Expected) ('Unexpected advisory code state: {0}' -f $Code)
}

try {
    $case1 = Invoke-AICarminePreTool -RawInput (New-AICarminePayload -TaskId 'missing-state' -ToolName 'fixture_tool' -ToolInput ([ordered]@{}))
    Assert-AICarmine ($case1.contextModification -eq '') 'Case 1 emitted contextModification.'
    $observation = Get-AICarmineLatestObservation
    Assert-AICarmineCode $observation 'routing_state_missing' $true

    $searchTask = 'search-task'
    Invoke-AICarmineUserPrompt $searchTask 'Cerca la definizione e i caller del simbolo controller_orientation_model_select'
    $rawCommand = 'Get-ChildItem C:\private-native-command-marker'
    $case2 = Invoke-AICarminePreTool -RawInput (New-AICarminePayload -TaskId $searchTask -ToolName 'execute_command' -ToolInput ([ordered]@{ command = $rawCommand }))
    Assert-AICarmine ($case2.contextModification.Contains('native tool was selected')) 'Case 2 missing native advisory.'
    $observation = Get-AICarmineLatestObservation
    Assert-AICarmineCode $observation 'native_used_while_mcp_recommended' $true

    $case3Input = [ordered]@{
        server_name = 'aicarmine_repo_search_det'
        tool_name = 'aicarmine_repo_search_rg'
        arguments = [ordered]@{ query = 'controller_orientation_model_select' }
    }
    $case3 = Invoke-AICarminePreTool -RawInput (New-AICarminePayload -TaskId $searchTask -ToolName 'use_mcp_tool' -ToolInput $case3Input)
    Assert-AICarmine ($case3.contextModification -eq '') 'Case 3 emitted contextModification.'
    $observation = Get-AICarmineLatestObservation
    Assert-AICarmineCode $observation 'recommended_mcp_selected' $true
    Assert-AICarmine ([bool]$observation.preferred_tool_match) 'Case 3 preferred_tool_match was false.'

    $readOnlyPatchTask = 'readonly-patch-task'
    Invoke-AICarmineUserPrompt $readOnlyPatchTask 'Audit read-only della patch; non modificare file'
    $applyInput = [ordered]@{
        server_name = 'aicarmine_repo_code'
        tool_name = 'aicarmine_repo_code_apply_patch'
        arguments = [ordered]@{ change_set_id = 'fixture'; allow_source_write = $true }
    }
    $case4 = Invoke-AICarminePreTool -RawInput (New-AICarminePayload -TaskId $readOnlyPatchTask -ToolName 'use_mcp_tool' -ToolInput $applyInput)
    Assert-AICarmine ($case4.contextModification.Contains('write-capable tool')) 'Case 4 missing write advisory.'
    Assert-AICarmine ($case4.contextModification.Length -le 900) 'Case 4 advisory exceeded bound.'
    $observation = Get-AICarmineLatestObservation
    Assert-AICarmineCode $observation 'read_only_write_tool_candidate' $true

    $readOnlyMemoryTask = 'readonly-memory-task'
    Invoke-AICarmineUserPrompt $readOnlyMemoryTask 'Audit read-only della project memory; non effettuare scritture'
    $memoryInput = [ordered]@{
        server_name = 'aicarmine_project_memory'
        tool_name = 'aicarmine_project_memory_upsert_verified'
        arguments = [ordered]@{ key = 'must-not-write' }
    }
    $case5 = Invoke-AICarminePreTool -RawInput (New-AICarminePayload -TaskId $readOnlyMemoryTask -ToolName 'use_mcp_tool' -ToolInput $memoryInput)
    Assert-AICarmine ($case5.contextModification.Contains('write-capable tool')) 'Case 5 missing write advisory.'
    $observation = Get-AICarmineLatestObservation
    Assert-AICarmineCode $observation 'read_only_write_tool_candidate' $true

    $applyTask = 'allowed-apply-task'
    Invoke-AICarmineUserPrompt $applyTask 'Applica la patch autorizzata usando il change_set_id già validato'
    $case6 = Invoke-AICarminePreTool -RawInput (New-AICarminePayload -TaskId $applyTask -ToolName 'use_mcp_tool' -ToolInput $applyInput)
    $observation = Get-AICarmineLatestObservation
    Assert-AICarmineCode $observation 'read_only_write_tool_candidate' $false

    $repeatTask = 'repeat-task'
    Invoke-AICarmineUserPrompt $repeatTask 'Cerca la definizione del simbolo router'
    $repeatPayload = New-AICarminePayload -TaskId $repeatTask -ToolName 'execute_command' -ToolInput ([ordered]@{ command = 'bounded-repeat-marker' })
    [void](Invoke-AICarminePreTool -RawInput $repeatPayload)
    $firstObservation = Get-AICarmineLatestObservation
    Assert-AICarmineCode $firstObservation 'identical_tool_call_repeated' $false
    $case7 = Invoke-AICarminePreTool -RawInput $repeatPayload
    Assert-AICarmine ($case7.contextModification.Contains('identical tool call')) 'Case 7 missing repeated advisory.'
    $secondObservation = Get-AICarmineLatestObservation
    Assert-AICarmineCode $secondObservation 'identical_tool_call_repeated' $true

    $differentTask = 'different-task'
    Invoke-AICarmineUserPrompt $differentTask 'Cerca la definizione del simbolo observer'
    [void](Invoke-AICarminePreTool -RawInput (New-AICarminePayload -TaskId $differentTask -ToolName 'execute_command' -ToolInput ([ordered]@{ command = 'first-call' })))
    $firstDifferent = Get-AICarmineLatestObservation
    [void](Invoke-AICarminePreTool -RawInput (New-AICarminePayload -TaskId $differentTask -ToolName 'execute_command' -ToolInput ([ordered]@{ command = 'second-call' })))
    $secondDifferent = Get-AICarmineLatestObservation
    Assert-AICarmineCode $firstDifferent 'identical_tool_call_repeated' $false
    Assert-AICarmineCode $secondDifferent 'identical_tool_call_repeated' $false

    $case9Result = Invoke-AICarmineProcess -ScriptPath $preToolPath -RawInput '{invalid'
    Assert-AICarmine ($case9Result.ExitCode -eq 0) 'Case 9 exit code was non-zero.'
    Assert-AICarmine ([string]::IsNullOrEmpty($case9Result.Stderr)) 'Case 9 stderr was not empty.'
    $case9 = ConvertFrom-AICarmineHookOutput -Stdout $case9Result.Stdout
    Assert-AICarmine (-not $case9.cancel) 'Case 9 returned cancel=true.'
    Assert-AICarmine ($case9.contextModification -eq '') 'Case 9 emitted contextModification.'
    Assert-AICarmine ($case9.errorMessage -eq '') 'Case 9 returned errorMessage.'

    $sensitiveTask = 'sensitive-task'
    Invoke-AICarmineUserPrompt $sensitiveTask 'Cerca la definizione del simbolo sensitive'
    $secretValues = @('token-value-SECRET', 'password-value-SECRET', 'authorization-value-SECRET', 'command-value-SECRET')
    $sensitiveInput = [ordered]@{
        token = $secretValues[0]
        password = $secretValues[1]
        authorization = $secretValues[2]
        command = $secretValues[3]
    }
    [void](Invoke-AICarminePreTool -RawInput (New-AICarminePayload -TaskId $sensitiveTask -ToolName 'execute_command' -ToolInput $sensitiveInput))
    $observation = Get-AICarmineLatestObservation
    Assert-AICarmine (@($observation.tool_input_key_names) -contains '[redacted]') 'Case 10 did not redact sensitive key names.'
    $observerRoot = Join-Path $testRoot 'aicarmine-cline-hooks\pretool-observer'
    $persisted = [string]::Join([Environment]::NewLine, @(Get-ChildItem -LiteralPath $observerRoot -File -Recurse | ForEach-Object {
        Get-Content -LiteralPath $_.FullName -Encoding UTF8 -Raw
    }))
    foreach ($secret in $secretValues) {
        Assert-AICarmine (-not $persisted.Contains($secret)) 'Case 10 persisted a sensitive raw value.'
    }
    Assert-AICarmine (-not $persisted.Contains($rawCommand)) 'Case 2 persisted a raw command.'

    $contract = Invoke-AICarmineProcess -ScriptPath $contractTestPath -RawInput ''
    Assert-AICarmine ($contract.ExitCode -eq 0) 'Case 11 contract test failed.'
    Assert-AICarmine ([string]::IsNullOrEmpty($contract.Stderr)) 'Case 11 contract stderr was not empty.'
    Assert-AICarmine ($contract.Stdout.Contains('Total hooks tested: 5')) 'Case 11 hook count mismatch.'
    Assert-AICarmine ($contract.Stdout.Contains('Passed: 5')) 'Case 11 pass count mismatch.'
    Assert-AICarmine ($contract.Stdout.Contains('Failed: 0')) 'Case 11 failure count mismatch.'
    Assert-AICarmine ($contract.Stdout.Contains('ALL AICARMINE CLINE HOOK CONTRACT TESTS PASSED')) 'Case 11 success marker missing.'

    Write-Host 'ALL AICARMINE CLINE PRETOOL OBSERVER TESTS PASSED'
    exit 0
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
finally {
    $tempParent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    $resolved = [IO.Path]::GetFullPath($testRoot)
    if ($resolved.StartsWith($tempParent, [StringComparison]::OrdinalIgnoreCase) -and
        $resolved -match 'aicarmine-cline-pretool-test-') {
        Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction SilentlyContinue
    }
}
