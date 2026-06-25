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
            '- Filtra e riconosci le famiglie con prefisso aicarmine_. sono tool su misura per il progetto',
            '',
            'MCP Servers (25 total, 87 tools verified against source):',
            '- Core: aicarmine_repo_state(3), aicarmine_repo_search_det(8), aicarmine_repo_validate(9), aicarmine_repo_code(5)',
            '- Data: aicarmine_rag(4 incl. health), aicarmine_sqlite_readonly(4), aicarmine_project_memory(7), aicarmine_index_bridge(5)',
            '- Jobs: aicarmine_job_artifact(9), aicarmine_job_view(8), aicarmine_git_readonly(6)',
            '- Ops: aicarmine_codex_ops(9), aicarmine_repo_symbol_index(4), aicarmine_test_discovery(5), aicarmine_code_dep_graph(7)',
            '- Refactor: refactor(8 tools, NO aicarmine_ prefix)',
            '- Agents: aicarmine_local_subagent(3), aicarmine_agentic_loop_client(7), aicarmine_ollama_subagent(4)',
            '- Analysis: aicarmine_enhanced_analysis(4 tools)',
            '- Format: aicarmine_prettier, aicarmine_biome, aicarmine_ruff, aicarmine_eslint, aicarmine_black (Cline built-in wrappers)',
            '',
            'Tool naming conventions:',
            '- Core/Data/Jobs/Ops/Analysis: aicarmine_* prefix',
            '- Refactor: NO prefix (refactor_rename_symbol, refactor_health, etc.)',
            '- Formatting servers: Cline built-in names (format_file, check_file)',
            '',
            'Deterministic search: aicarmine_repo_search_det (fd, rg, ast-grep, ctags, jq, tree-sitter)',
            'La superficie runtime scoperta è autoritativa rispetto alla mappa orientativa riportata sotto',
            'Git history: aicarmine_git_readonly (log, show, diff, blame, branch_compare)',
            'Project memory: aicarmine_project_memory (search, get, upsert_verified, mark_stale, supersede, audit_sources)',
            'Runtime evidence loop agentic: aicarmine_job_artifact and aicarmine_job_view',
            'Semantic orientation: aicarmine_rag + aicarmine_index_bridge (cross-reference RAG+Symbol Index)',
            'Local read-only data and operations: aicarmine_sqlite_readonly and aicarmine_codex_ops',
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
