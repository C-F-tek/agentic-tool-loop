# AICarmine Cline MCP router dedicated tests

[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$hooksRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$routerPath = Join-Path $hooksRoot 'lib\aicarmine_cline_mcp_router.ps1'
$wrapperPath = Join-Path $hooksRoot 'UserPromptSubmit.ps1'
$powerShellPath = (Get-Command powershell.exe -ErrorAction Stop).Source

. $routerPath

function Assert-AICarmine {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function ConvertTo-AICarmineRawInput {
    param([string]$Prompt)

    return ([ordered]@{ prompt = $Prompt } | ConvertTo-Json -Compress)
}

function Get-AICarmineSourceHashes {
    param([string[]]$Paths)

    $hashes = [ordered]@{}
    foreach ($path in $Paths) {
        $stream = [System.IO.File]::OpenRead($path)
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        try {
            $hashBytes = $sha256.ComputeHash($stream)
        }
        finally {
            $stream.Dispose()
            $sha256.Dispose()
        }
        $hashes[$path] = (($hashBytes | ForEach-Object { '{0:x2}' -f $_ }) -join '')
    }
    return $hashes
}

function Invoke-AICarmineWrapper {
    param([AllowEmptyString()][string]$RawInput)

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $powerShellPath
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    $startInfo.Arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f $wrapperPath

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    try {
        Assert-AICarmine -Condition $process.Start() -Message 'Wrapper process did not start.'
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

function ConvertFrom-AICarmineWrapperOutput {
    param([string]$Stdout)

    $normalizedOutput = $Stdout.Replace(
        [string][Environment]::NewLine,
        [string][char]10
    ).Replace([string][char]13, [string][char]10)
    $lines = @($normalizedOutput.Split([char]10) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    Assert-AICarmine -Condition ($lines.Count -eq 1) -Message 'Wrapper stdout must contain exactly one non-empty line.'
    return ($lines[0] | ConvertFrom-Json -ErrorAction Stop)
}

try {
    $case1 = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Trova la definizione e i caller di controller_orientation_model_select'
    )
    Assert-AICarmine ($case1.Contains('aicarmine_repo_search_det_health')) 'Case 1 missing search health.'
    Assert-AICarmine (
        $case1.Contains('aicarmine_repo_search_rg') -or $case1.Contains('aicarmine_repo_search_ctags')
    ) 'Case 1 missing rg or ctags.'
    Assert-AICarmine (-not $case1.Contains('aicarmine_repo_code_apply_patch')) 'Case 1 suggested apply_patch.'

    $case2 = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Correggi il file e verifica diffcheck'
    )
    Assert-AICarmine ($case2.Contains('aicarmine_repo_code_health')) 'Case 2 missing repo_code health.'
    Assert-AICarmine ($case2.Contains('aicarmine_repo_code_propose_edit')) 'Case 2 missing propose_edit.'
    Assert-AICarmine ($case2.Contains('aicarmine_repo_code_unidiff_validate')) 'Case 2 missing unidiff_validate.'
    Assert-AICarmine ($case2.Contains('aicarmine_repo_code_git_apply_check')) 'Case 2 missing git_apply_check.'
    Assert-AICarmine ($case2.Contains('Prefer structured_edit')) 'Case 2 does not prefer structured_edit.'
    Assert-AICarmine (-not $case2.Contains('Send the unified diff once')) 'Case 2 contains stale unified_diff guidance.'
    $case2ToolCount = [regex]::Matches($case2, '(?m)^\d+\. aicarmine_').Count
    Assert-AICarmine ($case2ToolCount -le 6) 'Case 2 suggested more than six exact tools.'

    $case2ExistingDiff = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Usa questa unified diff già pronta e validala'
    )
    Assert-AICarmine ($case2ExistingDiff.Contains('already-provided unified_diff')) 'Existing diff case missing unified_diff guidance.'
    Assert-AICarmine ($case2ExistingDiff.Contains('Do not manually calculate unified-diff hunk headers')) 'Existing diff case permits manual hunk generation.'
    Assert-AICarmine ($case2ExistingDiff.Contains('Propagate change_set_id')) 'Existing diff case missing change_set propagation.'
    $case3 = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Audit read-only del selector, non modificare file'
    )
    Assert-AICarmine (-not $case3.Contains('aicarmine_repo_code_apply_patch')) 'Case 3 suggested apply_patch.'
    Assert-AICarmine (
        $case3.Contains('aicarmine_repo_search_') -or $case3.Contains('aicarmine_repo_validate_')
    ) 'Case 3 missing search or validation.'
    Assert-AICarmine (
    $case3.Contains('Read-only: validate and apply-check are allowed') -and
    $case3.Contains('do not call apply_patch or state-write tools')
    ) 'Case 3 missing read-only constraint.'
    $case3b = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Prepara una modifica structured_edit in smoke read-only, valida e fai apply-check, ma non applicare'
    )
    Assert-AICarmine ($case3b.Contains('Prefer structured_edit')) 'Case 3b missing structured_edit guidance.'
    Assert-AICarmine ($case3b.Contains('aicarmine_repo_code_unidiff_validate')) 'Case 3b missing validation tool.'
    Assert-AICarmine ($case3b.Contains('aicarmine_repo_code_git_apply_check')) 'Case 3b missing apply-check tool.'
    Assert-AICarmine (-not $case3b.Contains('aicarmine_repo_code_apply_patch')) 'Case 3b suggested apply_patch.'
    Assert-AICarmine ($case3b.Contains('validate and apply-check are allowed')) 'Case 3b incorrectly treats apply-check as a write.'
    $case4 = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Esegui il reviewed probe orientation.selector.contract.v1'
    )
    Assert-AICarmine ($case4.Contains('aicarmine_repo_validate_probe_profiles')) 'Case 4 missing probe_profiles.'
    Assert-AICarmine ($case4.Contains('aicarmine_repo_validate_probe_run')) 'Case 4 missing probe_run.'
    Assert-AICarmine ($case4.Contains('exact profile_id')) 'Case 4 missing exact profile_id guidance.'
    Assert-AICarmine (-not ($case4 -match '(?i)python\s+inline')) 'Case 4 mentioned Python inline.'

    $case5 = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Esegui il warmup della memoria persistente con exact-key e record_id'
    )
    Assert-AICarmine ($case5.Contains('aicarmine_project_memory_health')) 'Case 5 missing memory health.'
    Assert-AICarmine ($case5.Contains('aicarmine_project_memory_search')) 'Case 5 missing memory search.'
    Assert-AICarmine ($case5.Contains('aicarmine_project_memory_get')) 'Case 5 missing memory get.'
    Assert-AICarmine (-not ($case5 -match 'upsert|supersede|mark_stale')) 'Case 5 suggested a memory write.'

    $memoryCaseA = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Analizza la project memory e verifica il manifest'
    )
    Assert-AICarmine ($memoryCaseA.Contains('aicarmine_project_memory_health')) 'Memory case A missing health.'
    Assert-AICarmine ($memoryCaseA.Contains('aicarmine_project_memory_search')) 'Memory case A missing search.'
    Assert-AICarmine ($memoryCaseA.Contains('aicarmine_project_memory_get')) 'Memory case A missing get.'
    Assert-AICarmine (-not ($memoryCaseA -match 'upsert_verified|supersede|mark_stale')) 'Memory case A suggested a write.'

    $memoryCaseC = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Aggiorna la project memory creando un record verificato'
    )
    Assert-AICarmine ($memoryCaseC.Contains('aicarmine_project_memory_upsert_verified')) 'Memory case C missing upsert_verified.'
    Assert-AICarmine (-not $memoryCaseC.Contains('aicarmine_project_memory_supersede')) 'Memory case C suggested supersede.'
    Assert-AICarmine (-not $memoryCaseC.Contains('aicarmine_project_memory_mark_stale')) 'Memory case C suggested mark_stale.'

    $memoryCaseD = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Supersede il vecchio record della project memory'
    )
    Assert-AICarmine ($memoryCaseD.Contains('aicarmine_project_memory_supersede')) 'Memory case D missing supersede.'
    Assert-AICarmine (-not $memoryCaseD.Contains('aicarmine_project_memory_upsert_verified')) 'Memory case D suggested upsert_verified.'
    Assert-AICarmine (-not $memoryCaseD.Contains('aicarmine_project_memory_mark_stale')) 'Memory case D suggested mark_stale.'

    $memoryCaseE = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Marca stale il record obsoleto nella project memory'
    )
    Assert-AICarmine ($memoryCaseE.Contains('aicarmine_project_memory_mark_stale')) 'Memory case E missing mark_stale.'
    Assert-AICarmine (-not $memoryCaseE.Contains('aicarmine_project_memory_upsert_verified')) 'Memory case E suggested upsert_verified.'
    Assert-AICarmine (-not $memoryCaseE.Contains('aicarmine_project_memory_supersede')) 'Memory case E suggested supersede.'

    $memoryCaseF = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Audit read-only: aggiorna la project memory ma non effettuare scritture'
    )
    Assert-AICarmine (-not ($memoryCaseF -match 'upsert_verified|supersede|mark_stale')) 'Memory case F suggested a write.'
    Assert-AICarmine ($memoryCaseF.Contains('Read-only:')) 'Memory case F missing read-only constraint.'

    $memoryCaseG = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Update del file README'
    )
    Assert-AICarmine (-not ($memoryCaseG -match 'aicarmine_project_memory_(upsert_verified|supersede|mark_stale)')) 'Memory case G suggested a memory write.'

    $case6 = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Spiegami che ore sono'
    )
    Assert-AICarmine ($case6 -eq '') 'Case 6 should produce an empty hint.'

    $invalidThrew = $false
    try {
        $case7 = Get-AICarmineMcpRoutingHint -RawInput '{invalid'
    }
    catch {
        $invalidThrew = $true
        $case7 = 'unexpected'
    }
    Assert-AICarmine (-not $invalidThrew) 'Case 7 threw for invalid JSON.'
    Assert-AICarmine ($case7 -eq '') 'Case 7 should produce an empty hint.'

    $nestedPayload = [ordered]@{
        envelope = [ordered]@{
            request = [ordered]@{
                data = [ordered]@{
                    user_prompt = 'Mostra git log e history del commit'
                }
            }
        }
    } | ConvertTo-Json -Compress -Depth 8
    $case8 = Get-AICarmineMcpRoutingHint -RawInput $nestedPayload
    Assert-AICarmine ($case8.Contains('git_readonly')) 'Case 8 nested prompt was not classified.'
    $tooDeepPayload = [ordered]@{
        one = [ordered]@{
            two = [ordered]@{
                three = [ordered]@{
                    four = [ordered]@{
                        five = [ordered]@{
                            prompt = 'git log'
                        }
                    }
                }
            }
        }
    } | ConvertTo-Json -Compress -Depth 10
    Assert-AICarmine (
        (Get-AICarmineMcpRoutingHint -RawInput $tooDeepPayload) -eq ''
    ) 'Case 8 exceeded the maximum nested depth.'

    $case9Raw = ConvertTo-AICarmineRawInput -Prompt 'Trova la definizione del router'
    $case9Invocation = Invoke-AICarmineWrapper -RawInput $case9Raw
    Assert-AICarmine ($case9Invocation.ExitCode -eq 0) 'Case 9 wrapper exit code was non-zero.'
    Assert-AICarmine ([string]::IsNullOrEmpty($case9Invocation.Stderr)) 'Case 9 wrapper stderr was not empty.'
    $case9Contract = ConvertFrom-AICarmineWrapperOutput -Stdout $case9Invocation.Stdout
    Assert-AICarmine ($case9Contract.cancel -is [bool] -and -not $case9Contract.cancel) 'Case 9 cancel contract failed.'
    Assert-AICarmine ($case9Contract.errorMessage -eq '') 'Case 9 errorMessage contract failed.'
    Assert-AICarmine (
        $case9Contract.contextModification.Contains('aicarmine_repo_search_det_health')
    ) 'Case 9 contextModification lacks the routing hint.'

    $sourcePaths = @($wrapperPath, $routerPath, $PSCommandPath)
    $beforeHashes = Get-AICarmineSourceHashes -Paths $sourcePaths
    $probeDirectory = Join-Path ([System.IO.Path]::GetTempPath()) 'aicarmine-cline-hooks\contract-probe'
    [void][System.IO.Directory]::CreateDirectory($probeDirectory)
    $beforeProbes = @(Get-ChildItem -LiteralPath $probeDirectory -Filter '*.json' -File -ErrorAction SilentlyContinue).FullName

    $case10Raw = ConvertTo-AICarmineRawInput -Prompt 'Spiegami che ore sono'
    $case10Invocation = Invoke-AICarmineWrapper -RawInput $case10Raw
    Assert-AICarmine ($case10Invocation.ExitCode -eq 0) 'Case 10 wrapper exit code was non-zero.'
    Assert-AICarmine ([string]::IsNullOrEmpty($case10Invocation.Stderr)) 'Case 10 wrapper stderr was not empty.'
    $case10Contract = ConvertFrom-AICarmineWrapperOutput -Stdout $case10Invocation.Stdout
    Assert-AICarmine ($case10Contract.contextModification -eq '') 'Case 10 contextModification was not empty.'
    Assert-AICarmine ($case10Contract.cancel -is [bool] -and -not $case10Contract.cancel) 'Case 10 cancel contract failed.'
    Assert-AICarmine ($case10Contract.errorMessage -eq '') 'Case 10 errorMessage contract failed.'

    $afterProbes = @(Get-ChildItem -LiteralPath $probeDirectory -Filter '*.json' -File -ErrorAction SilentlyContinue).FullName
    $newProbes = @($afterProbes | Where-Object { $beforeProbes -notcontains $_ })
    Assert-AICarmine ($newProbes.Count -eq 1) 'Case 10 contract probe did not create exactly one artifact.'

    $afterHashes = Get-AICarmineSourceHashes -Paths $sourcePaths
    foreach ($sourcePath in $sourcePaths) {
        Assert-AICarmine (
            $beforeHashes[$sourcePath] -eq $afterHashes[$sourcePath]
        ) ('Case 10 hook wrote source file: {0}' -f $sourcePath)
    }

    Write-Host 'ALL AICARMINE CLINE MCP ROUTER TESTS PASSED'
    exit 0
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
