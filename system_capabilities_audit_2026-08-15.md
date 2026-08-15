# System Capabilities Audit - 2026-08-15

## Executive Summary

This audit documents the current state of capabilities across MCP servers, skills, AGENTS.md contracts, hooks, and related infrastructure in the AICarmine agentic tool-loop system.

---

## 1. MCP Servers Inventory

### Connected Servers (24 total)

| # | Server Name | Tools | Health Check | Mode |
|---|-------------|-------|--------------|------|
| 1 | aicarmine-codex-app | ~30+ | aicarmine_bridge_health | Full operational |
| 2 | aicarmine-batch | 5 | health_check | Batch execution |
| 3 | aicarmine-repo-state | 3 | aicarmine_repo_state_status | Read-only repo state |
| 4 | aicarmine-ollama | 4 | aicarmine_ollama_subagent_health | Ollama subagent |
| 5 | aicarmine-repo-search-det | 8 | aicarmine_repo_search_det_health | Deterministic search |
| 6 | aicarmine-repo-validate | 9 | aicarmine_repo_validate_health | Validation |
| 7 | aicarmine-project-memory | 7 | aicarmine_project_memory_health | Project memory |
| 8 | aicarmine-sqlite-readonly | 4 | aicarmine_sqlite_readonly_health | SQLite read-only |
| 9 | aicarmine-rag | 3 | (none) | RAG indexing/search |
| 10 | aicarmine-rag-router | 5 | (implicit) | Multi-db RAG routing |
| 11 | aicarmine-job-artifact | 9 | aicarmine_job_artifact_health | Job artifacts |
| 12 | aicarmine-job-view | 8 | aicarmine_job_view_health | HTML job views |
| 13 | aicarmine-local-subagent | 3 | aicarmine_local_subagent_health | Subagent facade |
| 14 | aicarmine-agentic-loop-client | 7 | aicarmine_agentic_loop_health | Agentic loop client |
| 15 | aicarmine-repo-code | 5 | aicarmine_repo_code_health | Code editing |
| 16 | aicarmine-refactor | 7 | refactor_health | Refactoring |
| 17 | aicarmine-network-monitor | 8 | network_monitor_health | Network monitoring |
| 18 | aicarmine-symbol-rag | 4 | aicarmine_symbol_rag_health | Symbol RAG |
| 19 | aicarmine-context-compressor | 5 | aicarmine_context_compressor_health | Context compression |
| 20 | aicarmine-code-architect | 7 | aicarmine_code_architect_health | Architecture analysis |
| 21 | aicarmine-test-coverage | 6 | aicarmine_test_coverage_health | Test coverage |
| 22 | aicarmine-performance-profiling | 6 | aicarmine_performance_profiling_health | Performance profiling |
| 23 | aicarmine-api-documentation | 6 | aicarmine_api_documentation_health | API documentation |
| 24 | aicarmine-lifecycle | 5 | aicarmine_lifecycle_deprecation_scan | Lifecycle management |

**Total tools across all servers: ~150+**

### Probed Servers (12 from codex-ops inventory)

All 12 probed servers returned healthy status:
- aicarmine_agentic_loop_client ✓ (7 tools)
- aicarmine_git_readonly ✓ (6 tools)
- aicarmine_job_artifact ✓ (9 tools)
- aicarmine_job_view ✓ (8 tools)
- aicarmine_local_subagent ✓ (3 tools)
- aicarmine_project_memory ✓ (7 tools)
- aicarmine_rag ✓ (3 tools)
- aicarmine_repo_code ✓ (5 tools)
- aicarmine_repo_search_det ✓ (8 tools)
- aicarmine_repo_state ✓ (3 tools)
- aicarmine_repo_validate ✓ (9 tools)
- aicarmine_sqlite_readonly ✓ (4 tools)

---

## 2. Skills Inventory

### Documented Skills (19 total)

| # | Skill Name | Domain | File Location |
|---|-----------|--------|---------------|
| 1 | codedoctor | Forensic code audit | .clinerules/codedoctor.md |
| 2 | codedoctorskillquantumprequantumengineeringedition | Quantum code audit | .clinerules/codedoctorskillquantumprequantumengineeringedition.md |
| 3 | coderefactor | Safe code refactoring | .clinerules/coderefactor.md |
| 4 | debugquantum | Python + Quantum debugging | .clinerules/debugquantum.md |
| 5 | documentation | Technical documentation | .clinerules/documentation.md |
| 6 | documentationskillquantuprequantumengineeringedition | Quantum documentation | .clinerules/documentationskillquantuprequantumengineeringedition.md |
| 7 | gitmaster | Advanced Git operations | .clinerules/gitmaster.md |
| 8 | gitmasterskillquantumprequantumengineeringedition | Quantum Git operations | .clinerules/gitmasterskillquantumprequantumengineeringedition.md |
| 9 | html-python | Web development (quantum extended) | .clinerules/html-python.md |
| 10 | orchestrator | Large-scale orchestration | .clinerules/orchestrator.md |
| 11 | orchestratorskillquantumprequantumengineeringedition | Quantum orchestration | .clinerules/orchestratorskillquantumprequantumengineeringedition.md |
| 12 | pythoexpertskillquantum | Python + Quantum dev | .clinerules/pythoexpertskillquantum.md |
| 13 | pythonexpert | Python development | .clinerules/pythonexpert.md |
| 14 | softwarearchitect | System architecture | .clinerules/softwarearchitect.md |
| 15 | softwarearchitectskillquantumprequantumengineeringedition | Quantum architecture | .clinerules/softwarearchitectskillquantumprequantumengineeringedition.md |
| 16 | suitetestantiregresssion | Testing and anti-regression | .clinerules/suitetestantiregresssion.md |
| 17 | systemadmin | System administration | .clinerules/systemadmin.md |
| 18 | systemadminquantumservicemanagement | Quantum service admin | .clinerules/systemadminquantumservicemanagement.md |
| 19 | testing | Test expertise | .clinerules/testing.md |

### Skill Activation Patterns

Base skills → Quantum extensions:
- codedoctor → codedoctorskillquantumprequantumengineeringedition
- documentation → documentationskillquantuprequantumengineeringedition
- gitmaster → gitmasterskillquantumprequantumengineeringedition
- orchestrator → orchestratorskillquantumprequantumengineeringedition
- pythonexpert → pythoexpertskillquantum
- softwarearchitect → softwarearchitectskillquantumprequantumengineeringedition
- systemadmin → systemadminquantumservicemanagement

---

## 3. AGENTS.md Contracts

### Root AGENTS.md
- Global evidence-first agent instructions
- Instruction precedence hierarchy (6 levels)
- General operating method (symptom→evidence→cause→fix→verify)
- Repository startup protocol
- AICarmine repository routing rules
- Tool and fallback discipline
- Change discipline
- Test and probe discipline
- Safety boundaries
- Windows defaults
- User-level CLI surface documentation

### Nested AGENTS.md Files
1. `agentic_loop_logc_app/AGENTS.md` - RAG data query agent rules
2. `codex_ollama_bridge_applied/AGENTS.md` - Codex local agent rules

---

## 4. Hook System

### Hook Types (.clinerules/hooks/)

| Hook | File | Purpose |
|------|------|---------|
| TaskStart | TaskStart.ps1 | Task bootstrap, contract probe |
| PreToolUse | PreToolUse.ps1 | Pre-tool validation |
| PostCompact | PostCompact.ps1 | Post-compact cleanup |
| UserPromptSubmit | UserPromptSubmit.ps1 | Prompt submission handling |

### Hook Library
- `lib/aicarmine_cline_contract_probe.ps1` - Contract shape analysis, SHA256 hashing, structured metadata persistence
- Hooks are fail-open (failures don't affect Cline behavior)

---

## 5. .clinerules Rules

### Active Rules
- `00-aicarmine-mcp-first.md` - MCP-first operating rule for C:\Users\carmi\AI workspace
- State mutation boundaries
- Patch boundary rules
- Windows boundary assumptions

---

## 6. Identified Gaps

### Critical Gaps

| Gap | Impact | Severity |
|-----|--------|----------|
| No centralized MCP health dashboard | Cannot see aggregate system status at a glance | High |
| Manual skill activation required | Skills must be explicitly loaded per task | Medium |
| No skill-to-MCP-tool mapping | Unclear which tools each skill prefers | Medium |
| No AGENTS.md version tracking | Cannot detect stale contract documents | Medium |
| No cross-server orchestration tool | Multi-server workflows not atomically coordinated | High |
| Hook integration testing incomplete | Hook behavior not systematically validated | Medium |
| No context window budget tracker | Context usage not proactively managed | Medium |
| Performance benchmarking absent | Tool latency not measured or optimized | Low |
| Error recovery patterns undefined | Standardized recovery workflows missing | Medium |
| MCP dependency graph missing | Server dependencies not visualized | Low |

---

## 7. Improvement Proposals

### Priority 1: Critical Improvements

#### 7.1 Centralized MCP Health Aggregator
**Proposal**: Create a single endpoint that aggregates health status from all 24 MCP servers.

```markdown
Current state: Each server has individual health tools, no aggregate view.
Target: /health/aggregate returns JSON with all server statuses, tool counts, and overall system health score.
Benefit: Instant system-wide status awareness.
```

#### 7.2 Skill-to-MCP-Tool Mapping Document
**Proposal**: Create explicit mapping between each skill and its preferred MCP tools.

```markdown
Current state: Skills describe capabilities but don't reference specific MCP tools.
Target: skills_mcp_mapping.md with tables like:
| Skill | Primary MCP Tools | Fallback MCP Tools | Native Tools |
|------|-------------------|-------------------|-------------|
| codedoctor | aicarmine_repo_validate/*, aicarmine_git_readonly/* | search_files, read_file | - |
Benefit: Clearer tool selection guidance.
```

#### 7.3 Cross-Server Orchestration Pattern
**Proposal**: Define patterns for coordinating multiple MCP servers in atomic workflows.

```markdown
Current state: Each server operates independently.
Target: Document orchestration patterns like:
- validate → edit → validate cycle
- search → analyze → propose workflow
- RAG index → query → synthesize pipeline
Benefit: Reliable multi-step operations.
```

### Priority 2: Important Improvements

#### 7.4 AGENTS.md Version Tracking System
**Proposal**: Track versions of all AGENTS.md files and detect staleness.

```markdown
Current state: No version tracking.
Target: metadata/agents_versions.json with:
{
  "root_AGENTS.md": {"last_modified": "...", "version": "1.2"},
  "agentic_loop_logc_app/AGENTS.md": {...}
}
Benefit: Detect when contracts need updating.
```

#### 7.5 Hook Integration Test Suite
**Proposal**: Create systematic tests for hook behavior.

```markdown
Current state: Hooks exist but no comprehensive test coverage.
Target: .clinerules/hooks/tests/ with PowerShell test scripts validating:
- TaskStart bootstrap output format
- PreToolUse validation logic
- PostCompact cleanup behavior
- UserPromptSubmit handling
Benefit: Reliable hook behavior.
```

#### 7.6 Context Window Budget Tracker
**Proposal**: Proactively manage context window usage across operations.

```markdown
Current state: aicarmine_context_compressor exists but no budget tracking.
Target: Integrate budget tracking with:
- Current context usage %
- Estimated tokens per operation
- Automatic compression triggers
Benefit: Prevent context overflow.
```

### Priority 3: Nice-to-Have Improvements

#### 7.7 Performance Benchmarking Framework
**Proposal**: Measure and optimize MCP tool latency.

```markdown
Current state: No performance measurement.
Target: benchmarks/mcp_tools.json with:
{
  "aicarmine_repo_search_det/aicarmine_repo_search_rg": {"avg_ms": 150, "p99_ms": 400}
}
Benefit: Identify slow operations.
```

#### 7.8 Error Recovery Standardization
**Proposal**: Define standardized error recovery workflows.

```markdown
Current state: Error handling is ad hoc.
Target: error_recovery_protocols.md with patterns like:
- Tool failure → retry ×2 → fallback → report
- Validation failure → inspect diff → adjust → revalidate
Benefit: Consistent error handling.
```

#### 7.9 MCP Dependency Visualization
**Proposal**: Create visual representation of server dependencies.

```markdown
Current state: Dependencies implicit.
Target: diagrams/mcp_dependencies.svg showing:
- Which servers depend on which
- Data flow between servers
- Critical path servers
Benefit: Understand system architecture.
```

#### 7.10 Skill Activation Recommendation Engine
**Proposal**: Auto-suggest skills based on task description.

```markdown
Current state: Skills manually activated.
Target: Task analysis that recommends:
"Task involves code review → activate codedoctor + testing"
Benefit: Faster skill selection.
```

---

## 8. System Strengths

### What Works Well

1. **Comprehensive MCP Coverage**: 24 servers with ~150 tools cover all major operations
2. **Read-Only Safety**: Many servers enforce read-only constraints for safety
3. **Windows-First Design**: PowerShell-native hooks and commands
4. **Evidence-First Methodology**: AGENTS.md enforces symptom→evidence→cause→fix chain
5. **Skill Extension Pattern**: Base skills → quantum extensions work well
6. **Hook Fail-Open Design**: Hooks don't break Cline if they fail
7. **Contract-Based Operations**: Clear boundaries between components
8. **Project Memory System**: SQLite-based persistent memory with write guards

---

## 9. Tool Usage Statistics

### Most Used MCP Servers (by tool count)
1. aicarmine-repo-validate: 9 tools
2. aicarmine-job-artifact: 9 tools
3. aicarmine-repo-search-det: 8 tools
4. aicarmine-job-view: 8 tools
5. aicarmine-network-monitor: 8 tools

### Least Used MCP Servers (health check missing)
1. aicarmine-rag: No health tool exposed
2. aicarmine-rag-router: Implicit health only

---

## 10. Recommendations Summary

| Priority | Improvement | Effort | Impact |
|----------|------------|--------|--------|
| P1 | Centralized MCP health dashboard | Medium | High |
| P1 | Skill-to-MCP-tool mapping | Low | Medium |
| P1 | Cross-server orchestration patterns | Medium | High |
| P2 | AGENTS.md version tracking | Low | Medium |
| P2 | Hook integration test suite | Medium | Medium |
| P2 | Context window budget tracker | Low | Medium |
| P3 | Performance benchmarking | Medium | Low |
| P3 | Error recovery standardization | Low | Medium |
| P3 | MCP dependency visualization | Low | Low |
| P3 | Skill activation recommendations | Medium | Low |

---

## 11. Next Steps

1. Create centralized health aggregation endpoint
2. Build skills_mcp_mapping.md document
3. Document cross-server orchestration patterns
4. Add version tracking to AGENTS.md metadata
5. Write hook integration tests

---

*Audit generated: 2026-08-15*
*System version: main@fb412fe*
*Python version: 3.14.7*