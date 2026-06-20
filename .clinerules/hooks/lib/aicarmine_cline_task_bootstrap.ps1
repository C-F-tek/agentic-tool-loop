function Get-AICarmineClineTaskBootstrap {
    [CmdletBinding()]
    param(
        [AllowEmptyString()]
        [string]$RawInput
    )

    try {
        if ([string]::IsNullOrWhiteSpace($RawInput)) {
            return ''
        }

        $payload = $RawInput | ConvertFrom-Json -ErrorAction Stop
        if ($payload -isnot [System.Management.Automation.PSCustomObject]) {
            return ''
        }

        $taskIdentity = $null
        foreach ($alias in @('taskId', 'task_id', 'taskID')) {
            $property = $payload.PSObject.Properties[$alias]
            if ($null -ne $property) {
                $taskIdentity = $property.Value
                break
            }
        }

        if ($taskIdentity -isnot [string]) {
            return ''
        }
        if ($taskIdentity.Length -eq 0 -or $taskIdentity.Length -gt 512) {
            return ''
        }
        if ([string]::IsNullOrWhiteSpace($taskIdentity)) {
            return ''
        }

        $lines = @(
            'AICARMINE TASK BOOTSTRAP',
            '',
            'Operating method:',
            '- Use current source, Git state, runtime evidence and the current Cline tool schema as authoritative.',
            '- Read the applicable AGENTS.md before modifying repository files.',
            '- Use only the repository capability relevant to the current task; do not run a blanket health sweep.',
            '- UserPromptSubmit will add task-specific MCP routing after the user prompt.',
            '',
            'Inizio della task:',
            '- Leggi gli AGENTS.md applicabili e i contratti richiesti',
            '- Esegui il discovery nativo della superficie MCP esposta dalla sessione corrente',
            '- Filtra e riconosci le famiglie con prefisso aicarmine_. sono tool su misura per il proggetto',
            '- Deterministic search: aicarmine_repo_search_det',
            '- La superficie runtime scoperta è autoritativa rispetto alla mappa orientativa riportata sotto',
            '- Git history: aicarmine_git_readonly',
            '- Project memory: aicarmine_project_memory',
            '- Runtime evidence loop agentic: aicarmine_job_artifact and aicarmine_job_view',
            '- Semantic orientation: aicarmine_rag',
            '- Local read-only data and operations: aicarmine_sqlite_readonly and aicarmine_codex_ops',
            '',
            'Failure handling:',
            '- Do not repeat an unchanged failed tool call.',
            '- Use a native fallback only after a concrete MCP failure and report that failure.',
            '- Treat a missing tool in the current client schema as a possible stale-client condition; do not invent the tool.',
            '',
            'Boundaries:',
            '- Cline auto-approval.',
            '- Do not activate agentic loop, local subagent or service mutation unless explicitly requested.'
        )

        $bootstrap = $lines -join [Environment]::NewLine
        if ($bootstrap.Length -gt 1800) {
            return ''
        }
        return [string]$bootstrap
    }
    catch {
        return ''
    }
}
