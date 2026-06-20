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
        $normalized = $promptText.ToLowerInvariant()

        $readOnly = $normalized -match '(\bread[\s-]?only\b|\breadonly\b|\bsola lettura\b|\bnon modificare\b|\bnon applicare\b|\bno patch\b|\bno write\b|\banalysis only\b|\bsolo analisi\b|\baudit\b)'
        $positiveText = $normalized -replace '(\bread[\s-]?only\b|\breadonly\b|\bsola lettura\b|\bnon modificare\b|\bnon applicare\b|\bno patch\b|\bno write\b|\banalysis only\b|\bsolo analisi\b|\baudit\b)', ' '

        $projectMemory = $normalized -match '(\bproject[\s-]+memory\b|\bmemoria persistente\b|\bwarmup\b|\brecord_id\b|\bexact[\s-]key\b|\bmanifest\b)'
        $strongSearch = $normalized -match '(\btrova\b|\bcerca\b|\bsearch\b|\bfind\b|\bsymbol\b|\bsimbolo\b|\bdefinition\b|\bdefinizione\b|\bcaller\b|\bcall site\b|\briferimento\b|\breference\b|\bpath\b|\brg\b|\bgrep\b|\bast\b|\bctags\b|\btree[\s-]sitter\b)'
        $fileSearch = $normalized -match '(\b(read|leggi|inspect|ispeziona)\b.{0,40}\bfile\b|\bfile\b.{0,40}\b(trova|cerca|search|find)\b)'
        $repositorySearch = $strongSearch -or $fileSearch -or ($readOnly -and $normalized -match '\bfile\b')
        $repositoryPatch = $positiveText -match '(\bpatch\b|\bmodifica\b|\bmodificare\b|\bmodify\b|\bedit\b|\bcorreggi\b|\bfix\b|\breplace\b|\bdiff\b|\bunified diff\b|\bchange_set\b|\bchange-set\b|\bapply\b)'
        $explicitExistingDiff = $normalized -match '(\busa questa unified diff\b|\bapplica la diff seguente\b|\bthe following unified diff\b|\bexisting diff\b|\bdiff gi[àa] pronta\b|\bunified diff gi[àa] pronta\b|\bpatch gi[àa] fornita\b)'
        $reviewedProbe = $normalized -match '(\breviewed probe\b|\bprobe profile\b|\bprofilo probe\b|\borientation\.selector\.contract\.v1\b)'
        $probeRequested = $reviewedProbe -or
            $normalized -match '(\b(esegui|execute|run|avvia)\b.{0,40}\bprobe\b|\bprobe\b.{0,40}\b(profile|profilo)\b)'
        $repositoryValidation = $normalized -match '(\bverifica\b|\bvalidate\b|\bvalidation\b|\bcompile\b|\bpy_compile\b|\bruff\b|\bpyright\b|\bpytest\b|\bsemgrep\b|\bdiffcheck\b|\btest\b)' -or $probeRequested

        $gitReadonly = $normalized -match '(\bgit log\b|\bgit show\b|\bhistory\b|\bcommit\b|\bblame\b|\bbranch compare\b|\bcompare commit\b|\bdiff storico\b|\bhistorical diff\b)'
        $jobDiagnostics = $normalized -match '(\bjob\b|\bartifact\b|\bplanner payload\b|\bsubturn\b|\brejection\b|\beventi job\b|\bjob html\b|\bjob view\b)'

        $classes = [System.Collections.Generic.List[string]]::new()
        $tools = [System.Collections.Generic.List[string]]::new()

        function Add-AICarmineClass {
            param([string]$Name)
            if (-not $classes.Contains($Name)) {
                [void]$classes.Add($Name)
            }
        }

        function Add-AICarmineTool {
            param([string]$Name)
            if ($tools.Count -lt 6 -and -not $tools.Contains($Name)) {
                [void]$tools.Add($Name)
            }
        }

        if ($projectMemory) {
            Add-AICarmineClass -Name 'project_memory'
            Add-AICarmineTool -Name 'aicarmine_project_memory_health'
            Add-AICarmineTool -Name 'aicarmine_project_memory_search'
            Add-AICarmineTool -Name 'aicarmine_project_memory_get'

            if (-not $readOnly) {
                if ($normalized -match '\b(upsert_verified|upsert)\b' -or
                    ($normalized -match '\b(salva|scrivi|write|persisti)\b' -and $normalized -match '\b(project[\s-]+memory|memoria persistente)\b')) {
                    Add-AICarmineTool -Name 'aicarmine_project_memory_upsert_verified'
                }
                if ($normalized -match '\b(supersede|superseded)\b') {
                    Add-AICarmineTool -Name 'aicarmine_project_memory_supersede'
                }
                if ($normalized -match '\b(mark[\s-]+stale|marca(?:re)? stale)\b') {
                    Add-AICarmineTool -Name 'aicarmine_project_memory_mark_stale'
                }
            }
        }

        if ($repositorySearch) {
            Add-AICarmineClass -Name 'repository_search'
            Add-AICarmineTool -Name 'aicarmine_repo_search_det_health'

            if ($normalized -match '(\bsymbol\b|\bsimbolo\b|\bdefinition\b|\bdefinizione\b|\bcaller\b|\bcall site\b|\briferimento\b|\breference\b|\brg\b|\bgrep\b)') {
                Add-AICarmineTool -Name 'aicarmine_repo_search_rg'
            }
            if ($normalized -match '(\bfile\b|\bpath\b)' -and
                $normalized -match '(\btrova\b|\bcerca\b|\bsearch\b|\bfind\b|\bread\b|\bleggi\b|\binspect\b|\bispeziona\b|\baudit\b)') {
                Add-AICarmineTool -Name 'aicarmine_repo_search_fd'
            }
            if ($normalized -match '\bast\b') {
                Add-AICarmineTool -Name 'aicarmine_repo_search_ast_grep'
            }
            if ($normalized -match '\btree[\s-]sitter\b') {
                Add-AICarmineTool -Name 'aicarmine_repo_search_tree_sitter_parse'
            }
            if ($normalized -match '(\bctags\b|\bsymbol\b|\bsimbolo\b|\bdefinition\b|\bdefinizione\b)') {
                Add-AICarmineTool -Name 'aicarmine_repo_search_ctags'
            }
        }

        if ($repositoryPatch) {
            Add-AICarmineClass -Name 'repository_patch'
            Add-AICarmineTool -Name 'aicarmine_repo_code_health'
            Add-AICarmineTool -Name 'aicarmine_repo_code_propose_edit'
            Add-AICarmineTool -Name 'aicarmine_repo_code_unidiff_validate'
            Add-AICarmineTool -Name 'aicarmine_repo_code_git_apply_check'
            if (-not $readOnly) {
                Add-AICarmineTool -Name 'aicarmine_repo_code_apply_patch'
            }
        }

        if ($repositoryValidation) {
            Add-AICarmineClass -Name 'repository_validation'
            if ($tools.Count -lt 5) {
                Add-AICarmineTool -Name 'aicarmine_repo_validate_health'
            }
            if ($normalized -match '\bdiffcheck\b') {
                Add-AICarmineTool -Name 'aicarmine_repo_validate_diffcheck'
            }
            if ($normalized -match '\bruff\b') {
                Add-AICarmineTool -Name 'aicarmine_repo_validate_ruff'
            }
            if ($normalized -match '\bpyright\b') {
                Add-AICarmineTool -Name 'aicarmine_repo_validate_pyright'
            }
            if ($normalized -match '\bpytest\b') {
                Add-AICarmineTool -Name 'aicarmine_repo_validate_pytest'
            }
            if ($normalized -match '\bsemgrep\b') {
                Add-AICarmineTool -Name 'aicarmine_repo_validate_semgrep'
            }
            if ($probeRequested) {
                Add-AICarmineTool -Name 'aicarmine_repo_validate_probe_profiles'
                Add-AICarmineTool -Name 'aicarmine_repo_validate_probe_run'
            }
            if ($tools.Count -lt 6 -and -not $tools.Contains('aicarmine_repo_validate_health')) {
                Add-AICarmineTool -Name 'aicarmine_repo_validate_health'
            }
        }

        if ($gitReadonly) {
            Add-AICarmineClass -Name 'git_readonly'
            Add-AICarmineTool -Name 'aicarmine_git_readonly_health'
            if ($normalized -match '(\bgit log\b|\bhistory\b)') {
                Add-AICarmineTool -Name 'aicarmine_git_readonly_log'
            }
            if ($normalized -match '(\bgit show\b|\bcommit\b)') {
                Add-AICarmineTool -Name 'aicarmine_git_readonly_show'
            }
            if ($normalized -match '(\bdiff storico\b|\bhistorical diff\b)') {
                Add-AICarmineTool -Name 'aicarmine_git_readonly_diff'
            }
            if ($normalized -match '\bblame\b') {
                Add-AICarmineTool -Name 'aicarmine_git_readonly_blame'
            }
            if ($normalized -match '(\bbranch compare\b|\bcompare commit\b)') {
                Add-AICarmineTool -Name 'aicarmine_git_readonly_branch_compare'
            }
        }

        if ($jobDiagnostics) {
            Add-AICarmineClass -Name 'job_diagnostics'
            Add-AICarmineTool -Name 'aicarmine_job_artifact'
            Add-AICarmineTool -Name 'aicarmine_job_view'
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

        if ($repositoryPatch) {
            if ($explicitExistingDiff) {
                [void]$lines.Add('- Use the already-provided unified_diff; do not regenerate it.')
            }
            else {
                [void]$lines.Add('- Prefer structured_edit for changes authored by the model.')
            }
            [void]$lines.Add('- Do not manually calculate unified-diff hunk headers.')
            [void]$lines.Add('- Propagate change_set_id through validate and apply-check; apply only when explicitly authorized.')
            [void]$lines.Add('- Do not reconstruct whole files or create manual .diff transport files.')
        }
        if ($readOnly) {
            [void]$lines.Add('- Read-only: validate and apply-check are allowed; do not call apply_patch or state-write tools.')
        }
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
