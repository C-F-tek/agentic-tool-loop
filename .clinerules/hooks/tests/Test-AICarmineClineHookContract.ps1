# AICarmine Cline Hook Contract Test Harness

[CmdletBinding()]
param(
    [string]$HooksRoot
)

$resolvedScriptRoot = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($resolvedScriptRoot)) {
    $scriptPath = $MyInvocation.MyCommand.Path
    if (-not [string]::IsNullOrWhiteSpace($scriptPath)) {
        $resolvedScriptRoot = Split-Path -Parent $scriptPath
    }
}
if ([string]::IsNullOrWhiteSpace($resolvedScriptRoot)) {
    Write-Error 'Cannot resolve the test harness directory from PSScriptRoot or MyInvocation.MyCommand.Path.'
    exit 1
}

if ([string]::IsNullOrWhiteSpace($HooksRoot)) {
    $HooksRoot = [System.IO.Path]::GetFullPath((Join-Path $resolvedScriptRoot '..'))
}
else {
    $HooksRoot = [System.IO.Path]::GetFullPath($HooksRoot)
}
if (-not (Test-Path -LiteralPath $HooksRoot -PathType Container)) {
    Write-Error ("Hooks root does not exist: {0}" -f $HooksRoot)
    exit 1
}

$powerShellPath = (Get-Command powershell.exe -ErrorAction Stop).Source
if ([string]::IsNullOrWhiteSpace($powerShellPath) -or
    -not (Test-Path -LiteralPath $powerShellPath -PathType Leaf)) {
    Write-Error 'Cannot resolve an absolute powershell.exe path.'
    exit 1
}

$probeDirectory = Join-Path ([System.IO.Path]::GetTempPath()) 'aicarmine-cline-hooks\contract-probe'
[void][System.IO.Directory]::CreateDirectory($probeDirectory)

$fixtures = [ordered]@{
    TaskStart = [ordered]@{
        taskId = 'test-task'
        workspace = 'test-workspace'
    }
    UserPromptSubmit = [ordered]@{
        taskId = 'test-task'
        prompt = 'contract probe fixture'
    }
    PreToolUse = [ordered]@{
        taskId = 'test-task'
        toolName = 'fixture_tool'
        toolInput = [ordered]@{
            query = 'fixture-value'
        }
    }
    PostToolUse = [ordered]@{
        taskId = 'test-task'
        toolName = 'fixture_tool'
        toolResult = [ordered]@{
            ok = $true
        }
    }
    PreCompact = [ordered]@{
        taskId = 'test-task'
        contextSize = 123
    }
}

$forbiddenValues = @{
    TaskStart = @('test-task', 'test-workspace')
    UserPromptSubmit = @('test-task', 'contract probe fixture')
    PreToolUse = @('test-task', 'fixture_tool', 'fixture-value')
    PostToolUse = @('test-task', 'fixture_tool')
    PreCompact = @('test-task')
}

$Results = [System.Collections.Generic.List[object]]::new()
$Passed = [System.Collections.Generic.List[object]]::new()
$Failed = [System.Collections.Generic.List[object]]::new()
$ProbeFiles = [System.Collections.Generic.List[object]]::new()

function Get-ProbeFilePaths {
    return @(
        Get-ChildItem -LiteralPath $probeDirectory -Filter '*.json' -File -ErrorAction SilentlyContinue |
            ForEach-Object { $_.FullName }
    )
}

function Get-BoundedPrefix {
    param(
        [AllowEmptyString()]
        [string]$Text,
        [int]$MaximumLength = 240
    )

    if ([string]::IsNullOrEmpty($Text)) {
        return ''
    }
    $singleLine = (($Text -replace "`r`n", "`n") -replace "`r", "`n") -replace "`n", '\n'
    if ($singleLine.Length -le $MaximumLength) {
        return $singleLine
    }
    return $singleLine.Substring(0, $MaximumLength)
}

function Get-RawSha256 {
    param([AllowEmptyString()][string]$RawInput)

    $utf8 = New-Object System.Text.UTF8Encoding($false)
    $bytes = $utf8.GetBytes($RawInput)
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hashBytes = $sha256.ComputeHash($bytes)
    }
    finally {
        $sha256.Dispose()
    }
    return (($hashBytes | ForEach-Object { '{0:x2}' -f $_ }) -join '')
}

function Add-Failure {
    param(
        [System.Collections.Generic.List[object]]$Target,
        [string]$HookName,
        [string]$HookPath,
        [int]$ExitCode,
        [string]$Stdout,
        [string]$Stderr,
        [string]$ErrorType
    )

    $Target.Add([pscustomobject]@{
        HookName = $HookName
        HookPath = $HookPath
        ExitCode = $ExitCode
        StdoutPrefix = Get-BoundedPrefix -Text $Stdout
        StderrPrefix = Get-BoundedPrefix -Text $Stderr
        ErrorType = $ErrorType
    })
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

function Invoke-HookProcess {
    param(
        [Parameter(Mandatory = $true)][string]$HookPath,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$FixtureJson
    )

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $powerShellPath
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    $startInfo.Arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File {0}' -f (
        ConvertTo-WindowsCommandLineArgument -Value $HookPath
    )

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    try {
        if (-not $process.Start()) {
            throw 'Process.Start() returned false.'
        }
        $process.StandardInput.Write($FixtureJson)
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

function Test-ProbeFile {
    param(
        [Parameter(Mandatory = $true)][string]$ProbePath,
        [Parameter(Mandatory = $true)][string]$HookName,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$FixtureJson,
        [Parameter(Mandatory = $true)][bool]$ExpectedParseOk,
        [string[]]$ForbiddenRawValues = @()
    )

    $errors = [System.Collections.Generic.List[string]]::new()
    try {
        $probeText = [System.IO.File]::ReadAllText($ProbePath, [System.Text.Encoding]::UTF8)
        $probe = $probeText | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        $errors.Add('ProbeJsonInvalid')
        return @($errors.ToArray())
    }

    if ($probe.schema -ne 'aicarmine.hook.contract.v1') { $errors.Add('ProbeSchemaMismatch') }
    if ($probe.hook_name -ne $HookName) { $errors.Add('ProbeHookNameMismatch') }
    if ($probe.parse_ok -isnot [bool] -or $probe.parse_ok -ne $ExpectedParseOk) {
        $errors.Add('ProbeParseOkMismatch')
    }

    $expectedBytes = ([System.Text.Encoding]::UTF8.GetBytes($FixtureJson)).Length
    if ($probe.raw_utf8_bytes -ne $expectedBytes) { $errors.Add('ProbeByteCountMismatch') }
    if ($probe.raw_sha256 -ne (Get-RawSha256 -RawInput $FixtureJson)) {
        $errors.Add('ProbeSha256Mismatch')
    }

    if ($ExpectedParseOk) {
        try {
            $fixtureObject = $FixtureJson | ConvertFrom-Json -ErrorAction Stop
            $expectedKeys = @($fixtureObject.PSObject.Properties.Name | Sort-Object)
            $actualKeys = @($probe.top_level_keys | Sort-Object)
            if ((Compare-Object -ReferenceObject $expectedKeys -DifferenceObject $actualKeys).Count -ne 0) {
                $errors.Add('ProbeTopLevelKeysMismatch')
            }
        }
        catch {
            $errors.Add('FixtureJsonInvalid')
        }
        if ($null -eq $probe.shape -or $probe.shape.type -ne 'object') {
            $errors.Add('ProbeShapeMismatch')
        }
    }
    else {
        if (@($probe.top_level_keys).Count -ne 0) { $errors.Add('InvalidProbeTopLevelKeysPresent') }
        if ($null -ne $probe.shape) { $errors.Add('InvalidProbeShapePresent') }
    }

    if ($probeText.Contains($FixtureJson)) { $errors.Add('RawFixturePersisted') }
    foreach ($rawValue in $ForbiddenRawValues) {
        if (-not [string]::IsNullOrEmpty($rawValue) -and $probeText.Contains($rawValue)) {
            $errors.Add('RawFixtureValuePersisted')
            break
        }
    }

    return @($errors.ToArray())
}

function Invoke-And-ValidateHook {
    param(
        [Parameter(Mandatory = $true)][string]$HookName,
        [Parameter(Mandatory = $true)][string]$HookPath,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$FixtureJson,
        [Parameter(Mandatory = $true)][bool]$ExpectedParseOk,
        [string[]]$ForbiddenRawValues = @()
    )

    $before = @(Get-ProbeFilePaths)
    $invocation = Invoke-HookProcess -HookPath $HookPath -FixtureJson $FixtureJson
    $after = @(Get-ProbeFilePaths)
    $newProbePaths = @($after | Where-Object { $before -notcontains $_ })
    foreach ($newProbePath in $newProbePaths) {
        $ProbeFiles.Add($newProbePath)
    }

    $errorTypes = [System.Collections.Generic.List[string]]::new()
    if ($invocation.ExitCode -ne 0) { $errorTypes.Add('NonZeroExitCode') }
    if (-not [string]::IsNullOrWhiteSpace($invocation.Stderr)) { $errorTypes.Add('StderrNotEmpty') }

    $normalizedStdout = (($invocation.Stdout -replace "`r`n", "`n") -replace "`r", "`n")
    $nonEmptyLines = @($normalizedStdout -split "`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($nonEmptyLines.Count -ne 1) {
        $errorTypes.Add('StdoutLineCountMismatch')
    }
    else {
        try {
            $contract = $nonEmptyLines[0] | ConvertFrom-Json -ErrorAction Stop
            if ($contract.cancel -isnot [bool] -or $contract.cancel -ne $false) {
                $errorTypes.Add('CancelContractMismatch')
            }
            if ($contract.contextModification -ne '') {
                $errorTypes.Add('ContextModificationContractMismatch')
            }
            if ($contract.errorMessage -ne '') {
                $errorTypes.Add('ErrorMessageContractMismatch')
            }
        }
        catch {
            $errorTypes.Add('StdoutJsonInvalid')
        }
    }

    if ($newProbePaths.Count -ne 1) {
        $errorTypes.Add('ProbeFileCountMismatch')
    }
    else {
        $probeErrors = Test-ProbeFile -ProbePath $newProbePaths[0] -HookName $HookName `
            -FixtureJson $FixtureJson -ExpectedParseOk $ExpectedParseOk `
            -ForbiddenRawValues $ForbiddenRawValues
        foreach ($probeError in $probeErrors) {
            $errorTypes.Add($probeError)
        }
    }

    return [pscustomobject]@{
        Passed = ($errorTypes.Count -eq 0)
        ExitCode = $invocation.ExitCode
        Stdout = $invocation.Stdout
        Stderr = $invocation.Stderr
        ErrorType = ($errorTypes -join ',')
    }
}

$events = @('TaskStart', 'UserPromptSubmit', 'PreToolUse', 'PostToolUse', 'PreCompact')
$hookMap = [ordered]@{}

try {
    $rootFiles = @(Get-ChildItem -LiteralPath $HooksRoot -File -ErrorAction Stop)
    foreach ($eventName in $events) {
        $candidatePaths = [System.Collections.Generic.HashSet[string]]::new(
            [System.StringComparer]::OrdinalIgnoreCase
        )

        foreach ($file in $rootFiles) {
            if ($file.BaseName -eq $eventName) {
                if ($file.Extension -ne '.ps1') {
                    throw ("Hook event {0} resolves to a non-PowerShell file: {1}" -f $eventName, $file.FullName)
                }
                [void]$candidatePaths.Add($file.FullName)
                continue
            }

            if ($file.Extension -eq '.ps1') {
                $template = [System.IO.File]::ReadAllText($file.FullName, [System.Text.Encoding]::UTF8)
                $marker = '\[' + [System.Text.RegularExpressions.Regex]::Escape($eventName) + '\]'
                if ($template -match $marker) {
                    [void]$candidatePaths.Add($file.FullName)
                }
            }
        }

        if ($candidatePaths.Count -eq 0) {
            throw ("Missing hook file for event {0}." -f $eventName)
        }
        if ($candidatePaths.Count -ne 1) {
            throw ("Duplicate hook files for event {0}: {1}" -f $eventName, ($candidatePaths -join ', '))
        }
        $hookMap[$eventName] = @($candidatePaths)[0]
    }
}
catch {
    Write-Host ("HOOK DISCOVERY FAILED: {0}" -f $_.Exception.Message)
    exit 1
}

foreach ($eventName in $events) {
    $hookPath = $hookMap[$eventName]
    $fixtureJson = $fixtures[$eventName] | ConvertTo-Json -Compress -Depth 10
    try {
        $validation = Invoke-And-ValidateHook -HookName $eventName -HookPath $hookPath `
            -FixtureJson $fixtureJson -ExpectedParseOk $true `
            -ForbiddenRawValues $forbiddenValues[$eventName]
        $result = [pscustomobject]@{
            HookName = $eventName
            HookPath = $hookPath
            ExitCode = $validation.ExitCode
            Passed = $validation.Passed
        }
        $Results.Add($result)
        if ($validation.Passed) {
            $Passed.Add($result)
        }
        else {
            Add-Failure -Target $Failed -HookName $eventName -HookPath $hookPath `
                -ExitCode $validation.ExitCode -Stdout $validation.Stdout `
                -Stderr $validation.Stderr -ErrorType $validation.ErrorType
        }
    }
    catch {
        $Results.Add([pscustomobject]@{
            HookName = $eventName
            HookPath = $hookPath
            ExitCode = -1
            Passed = $false
        })
        Add-Failure -Target $Failed -HookName $eventName -HookPath $hookPath `
            -ExitCode -1 -Stdout '' -Stderr '' -ErrorType $_.Exception.GetType().FullName
    }
}

$invalidFixture = '{invalid'
$invalidHookPath = $hookMap['TaskStart']
try {
    $invalidValidation = Invoke-And-ValidateHook -HookName 'TaskStart' -HookPath $invalidHookPath `
        -FixtureJson $invalidFixture -ExpectedParseOk $false -ForbiddenRawValues @($invalidFixture)
    if (-not $invalidValidation.Passed) {
        Add-Failure -Target $Failed -HookName 'TaskStart.InvalidJson' -HookPath $invalidHookPath `
            -ExitCode $invalidValidation.ExitCode -Stdout $invalidValidation.Stdout `
            -Stderr $invalidValidation.Stderr -ErrorType $invalidValidation.ErrorType
    }
}
catch {
    Add-Failure -Target $Failed -HookName 'TaskStart.InvalidJson' -HookPath $invalidHookPath `
        -ExitCode -1 -Stdout '' -Stderr '' -ErrorType $_.Exception.GetType().FullName
}

Write-Host ("Total hooks tested: {0}" -f $Results.Count)
Write-Host ("Passed: {0}" -f $Passed.Count)
Write-Host ("Failed: {0}" -f $Failed.Count)
Write-Host ("Probe files created: {0}" -f $ProbeFiles.Count)

if ($Failed.Count -gt 0) {
    foreach ($failure in $Failed) {
        Write-Host (
            "FAIL {0}: type={1}; path={2}; exit={3}; stdout_prefix={4}; stderr_prefix={5}" -f `
                $failure.HookName,
                $failure.ErrorType,
                $failure.HookPath,
                $failure.ExitCode,
                $failure.StdoutPrefix,
                $failure.StderrPrefix
        )
    }
    exit 1
}

Write-Host 'ALL AICARMINE CLINE HOOK CONTRACT TESTS PASSED'
exit 0
