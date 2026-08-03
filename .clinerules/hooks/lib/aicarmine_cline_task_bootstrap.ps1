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
            '- Deterministic search: aicarmine_repo_search_det',
            '- La superficie runtime scoperta è autoritativa rispetto alla mappa orientativa',
            '- Git history: aicarmine_git_readonly',
            '- Project memory: aicarmine_project_memory',
            '- Runtime evidence loop agentic: aicarmine_job_artifact and aicarmine_job_view',
            '- Semantic orientation: aicarmine_rag',
            '- Local read-only data and operations: aicarmine_sqlite_readonly and aicarmine_codex_ops',
            '',
            'MCP SERVER INVENTORY (16 servers, 95 tools):',
            '',
            'Core Infrastructure:',
            '- aicarmine-codex-app (37 tools): Master facade, terminal ops, repo CRUD, memory writes',
            '- aicarmine-codex-ops (9 tools): Inventory, service state, ports, processes, logs',
            '',
            'Repository Operations:',
            '- aicarmine-repo-state (3 tools): Branch, commit, status, capabilities',
            '- aicarmine-repo-search-det (8 tools): fd, ripgrep, ast-grep, tree-sitter, ctags, jq',
            '- aicarmine-repo-code (5 tools): structured_edit, unified_diff, patch apply',
            '- aicarmine-repo-validate (9 tools): ruff, pyright, pytest, shellcheck, semgrep',
            '- aicarmine-git-readonly (6 tools): log, show, diff, blame, branch-compare',
            '',
            'Runtime & Jobs:',
            '- aicarmine-job-artifact (9 tools): Job events, final output, tool results, planner payloads',
            '- aicarmine-job-view (8 tools): HTML dashboard, events, final JSON, IA view',
            '- aicarmine-agentic-loop-client (7 tools): Agentic loop run, status, result, broker/reranker',
            '- aicarmine-local-subagent (3 tools): Read-only bounded agentic tasks via dedicated port',
            '- aicarmine-broker-planner (8 tools): Planner state, decision history, validator diagnostics',
            '- aicarmine-planner-components (5 tools): Orientation shadow, vulkan repair, replan, guard rejection',
            '',
            'Data & Memory:',
            '- aicarmine-project-memory (7 tools): Search, upsert, mark-stale, supersede, audit sources',
            '- aicarmine-sqlite-readonly (4 tools): List databases, schema, SELECT queries',
            '- aicarmine-rag (3 tools): RAG context search, index status, reindex',
            '- aicarmine-rag-router (7 tools): Cross-DB query planning, topics, consolidation',
            '',
            'Model & Inference:',
            '- aicarmine-ollama (13 tools): Model list, show, chat, generate, create, copy',
            '- aicarmine-ovms-reranker (8 tools): Rerank, model list, config, start/stop',
            '',
            'AUTOMATIC MCP ROUTING PATTERNS:',
            '- Repository search/file discovery → aicarmine-repo-search-det',
            '- Code editing/patch application → aicarmine-repo-code',
            '- Validation/linting → aicarmine-repo-validate',
            '- Git history/diff inspection → aicarmine-git-readonly',
            '- Job artifact inspection → aicarmine-job-artifact',
            '- Job view/dashboard → aicarmine-job-view',
            '- Project memory read/write → aicarmine-project-memory',
            '- SQLite query → aicarmine-sqlite-readonly',
            '- RAG context search → aicarmine-rag',
            '- RAG cross-DB planning → aicarmine-rag-router',
            '- Ollama model operations → aicarmine-ollama',
            '- OVMS reranker operations → aicarmine-ovms-reranker',
            '- Agentic loop execution → aicarmine-agentic-loop-client',
            '- Local subagent task → aicarmine-local-subagent',
            '- Planner state inspection → aicarmine-broker-planner',
            '- Service state/ports → aicarmine-codex-ops',
            '',
            'RUNTIME PORTS:',
            '- 3550: OVMS Reranker (ovms.exe)',
            '- 3571: Vulkan Bridge (uvicorn)',
            '- 3572: Vulkan Tool Broker (uvicorn)',
            '- 3579: Agentic Loop Client (uvicorn)',
            '- 11434: Ollama (ollama.exe)',
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