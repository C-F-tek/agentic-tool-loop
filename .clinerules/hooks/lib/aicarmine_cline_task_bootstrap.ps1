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
<<<<<<< HEAD
            'CRITICAL: Always prefer MCP tools over native Cline tools.',
            '',
            'MCP > Native Cline priority:',
            '- aicarmine_repo_read > read_file (truncation, structured output)',
            '- aicarmine_repo_search / aicarmine_repo_rg_search > search_files (context, filtering)',
            '- aicarmine_repo_list_files / aicarmine_repo_tree > list_files (bounded, repo-aware)',
            '- aicarmine_git_readonly_* > execute_command git (structured, Git-integrated)',
            '- aicarmine_sqlite_readonly_* > execute_command sqlite3 (allowlist, bounded)',
            '',
            'Workflow before modifying files:',
            '1. aicarmine_repo_read → read the actual file',
            '2. aicarmine_git_readonly_diff → check uncommitted changes',
            '3. aicarmine_git_readonly_log → check recent history',
            '4. aicarmine_repo_status → verify repository state',
            '',
            'Workflow before searching information:',
            '1. aicarmine_rag_context → semantic orientation',
            '2. aicarmine_repo_search → structured text search',
            '3. aicarmine_memory_state_packet → recover operational state',
            '',
            'Inizio della task:',
            '- Leggi gli AGENTS.md applicabili e i contratti richiesti',
            '- Esegui il discovery nativo della superficie MCP esposta dalla sessione corrente',
            '- Filtra e riconosci le famiglie con prefisso aicarmine_. sono tool su misura per il progetto',
=======
            'Inizio della task:',
            '- Leggi gli AGENTS.md applicabili e i contratti richiesti',
            '- Esegui il discovery nativo della superficie MCP esposta dalla sessione corrente',
            '- Filtra e riconosci le famiglie con prefisso aicarmine_. sono tool su misura per il proggetto',
>>>>>>> f00b7873c326fa2c8e93286beb4604e3655f9aa8
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
