# AICarmine deterministic MCP routing helper

function Get-AICarmineMcpRoutingHint {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$RawInput
    )

    Set-StrictMode -Version 2.0

    $parsedInput = $null
    $promptText = $null
    $normalized = $null
    try {
        if ([string]::IsNullOrWhiteSpace($RawInput)) {
            return ''
        }

        function Add-AICarminePromptFragments {
            param(
                $Value,
                [int]$Depth,
                [ref]$Remaining,
                [ref]$Visited,
                [System.Collections.Generic.List[string]]$Fragments
            )

            if ($Depth -gt 4 -or $Remaining.Value -le 0 -or $Visited.Value -ge 256) {
                return
            }
            $Visited.Value = [int]$Visited.Value + 1

            if ($null -eq $Value -or $Value -is [string]) {
                return
            }

            if ($Value -is [System.Array]) {
                $itemLimit = [Math]::Min($Value.Count, 64)
                for ($index = 0; $index -lt $itemLimit; $index++) {
                    Add-AICarminePromptFragments -Value $Value[$index] -Depth ($Depth + 1) -Remaining $Remaining -Visited $Visited -Fragments $Fragments
                    if ($Remaining.Value -le 0 -or $Visited.Value -ge 256) {
                        break
                    }
                }
                return
            }

            if ($Value -isnot [System.Collections.IDictionary] -and
                $Value -isnot [pscustomobject]) {
                return
            }

            $properties = @($Value.PSObject.Properties)
            $propertyLimit = [Math]::Min($properties.Count, 64)
            $acceptedNames = @('prompt', 'userprompt', 'user_prompt', 'message', 'content', 'text')
            for ($index = 0; $index -lt $propertyLimit; $index++) {
                $property = $properties[$index]
                $propertyName = ([string]$property.Name).ToLowerInvariant()
                $propertyValue = $property.Value

                if ($acceptedNames -contains $propertyName -and $propertyValue -is [string] -and
                    -not [string]::IsNullOrEmpty($propertyValue)) {
                    if ($Fragments.Count -gt 0) {
                        if ($Remaining.Value -le 1) {
                            return
                        }
                        $Remaining.Value = [int]$Remaining.Value - 1
                    }
                    $takeLength = [Math]::Min($propertyValue.Length, [int]$Remaining.Value)
                    if ($takeLength -gt 0) {
                        [void]$Fragments.Add($propertyValue.Substring(0, $takeLength))
                        $Remaining.Value = [int]$Remaining.Value - $takeLength
                    }
                }

                if ($Depth -lt 4 -and $Remaining.Value -gt 0) {
                    Add-AICarminePromptFragments -Value $propertyValue -Depth ($Depth + 1) -Remaining $Remaining -Visited $Visited -Fragments $Fragments
                }
                if ($Remaining.Value -le 0 -or $Visited.Value -ge 256) {
                    break
                }
            }
        }

        $parsedInput = ConvertFrom-Json -InputObject $RawInput -ErrorAction Stop
        $fragments = [System.Collections.Generic.List[string]]::new()
        $remaining = 12000
        $visited = 0
        $remainingReference = [ref]$remaining
        $visitedReference = [ref]$visited
        Add-AICarminePromptFragments -Value $parsedInput -Depth 0 -Remaining $remainingReference -Visited $visitedReference -Fragments $fragments

        if ($fragments.Count -eq 0) {
            return ''
        }

        $promptText = [string]::Join([Environment]::NewLine, $fragments.ToArray())
        if ([string]::IsNullOrWhiteSpace($promptText)) {
            return ''
        }
        $normalized = [regex]::Replace($promptText.ToLowerInvariant(), '\s+', ' ').Trim()

        function Test-AICarmineSignalAtIndexNegated {
            param([string]$Text, [int]$Index)

            if ($Index -le 0) {
                return $false
            }
            $start = [Math]::Max(0, $Index - 80)
            $window = $Text.Substring($start, $Index - $start)
            $lastBoundary = -1
            foreach ($separator in @('.', ';', '!', '?', [string][char]10, [string][char]13)) {
                $candidate = $window.LastIndexOf($separator, [StringComparison]::Ordinal)
                if ($candidate -gt $lastBoundary) {
                    $lastBoundary = $candidate
                }
            }
            if ($lastBoundary -ge 0) {
                $window = $window.Substring($lastBoundary + 1)
            }
            return $window -match '(?i)(?:^|\W)(?:non|no|senza|evitare|vietato|proibito|do not|don''t|dont|never|without|avoid|must not)(?:\W|$)'
        }

        function Test-AICarmineNegatedSignal {
            param([string]$Text, [string]$Pattern)

            foreach ($match in [regex]::Matches($Text, $Pattern, [Text.RegularExpressions.RegexOptions]::IgnoreCase)) {
                if (Test-AICarmineSignalAtIndexNegated -Text $Text -Index $match.Index) {
                    return $true
                }
            }
            return $false
        }

        function Test-AICarminePositiveSignal {
            param([string]$Text, [string]$Pattern)

            foreach ($match in [regex]::Matches($Text, $Pattern, [Text.RegularExpressions.RegexOptions]::IgnoreCase)) {
                if (-not (Test-AICarmineSignalAtIndexNegated -Text $Text -Index $match.Index)) {
                    return $true
                }
            }
            return $false
        }

        $sourceWritePattern = '(?:\bapplica(?:re)?\b.{0,24}\b(?:patch|diff)\b|\b(?:correggi|modifica(?:re)?|implementa|modify|edit|fix|replace)\b.{0,48}\b(?:file|source|codice|router|patch)\b|\b(?:crea|create)\b.{0,24}\bpatch\b|\b(?:write|scrivi)\b.{0,24}\b(?:file|source|codice)\b)'
        $memoryUpsertPattern = '(?:\bupsert(?:_verified)?\b|\bmemory write\b|\bupdate project[\s-]+memory\b|\b(?:scrivi|aggiorna|salva)\b.{0,32}\b(?:project[\s-]+memory|memoria)\b|\bcrea(?:ndo|re)?\b.{0,24}\b(?:un )?record\b|\b(?:create|save|write|update)\b.{0,24}\b(?:record|project[\s-]+memory)\b)'
        $memorySupersedePattern = '(?:\bsupersede(?:d)?\b|\bsostituisci\b.{0,24}\b(?:il )?record\b|\breplace\b.{0,24}\b(?:old )?record\b)'
        $memoryMarkStalePattern = '(?:\bmark[\s_-]+stale\b|\bmarca(?:re)?\b.{0,24}\b(?:stale|obsoleto)\b|\binvalida\b.{0,24}\b(?:il )?record\b|\binvalidate\b.{0,24}\brecord\b)'
        $serviceMutationPattern = '(?:\b(?:avvia|riavvia|start|restart)\b.{0,24}\b(?:servizi?|services?)\b)'
        $commitPattern = '(?:\b(?:esegui|crea|create|make)\b.{0,20}\bcommit\b|\bgit commit\b)'
        $pushPattern = '(?:\b(?:esegui|fai|run)\b.{0,20}\bpush\b|\bgit push\b|\bpush\b)'

        $negatedSourceWrite = Test-AICarmineNegatedSignal -Text $normalized -Pattern $sourceWritePattern
        $negatedMemoryWrite = (Test-AICarmineNegatedSignal -Text $normalized -Pattern $memoryUpsertPattern) -or
            (Test-AICarmineNegatedSignal -Text $normalized -Pattern $memorySupersedePattern) -or
            (Test-AICarmineNegatedSignal -Text $normalized -Pattern $memoryMarkStalePattern)
        $positiveSourceWrite = Test-AICarminePositiveSignal -Text $normalized -Pattern $sourceWritePattern
        $memoryUpsertRequested = Test-AICarminePositiveSignal -Text $normalized -Pattern $memoryUpsertPattern
        $memorySupersedeRequested = Test-AICarminePositiveSignal -Text $normalized -Pattern $memorySupersedePattern
        $memoryMarkStaleRequested = Test-AICarminePositiveSignal -Text $normalized -Pattern $memoryMarkStalePattern
        $memoryWriteRequested = $memoryUpsertRequested -or $memorySupersedeRequested -or $memoryMarkStaleRequested

        $explicitExistingDiff = $normalized -match '(\bdiff gi[àa] esistente\b|\bunified diff fornita\b|\bvalida questa diff\b|\bapply-check della diff\b|\busa questa unified diff\b|\bapplica la diff seguente\b|\bthe following unified diff\b|\bexisting diff\b|\bdiff gi[àa] pronta\b|\bunified diff gi[àa] pronta\b|\bpatch gi[àa] fornita\b|\bunified diff esistente\b)'
        $dryRunRequested = $explicitExistingDiff -or $normalized -match '(\bdry[\s-]?run\b|\bsmoke\b|\bapply[\s-]?check\b|\bvalida soltanto\b|\bverifica soltanto\b)'
        $noSourceWrite = $negatedSourceWrite -or $normalized -match '(\bnon modificare\b|\bsenza modificare\b|\bno patch\b|\bno source write\b|\bnon effettuare\b.{0,24}\bscrittur[ae]\b)'
        $noMemoryWrite = $negatedMemoryWrite -or
            (($normalized -match '(\bproject[\s-]+memory\b|\bmemoria\b)') -and
             ($normalized -match '(\bnon effettuare\b.{0,24}\bscrittur[ae]\b|\bno memory write\b|\bno write\b)'))
        $noServiceMutation = (Test-AICarmineNegatedSignal -Text $normalized -Pattern $serviceMutationPattern) -or
            $normalized -match '(\bno service mutation\b|\bnon avviare servizi\b)'
        $noCommit = (Test-AICarmineNegatedSignal -Text $normalized -Pattern $commitPattern) -or
            $normalized -match '(\bno commit\b|\bnon fare commit\b)'
        $noPush = (Test-AICarmineNegatedSignal -Text $normalized -Pattern $pushPattern) -or
            $normalized -match '(\bno push\b|\bnon fare push\b)'
        $readOnly = $normalized -match '(\bread[\s-]?only\b|\breadonly\b|\bsola lettura\b|\banalysis only\b|\bsolo analisi\b|\baudit\b)' -or $noSourceWrite
        $explicitMemoryWrite = $memoryWriteRequested -and -not $readOnly -and -not $noMemoryWrite
        $explicitSourceWrite = $positiveSourceWrite -and -not $readOnly -and -not $noSourceWrite

        $reviewedProbe = $normalized -match '(\breviewed probe\b|\bprobe profile\b|\bprofilo probe\b|\bprofile_id\b|\baicarmine_repo_validate_probe_run\b|\borientation\.selector\.contract\.v1\b)'
        $probeRequested = $reviewedProbe -or
            $normalized -match '(\b(?:esegui|execute|run|avvia)\b.{0,40}\bprobe\b|\bprobe\b.{0,40}\b(?:profile|profilo)\b)'

        $scores = [ordered]@{
            repository_validation = 0
            repository_patch = 0
            repository_search = 0
            project_memory = 0
            repository_state = 0
            git_readonly = 0
            job_diagnostics = 0
        }

        if ($reviewedProbe) { $scores.repository_validation += 100 }
        if ($normalized -match '\b(?:diffcheck|ruff|pyright|pytest|semgrep|py_compile|probe_run)\b') {
            $scores.repository_validation += 100
        }
        if ($probeRequested -or
            $normalized -match '\b(?:verifica|valida|validate|testa|compile|controlla)\b.{0,48}\b(?:diff|patch|contratto|contract|invariant[ei]|probe|test|codice|code)\b') {
            $scores.repository_validation += 60
        }
        if ($normalized -match '\b(?:audit contract|controlla invarianti)\b') {
            $scores.repository_validation += 60
        }
        if ($readOnly -and $normalized -match '\baudit\b') {
            $scores.repository_validation += 40
        }
        if ($dryRunRequested) { $scores.repository_validation += 60 }
        if ($scores.repository_validation -eq 0 -and
            $normalized -match '\b(?:verifica|validate|validation|test)\b') {
            $scores.repository_validation += 10
        }

        if ($normalized -match '\bstructured_edit\b') { $scores.repository_patch += 100 }
        if ($positiveSourceWrite) { $scores.repository_patch += 60 }
        if ($normalized -match '\b(?:patch|diff|change_set|change-set)\b') {
            $scores.repository_patch += 10
        }
        if ($explicitExistingDiff -and -not $positiveSourceWrite) {
            $scores.repository_patch = [Math]::Min($scores.repository_patch, 10)
        }

        if ($normalized -match '\b(?:aicarmine_repo_search_rg|aicarmine_repo_search_ctags|rg|ctags|ast-grep|tree[\s-]sitter)\b') {
            $scores.repository_search += 100
        }
        if (Test-AICarminePositiveSignal -Text $normalized -Pattern '\b(?:trova|cerca|localizza|search|find|locate)\b') {
            $scores.repository_search += 60
        }
        if ($normalized -match '\b(?:definizione|definition|caller|call site|riferiment[oi]|reference|simbolo|symbol)\b') {
            $scores.repository_search += 25
        }
        if ($normalized -match '\b(?:analizza|analyze)\b.{0,32}\b(?:owner|readers?|writers?)\b') {
            $scores.repository_search += 40
        }

        $memoryObject = $normalized -match '\b(?:project[\s-]+memory|memoria persistente|exact[\s-]key|record_id)\b'
        if ($memoryWriteRequested -and $memoryObject) { $scores.project_memory += 60 }
        if ($normalized -match '\b(?:warmup|carica|leggi|cerca)\b.{0,36}\b(?:project[\s-]+memory|memoria|record)\b' -or
            $normalized -match '\b(?:audit|verifica)\b.{0,36}\b(?:project[\s-]+memory|memoria|manifest)\b' -or
            $normalized -match '\b(?:project[\s-]+memory|memoria)\b.{0,36}\b(?:manifest|exact[\s-]key|record_id)\b') {
            $scores.project_memory += 60
        }
        if ($memoryObject -and $normalized -match '\b(?:exact[\s-]key|record_id|manifest)\b') {
            $scores.project_memory += 25
        }
        if ($scores.project_memory -eq 0 -and $memoryObject) {
            $scores.project_memory += 5
        }
        if ($negatedMemoryWrite -and $scores.project_memory -le 5) {
            $scores.project_memory = 0
        }

        if ($normalized -match '\b(?:git status|working tree|staged state|repo root|repository root|cwd)\b' -or
            $normalized -match '\bverifica\b.{0,32}\b(?:branch|head|stato repository)\b') {
            $scores.repository_state += 60
        }

        if ($normalized -match '\b(?:git log|git show|blame|diff storico|historical diff|compare commits?|confronta (?:i )?commit|branch compare)\b') {
            $scores.git_readonly += 100
        }
        if ($normalized -match '\b(?:history|commit regression analysis|regressione)\b') {
            $scores.git_readonly += 60
        }
        if ($scores.git_readonly -eq 0 -and $normalized -match '\bcommit\b') {
            $scores.git_readonly += 10
        }

        if ($normalized -match '\b(?:job artifact|planner payload|subturn|rejection|eventi job|job events|job view|job html|html job diagnostic)\b') {
            $scores.job_diagnostics += 60
        }
        elseif ($normalized -match '\bjob\b') {
            $scores.job_diagnostics += 10
        }

        $classes = [System.Collections.Generic.List[string]]::new()
        $tools = [System.Collections.Generic.List[string]]::new()
        $tieOrder = @{
            repository_validation = 0
            repository_patch = 1
            repository_search = 2
            project_memory = 3
            repository_state = 4
            git_readonly = 5
            job_diagnostics = 6
        }
        $rankedClasses = @(
            $scores.GetEnumerator() |
                Where-Object { [int]$_.Value -ge 20 } |
                Sort-Object -Property @{ Expression = { -[int]$_.Value } }, @{ Expression = { $tieOrder[[string]$_.Key] } } |
                Select-Object -First 4
        )
        foreach ($entry in $rankedClasses) {
            [void]$classes.Add([string]$entry.Key)
        }

        function Add-AICarmineTool {
            param([string]$Name)
            if ($tools.Count -lt 6 -and -not $tools.Contains($Name)) {
                [void]$tools.Add($Name)
            }
        }

        if ($reviewedProbe -and $classes.Contains('repository_validation')) {
            Add-AICarmineTool -Name 'aicarmine_repo_validate_probe_profiles'
            Add-AICarmineTool -Name 'aicarmine_repo_validate_probe_run'
        }

        foreach ($className in $classes) {
            switch ($className) {
                'repository_validation' {
                    if ($explicitExistingDiff) {
                        Add-AICarmineTool -Name 'aicarmine_repo_code_unidiff_validate'
                        Add-AICarmineTool -Name 'aicarmine_repo_code_git_apply_check'
                    }
                    if ($normalized -match '\bdiffcheck\b') { Add-AICarmineTool -Name 'aicarmine_repo_validate_diffcheck' }
                    if ($normalized -match '\bruff\b') { Add-AICarmineTool -Name 'aicarmine_repo_validate_ruff' }
                    if ($normalized -match '\bpyright\b') { Add-AICarmineTool -Name 'aicarmine_repo_validate_pyright' }
                    if ($normalized -match '\bpytest\b') { Add-AICarmineTool -Name 'aicarmine_repo_validate_pytest' }
                    if ($normalized -match '\bsemgrep\b') { Add-AICarmineTool -Name 'aicarmine_repo_validate_semgrep' }
                    Add-AICarmineTool -Name 'aicarmine_repo_validate_health'
                }
                'repository_patch' {
                    if (-not $readOnly -or $dryRunRequested) {
                        Add-AICarmineTool -Name 'aicarmine_repo_code_health'
                        Add-AICarmineTool -Name 'aicarmine_repo_code_propose_edit'
                        Add-AICarmineTool -Name 'aicarmine_repo_code_unidiff_validate'
                        Add-AICarmineTool -Name 'aicarmine_repo_code_git_apply_check'
                        if (-not $readOnly -and -not $noSourceWrite) {
                            Add-AICarmineTool -Name 'aicarmine_repo_code_apply_patch'
                        }
                    }
                }
                'repository_search' {
                    Add-AICarmineTool -Name 'aicarmine_repo_search_det_health'
                    if ($normalized -match '\b(?:definition|definizione|caller|call site|riferiment[oi]|reference|rg|grep)\b') {
                        Add-AICarmineTool -Name 'aicarmine_repo_search_rg'
                    }
                    if ($normalized -match '\b(?:file|path)\b') { Add-AICarmineTool -Name 'aicarmine_repo_search_fd' }
                    if ($normalized -match '\b(?:ast|ast-grep)\b') { Add-AICarmineTool -Name 'aicarmine_repo_search_ast_grep' }
                    if ($normalized -match '\btree[\s-]sitter\b') { Add-AICarmineTool -Name 'aicarmine_repo_search_tree_sitter_parse' }
                    if ($normalized -match '\b(?:ctags|symbol|simbolo|definition|definizione)\b') {
                        Add-AICarmineTool -Name 'aicarmine_repo_search_ctags'
                    }
                }
                'project_memory' {
                    Add-AICarmineTool -Name 'aicarmine_project_memory_health'
                    Add-AICarmineTool -Name 'aicarmine_project_memory_search'
                    Add-AICarmineTool -Name 'aicarmine_project_memory_get'
                    if ($explicitMemoryWrite) {
                        if ($memoryUpsertRequested) { Add-AICarmineTool -Name 'aicarmine_project_memory_upsert_verified' }
                        if ($memorySupersedeRequested) { Add-AICarmineTool -Name 'aicarmine_project_memory_supersede' }
                        if ($memoryMarkStaleRequested) { Add-AICarmineTool -Name 'aicarmine_project_memory_mark_stale' }
                    }
                }
                'repository_state' {
                    Add-AICarmineTool -Name 'aicarmine_repo_state_health'
                }
                'git_readonly' {
                    Add-AICarmineTool -Name 'aicarmine_git_readonly_health'
                    if ($normalized -match '\b(?:git log|history)\b') { Add-AICarmineTool -Name 'aicarmine_git_readonly_log' }
                    if ($normalized -match '\b(?:git show|commit)\b') { Add-AICarmineTool -Name 'aicarmine_git_readonly_show' }
                    if ($normalized -match '\b(?:diff storico|historical diff)\b') { Add-AICarmineTool -Name 'aicarmine_git_readonly_diff' }
                    if ($normalized -match '\bblame\b') { Add-AICarmineTool -Name 'aicarmine_git_readonly_blame' }
                    if ($normalized -match '\b(?:branch compare|compare commits?|confronta (?:i )?commit)\b') {
                        Add-AICarmineTool -Name 'aicarmine_git_readonly_branch_compare'
                    }
                }
                'job_diagnostics' {
                    Add-AICarmineTool -Name 'aicarmine_job_artifact'
                    Add-AICarmineTool -Name 'aicarmine_job_view'
                }
            }
        }

        if ($classes.Count -eq 0) {
            return ''
        }

        $lines = [System.Collections.Generic.List[string]]::new()
        [void]$lines.Add('AICARMINE MCP ROUTING HINT')
        [void]$lines.Add('')
        [void]$lines.Add('Task classes:')
        foreach ($className in $classes) {
            [void]$lines.Add(('- {0}' -f $className))
        }

        [void]$lines.Add('')
        [void]$lines.Add('Preferred sequence:')
        for ($index = 0; $index -lt $tools.Count; $index++) {
            [void]$lines.Add(('{0}. {1}' -f ($index + 1), $tools[$index]))
        }

        [void]$lines.Add('')
        [void]$lines.Add('Constraints:')
        [void]$lines.Add('- Use native fallback only after a concrete MCP failure.')
        [void]$lines.Add('- Do not repeat an unchanged failed tool call.')
        [void]$lines.Add('- Emit MCP arguments as structured data, not shell-built JSON.')

        if ($explicitExistingDiff) {
            [void]$lines.Add('- existing_diff_only: use the already-provided unified_diff; do not regenerate it.')
        }
        elseif ($classes.Contains('repository_patch')) {
            [void]$lines.Add('- Prefer structured_edit for changes authored by the model.')
        }
        if ($classes.Contains('repository_patch') -or $explicitExistingDiff) {
            [void]$lines.Add('- Do not manually calculate unified-diff hunk headers.')
            [void]$lines.Add('- Propagate change_set_id through validate and apply-check; apply only when explicitly authorized.')
            [void]$lines.Add('- Do not reconstruct whole files or create manual .diff transport files.')
        }
        if ($readOnly) {
            [void]$lines.Add('- Read-only: validate and apply-check are allowed; do not call apply_patch or state-write tools.')
        }
        if ($noSourceWrite) { [void]$lines.Add('- no_source_write: do not call source write tools.') }
        if ($noMemoryWrite) { [void]$lines.Add('- no_memory_write: do not call project-memory write tools.') }
        if ($noServiceMutation) { [void]$lines.Add('- no_service_mutation: do not mutate services.') }
        if ($noCommit) { [void]$lines.Add('- no_commit: do not create commits.') }
        if ($noPush) { [void]$lines.Add('- no_push: do not push.') }
        if ($explicitMemoryWrite) { [void]$lines.Add('- explicit_memory_write: only the requested memory write is in scope.') }
        if ($explicitSourceWrite) { [void]$lines.Add('- explicit_source_write: source apply still requires authorization.') }
        if ($reviewedProbe) {
            [void]$lines.Add('- Use the exact profile_id returned by probe_profiles before probe_run.')
        }

        $hint = [string]::Join([Environment]::NewLine, $lines.ToArray())
        if ($hint.Length -gt 1400) {
            return ''
        }
        return [string]$hint
    }
    catch {
        return ''
    }
    finally {
        $parsedInput = $null
        $promptText = $null
        $normalized = $null
    }
}
