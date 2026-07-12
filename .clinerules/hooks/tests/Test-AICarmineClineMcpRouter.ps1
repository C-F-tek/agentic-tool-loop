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

function Get-AICarmineHintClasses {
    param([string]$Hint)

    $classes = [System.Collections.Generic.List[string]]::new()
    $inSection = $false
    foreach ($line in @($Hint -split '\r?\n')) {
        if ($line -eq 'Task classes:') {
            $inSection = $true
            continue
        }
        if ($line -eq 'Preferred sequence:') {
            break
        }
        if ($inSection -and $line -match '^- (.+)$') {
            [void]$classes.Add($Matches[1])
        }
    }
    return @($classes)
}

function Get-AICarmineHintTools {
    param([string]$Hint)

    $tools = [System.Collections.Generic.List[string]]::new()
    foreach ($match in [regex]::Matches($Hint, '(?m)^\d+\. (aicarmine_[^\r\n]+)\r?$')) {
        [void]$tools.Add($match.Groups[1].Value)
    }
    return @($tools)
}

function Get-AICarmineTextSha256 {
    param([string]$Text)

    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
        return (($sha256.ComputeHash($bytes) | ForEach-Object { '{0:x2}' -f $_ }) -join '')
    }
    finally {
        $sha256.Dispose()
    }
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
    Assert-AICarmine ($case3 -eq '') 'Case 3 inferred routing or policy from natural-language prohibitions.'

    $case3b = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Prepara una modifica structured_edit in smoke read-only, valida e fai apply-check, ma non applicare'
    )
    Assert-AICarmine ($case3b.Contains('Prefer structured_edit')) 'Case 3b missing structured_edit guidance.'
    Assert-AICarmine ($case3b.Contains('aicarmine_repo_code_unidiff_validate')) 'Case 3b missing validation tool.'
    Assert-AICarmine ($case3b.Contains('aicarmine_repo_code_git_apply_check')) 'Case 3b missing apply-check tool.'
    Assert-AICarmine ($case3b.Contains('aicarmine_repo_code_apply_patch')) 'Case 3b suppressed a routing tool from natural-language policy.'
    Assert-AICarmine (-not $case3b.Contains('Read-only:')) 'Case 3b inferred read_only from natural language.'
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
    Assert-AICarmine ($memoryCaseF.Contains('aicarmine_project_memory_upsert_verified')) 'Memory case F lost positive memory routing.'
    Assert-AICarmine (-not ($memoryCaseF -match 'Read-only:|no_memory_write:|explicit_memory_write:')) 'Memory case F inferred linguistic policy.'

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


    $case11 = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Non applicare patch e non modificare file. Esegui soltanto il reviewed probe orientation.selector.contract.v1.'
    )
    $case11Classes = @(Get-AICarmineHintClasses -Hint $case11)
    Assert-AICarmine ($case11Classes[0] -eq 'repository_validation') 'Case 11 primary class is not repository_validation.'
    Assert-AICarmine ($case11.Contains('aicarmine_repo_validate_probe_profiles')) 'Case 11 missing probe_profiles.'
    Assert-AICarmine ($case11.Contains('aicarmine_repo_validate_probe_run')) 'Case 11 missing probe_run.'
    Assert-AICarmine (-not ($case11Classes -contains 'repository_patch')) 'Case 11 classified the negated patch positively.'
    Assert-AICarmine (-not $case11.Contains('aicarmine_repo_code_apply_patch')) 'Case 11 suggested apply_patch.'
    Assert-AICarmine (-not $case11.Contains('Read-only:')) 'Case 11 inferred read_only from natural language.'

    $case12 = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Verifica il reviewed probe. Non scrivere nella project memory.'
    )
    $case12Classes = @(Get-AICarmineHintClasses -Hint $case12)
    Assert-AICarmine ($case12Classes[0] -eq 'repository_validation') 'Case 12 primary class is not repository_validation.'
    Assert-AICarmine (-not ($case12Classes -contains 'project_memory')) 'Case 12 classified incidental memory.'
    Assert-AICarmine (-not ($case12 -match 'upsert_verified|supersede|mark_stale')) 'Case 12 suggested a memory write.'
    Assert-AICarmine (-not $case12.Contains('no_memory_write')) 'Case 12 invented no_memory_write.'

    $case13 = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Audit read-only della project memory e verifica il manifest.'
    )
    $case13Classes = @(Get-AICarmineHintClasses -Hint $case13)
    Assert-AICarmine ($case13Classes -contains 'project_memory') 'Case 13 missing project_memory.'
    Assert-AICarmine ($case13.Contains('aicarmine_project_memory_health')) 'Case 13 missing memory health.'
    Assert-AICarmine ($case13.Contains('aicarmine_project_memory_search')) 'Case 13 missing memory search.'
    Assert-AICarmine ($case13.Contains('aicarmine_project_memory_get')) 'Case 13 missing memory get.'
    Assert-AICarmine (-not ($case13 -match 'upsert_verified|supersede|mark_stale')) 'Case 13 suggested a memory write.'
    Assert-AICarmine (-not $case13.Contains('Read-only:')) 'Case 13 inferred read_only from natural language.'

    $case14 = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Correggi il router con una structured_edit e applica la patch.'
    )
    $case14Classes = @(Get-AICarmineHintClasses -Hint $case14)
    Assert-AICarmine ($case14Classes[0] -eq 'repository_patch') 'Case 14 primary class is not repository_patch.'
    foreach ($tool in @(
        'aicarmine_repo_code_propose_edit',
        'aicarmine_repo_code_unidiff_validate',
        'aicarmine_repo_code_git_apply_check',
        'aicarmine_repo_code_apply_patch'
    )) {
        Assert-AICarmine ($case14.Contains($tool)) ('Case 14 missing {0}.' -f $tool)
    }
    Assert-AICarmine ($case14.Contains('Prefer structured_edit')) 'Case 14 missing structured_edit guidance.'

    $case15 = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Non applicare la patch; valida soltanto la unified diff esistente.'
    )
    $case15Classes = @(Get-AICarmineHintClasses -Hint $case15)
    Assert-AICarmine ($case15Classes[0] -eq 'repository_validation') 'Case 15 primary class is not repository_validation.'
    Assert-AICarmine (-not $case15.Contains('aicarmine_repo_code_apply_patch')) 'Case 15 suggested apply_patch.'
    Assert-AICarmine ($case15.Contains('already-provided unified_diff')) 'Case 15 missing existing diff guidance.'
    Assert-AICarmine ($case15.Contains('aicarmine_repo_code_unidiff_validate')) 'Case 15 missing unidiff_validate.'
    Assert-AICarmine ($case15.Contains('aicarmine_repo_code_git_apply_check')) 'Case 15 missing git_apply_check.'

    $case16 = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Verifica repo root, branch, HEAD, working tree e staged state.'
    )
    $case16Classes = @(Get-AICarmineHintClasses -Hint $case16)
    Assert-AICarmine ($case16Classes -contains 'repository_state') 'Case 16 missing repository_state.'
    Assert-AICarmine ($case16.Contains('aicarmine_repo_state_health')) 'Case 16 missing repo_state health.'
    Assert-AICarmine (-not ($case16 -match 'aicarmine_repo_code_|aicarmine_project_memory_')) 'Case 16 suggested patch or memory tools.'

    $case17 = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Confronta i commit e trova la regressione con git show e blame.'
    )
    $case17Classes = @(Get-AICarmineHintClasses -Hint $case17)
    Assert-AICarmine ($case17Classes -contains 'git_readonly') 'Case 17 missing git_readonly.'
    Assert-AICarmine ($case17.Contains('aicarmine_git_readonly_show')) 'Case 17 missing git show tool.'
    Assert-AICarmine ($case17.Contains('aicarmine_git_readonly_blame')) 'Case 17 missing blame tool.'
    Assert-AICarmine (-not ($case17Classes -contains 'repository_patch')) 'Case 17 classified repository_patch.'

    $case18 = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'La documentazione cita patch e project memory, ma spiegami soltanto il contratto del reviewed probe.'
    )
    $case18Classes = @(Get-AICarmineHintClasses -Hint $case18)
    Assert-AICarmine ($case18Classes[0] -eq 'repository_validation') 'Case 18 primary class is not repository_validation.'
    Assert-AICarmine (-not ($case18Classes -contains 'repository_patch')) 'Case 18 classified contextual patch.'
    Assert-AICarmine (-not ($case18Classes -contains 'project_memory')) 'Case 18 classified contextual memory.'

    $case19 = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Audit read-only: aggiorna la project memory ma non effettuare alcuna scrittura.'
    )
    Assert-AICarmine ($case19.Contains('aicarmine_project_memory_upsert_verified')) 'Case 19 lost positive memory routing.'
    Assert-AICarmine (-not ($case19 -match 'Read-only:|no_memory_write:|explicit_memory_write:')) 'Case 19 inferred linguistic policy.'

    $case20 = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Usa aicarmine_repo_validate_probe_run con il profile_id già verificato.'
    )
    $case20Classes = @(Get-AICarmineHintClasses -Hint $case20)
    $case20Tools = @(Get-AICarmineHintTools -Hint $case20)
    Assert-AICarmine ($case20Classes[0] -eq 'repository_validation') 'Case 20 primary class is not repository_validation.'
    Assert-AICarmine ($case20Tools[0] -eq 'aicarmine_repo_validate_probe_profiles') 'Case 20 did not start with probe_profiles.'
    Assert-AICarmine ($case20Tools[1] -eq 'aicarmine_repo_validate_probe_run') 'Case 20 did not place probe_run second.'

    $case21 = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Raccontami una barzelletta.'
    )
    Assert-AICarmine ($case21 -eq '') 'Case 21 should produce an empty hint.'

    $case22Prompt = 'Esegui il reviewed probe orientation.selector.contract.v1'
    $case22TaskId = 'aicarmine-router-state-' + [Guid]::NewGuid().ToString('N')
    $case22Raw = [ordered]@{ taskId = $case22TaskId; prompt = $case22Prompt } | ConvertTo-Json -Compress
    $case22SourceHashes = Get-AICarmineSourceHashes -Paths $sourcePaths
    $case22Invocation = Invoke-AICarmineWrapper -RawInput $case22Raw
    Assert-AICarmine ($case22Invocation.ExitCode -eq 0) 'Case 22 wrapper exit code was non-zero.'
    Assert-AICarmine ([string]::IsNullOrEmpty($case22Invocation.Stderr)) 'Case 22 wrapper stderr was not empty.'
    $case22Contract = ConvertFrom-AICarmineWrapperOutput -Stdout $case22Invocation.Stdout
    $case22Classes = @(Get-AICarmineHintClasses -Hint $case22Contract.contextModification)
    $case22TaskKey = Get-AICarmineTextSha256 -Text $case22TaskId
    $case22StatePath = Join-Path ([IO.Path]::GetTempPath()) ('aicarmine-cline-hooks\pretool-observer\routing-{0}.json' -f $case22TaskKey)
    Assert-AICarmine (Test-Path -LiteralPath $case22StatePath -PathType Leaf) 'Case 22 routing state was not written.'
    $case22StateText = [IO.File]::ReadAllText($case22StatePath, [Text.Encoding]::UTF8)
    $case22State = $case22StateText | ConvertFrom-Json -ErrorAction Stop
    Assert-AICarmine ([bool]$case22State.classified) 'Case 22 state is not classified.'
    Assert-AICarmine (@($case22State.classes).Count -gt 0) 'Case 22 state classes are empty.'
    Assert-AICarmine ($case22State.classes[0] -eq $case22Classes[0]) 'Case 22 primary class is not preserved in state.'
    Assert-AICarmine ($case22State.preferred_tools[0] -eq 'aicarmine_repo_validate_probe_profiles') 'Case 22 preferred tools are inconsistent.'
    Assert-AICarmine (-not [bool]$case22State.read_only) 'Case 22 read_only is incorrect.'
    Assert-AICarmine (-not $case22StateText.Contains($case22Prompt)) 'Case 22 persisted the raw prompt.'
    $case22AfterHashes = Get-AICarmineSourceHashes -Paths $sourcePaths
    foreach ($sourcePath in $sourcePaths) {
        Assert-AICarmine ($case22SourceHashes[$sourcePath] -eq $case22AfterHashes[$sourcePath]) ('Case 22 hook wrote source file: {0}' -f $sourcePath)
    }
    Remove-Item -LiteralPath $case22StatePath -Force -ErrorAction SilentlyContinue


    $negativeOnly = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Non scrivere nella project memory.'
    )
    Assert-AICarmine ($negativeOnly -eq '') 'Policy case 1 produced a constraint-only hint.'

    $negativeMemoryProbe = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Esegui il reviewed probe. Non scrivere nella project memory.'
    )
    $negativeMemoryClasses = @(Get-AICarmineHintClasses -Hint $negativeMemoryProbe)
    Assert-AICarmine ($negativeMemoryClasses[0] -eq 'repository_validation') 'Policy case 2 primary class was not validation.'
    Assert-AICarmine ($negativeMemoryProbe.Contains('aicarmine_repo_validate_probe_profiles')) 'Policy case 2 missing probe_profiles.'
    Assert-AICarmine ($negativeMemoryProbe.Contains('aicarmine_repo_validate_probe_run')) 'Policy case 2 missing probe_run.'
    Assert-AICarmine (-not ($negativeMemoryClasses -contains 'project_memory')) 'Policy case 2 activated project_memory.'
    Assert-AICarmine (-not $negativeMemoryProbe.Contains('no_memory_write')) 'Policy case 2 invented no_memory_write.'

    $negativeSourceProbe = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Esegui il reviewed probe. Non modificare README.'
    )
    $negativeSourceClasses = @(Get-AICarmineHintClasses -Hint $negativeSourceProbe)
    Assert-AICarmine ($negativeSourceClasses[0] -eq 'repository_validation') 'Policy case 3 primary class was not validation.'
    Assert-AICarmine (-not $negativeSourceProbe.Contains('no_source_write')) 'Policy case 3 invented no_source_write.'
    Assert-AICarmine (-not ($negativeSourceProbe -match 'aicarmine_repo_code_(health|propose_edit|apply_patch)')) 'Policy case 3 added source tools.'

    $structuredReadOnlyPrompt = 'Esegui il reviewed probe orientation.selector.contract.v1.' +
        [Environment]::NewLine + 'MODE: READ_ONLY'
    $structuredReadOnly = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt $structuredReadOnlyPrompt
    )
    Assert-AICarmine ($structuredReadOnly.Contains('Read-only:')) 'Policy case 4 did not preserve structured read_only.'
    Assert-AICarmine (-not ($structuredReadOnly -match 'no_source_write|no_memory_write|no_commit|no_push')) 'Policy case 4 emitted linguistic constraints.'

    $strictReadOnlyPrompt = 'Esegui il reviewed probe orientation.selector.contract.v1.' +
        [Environment]::NewLine + 'strictly read-only'
    $strictReadOnly = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt $strictReadOnlyPrompt
    )
    Assert-AICarmine ($strictReadOnly.Contains('Read-only:')) 'Policy case 4b did not recognize STRICTLY READ-ONLY.'

    $naturalReadOnly = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Esegui il reviewed probe. Audit read-only, non modificare file.'
    )
    Assert-AICarmine (-not $naturalReadOnly.Contains('Read-only:')) 'Policy case 5 inferred read_only from natural language.'
    Assert-AICarmine (-not ($naturalReadOnly -match 'no_source_write|no_memory_write|no_commit|no_push')) 'Policy case 5 persisted linguistic policy.'

    $positivePatch = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Correggi il router e applica la patch.'
    )
    $positivePatchClasses = @(Get-AICarmineHintClasses -Hint $positivePatch)
    Assert-AICarmine ($positivePatchClasses[0] -eq 'repository_patch') 'Policy case 6 lost repository_patch.'
    foreach ($tool in @('aicarmine_repo_code_propose_edit', 'aicarmine_repo_code_unidiff_validate', 'aicarmine_repo_code_git_apply_check', 'aicarmine_repo_code_apply_patch')) {
        Assert-AICarmine ($positivePatch.Contains($tool)) ('Policy case 6 missing {0}.' -f $tool)
    }

    $positiveMemory = Get-AICarmineMcpRoutingHint -RawInput (
        ConvertTo-AICarmineRawInput -Prompt 'Aggiorna la project memory creando un record verificato.'
    )
    $positiveMemoryClasses = @(Get-AICarmineHintClasses -Hint $positiveMemory)
    Assert-AICarmine ($positiveMemoryClasses -contains 'project_memory') 'Policy case 7 lost project_memory.'
    Assert-AICarmine ($positiveMemory.Contains('aicarmine_project_memory_upsert_verified')) 'Policy case 7 missing upsert routing.'
    Assert-AICarmine (-not $positiveMemory.Contains('explicit_memory_write')) 'Policy case 7 emitted explicit_memory_write policy.'

    Write-Host 'ALL AICARMINE CLINE MCP ROUTER TESTS PASSED'
    exit 0
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
