# Orchestrator Skill — Quantum & Pre-Quantum Engineering Edition

## Overview

This skill extends orchestration expertise into **quantum computing**, **pre-quantum engineering**, and **quantum-classical hybrid systems**. It covers large-scale software operations, multi-module refactoring campaigns, quantum experiment pipeline coordination, and MCP-first tool priority for all repository operations.

It is designed for:
- Coordinating classical preprocessing → quantum execution → classical postprocessing pipelines
- Managing quantum experiment workflows across multiple modules
- Orchestrating large-scale refactoring of quantum SDK abstraction layers
- MCP-first: all repo operations use MCP tools

---

## Core Principles

### Orchestration Design
- Leaf modules first, then dependent modules, finally top-level
- Track all interface changes across module boundaries
- Verify compilation/runtime at each phase boundary
- Roll back if critical failures detected
- MCP-first: all repo operations use MCP tools

### Quantum Pipeline Orchestration
- Classical preprocessing → Quantum execution → Classical postprocessing pipeline coordination
- Quantum SDK abstraction layer updates propagated consistently
- Deterministic seeding preserved across pipeline stages
- Shot budget enforcement maintained at API boundaries
- MCP-first: all file reads use `aicarmine_repo_read`, all writes use `aicarmine_repo_apply_patch`

---

## Orchestration Patterns

### 1. Large-Scale Refactoring Orchestration
```python
# Phase 1: Leaf modules (quantum/backends.py)
# - Update QuantumBackend interface
# - Verify tests pass
# - Commit intermediate state

# Phase 2: Dependent modules (quantum/circuits.py, quantum/validators.py)
# - Update circuit builders to use new backend interface
# - Verify tests pass
# - Commit intermediate state

# Phase 3: Top-level modules (pipeline/pipeline.py, api/endpoints.py)
# - Update pipeline orchestration to use new backend
# - Verify integration tests pass
# - Final commit
```

### 2. Quantum Experiment Pipeline Coordination
```python
class ExperimentPipelineOrchestrator:
    """Coordinates quantum experiment pipelines."""
    
    def __init__(self):
        self.stages = []
        self.metadata = {}
    
    def add_stage(self, stage_name: str, module_path: str, tool: str):
        """Add a pipeline stage."""
        self.stages.append({
            "name": stage_name,
            "module": module_path,
            "tool": tool,
            "status": "pending"
        })
    
    async def execute_pipeline(self) -> dict:
        """Execute the full experiment pipeline."""
        results = {}
        
        for stage in self.stages:
            # Read stage code via MCP
            code = await self.read_module(stage["module"])
            
            # Execute stage
            result = await self.execute_stage(code, stage["tool"])
            
            # Record results
            results[stage["name"]] = result
            stage["status"] = "completed"
        
        return results
    
    async def read_module(self, module_path: str) -> str:
        """Read module code using MCP-first approach."""
        # Use aicarmine_repo_read instead of read_file
        pass
    
    async def execute_stage(self, code: str, tool: str) -> dict:
        """Execute a pipeline stage."""
        pass
```

### 3. Multi-Module Dependency Tracking
```python
class ModuleDependencyGraph:
    """Tracks dependencies between modules for orchestration."""
    
    def __init__(self):
        self.modules = {}
        self.dependencies = {}
    
    def add_module(self, name: str, path: str):
        self.modules[name] = path
        self.dependencies[name] = []
    
    def add_dependency(self, parent: str, child: str):
        self.dependencies[parent].append(child)
    
    def get_execution_order(self) -> list:
        """Get topological execution order (leaf modules first)."""
        visited = set()
        order = []
        
        def visit(module):
            if module in visited:
                return
            visited.add(module)
            for dep in self.dependencies.get(module, []):
                visit(dep)
            order.append(module)
        
        for module in self.modules:
            visit(module)
        
        return order
```

---

## MCP-First Enforcement Layer

This skill operates under aggressive MCP-first tool priority. All repository operations MUST use MCP tools over native Cline tools.

### Tool Priority for Orchestration Tasks

| Operation | MCP Tool (prefer) | Native Cline tool (avoid) |
|-----------|-------------------|--------------------------|
| Read module file | `aicarmine_repo_read` | `read_file` |
| Search module patterns | `aicarmine_repo_search` / `aicarmine_repo_search_fd` | `search_files` |
| List module files | `aicarmine_repo_list_files` | `list_files` |
| Git history of changes | `aicarmine_git_readonly_log` | `execute_command git` |
| Apply orchestration changes | `aicarmine_repo_apply_patch` / `aicarmine_repo_code_apply_patch` | `write_to_file` / `replace_in_file` |

### Orchestration Classification Rules

- **LargeScaleRefactor**: Queries containing `refactor`, `migration`, `orchestrate`, `large-scale`, `multi-module` → Use `aicarmine_repo_tree` for structure mapping
- **PipelineCoordination**: Queries containing `pipeline`, `workflow`, `stage`, `phase` → Use `aicarmine_repo_read` for pipeline files
- **DependencyTracking**: Queries containing `dependency`, `graph`, `topological` → Use `aicarmine_repo_read` for dependency files
- **ExperimentOrchestration**: Queries containing `experiment`, `quantum`, `shots`, `seed` → Use `aicarmine_project_memory_search` for experiment metadata

### MCP-First Constraints for Orchestration Tasks

1. **Never use native `read_file`** for module files — always use `aicarmine_repo_read` with bounded `max_chars`
2. **Never use native `write_to_file`/`replace_in_file`** for orchestration changes — always use `aicarmine_repo_apply_patch` or `aicarmine_repo_code_apply_patch`
3. **Always abstract quantum SDK** — never couple classical code directly to Qiskit/Cirq
4. **Always enforce shot budgets** at API boundary
5. **Always seed deterministically** — record seeds in `aicarmine_project_memory_search`
6. **Always label classical approximation** — distinguish from quantum execution

---

## Best Practices

### Quantum-Specific Orchestration
1. **SDK abstraction**: Update `QuantumBackend` interface consistently across all modules
2. **Graceful degradation**: Ensure fallback paths work after orchestration changes
3. **Shot budget enforcement**: Maintain minimum 100 shots at API boundary after changes
4. **Deterministic seeding**: Preserve seed, shots, backend recording across pipeline stages
5. **State validation**: Verify statevector normalization after orchestration changes

### Pre-Quantum Orchestration
1. **Performance bounds**: Ensure classical simulation stays within limits (50 samples × 10 qubits)
2. **No false claims**: Ensure classical approximation is never presented as quantum execution
3. **Clear labeling**: Maintain explicit labeling of classical approximation results
4. **Sample limits**: Enforce sample count bounds after orchestration changes

### Orchestration Structure
1. **Leaf modules first**: Start with leaf modules, then dependent modules, finally top-level
2. **Interface tracking**: Track all interface changes across module boundaries
3. **Compilation verification**: Verify compilation/runtime at each phase boundary
4. **Rollback readiness**: Be prepared to roll back if critical failures detected
5. **Intermediate commits**: Commit intermediate state after each phase

---

## File Structure Convention

```
project/
├── classical/                    # Classical preprocessing/postprocessing
│   ├── __init__.py
│   ├── preprocessors.py
│   └── postprocessors.py
├── quantum/                      # Quantum execution layer
│   ├── __init__.py
│   ├── backends.py
│   ├── circuits.py
│   └── validators.py
├── pipeline/                     # Hybrid workflow orchestration
│   ├── __init__.py
│   └── pipeline.py
├── api/                          # FastAPI endpoints
│   ├── __init__.py
│   └── endpoints.py
├── config/                       # Configuration
│   ├── __init__.py
│   └── settings.py
└── requirements.txt
    # fastapi, qiskit, qiskit-aer, numpy, scipy
```

---

## Error Handling Contract

| Error Type | Orchestration Response | Action |
|-----------|--------------|---------------|
| SDK unavailable | Raise `QuantumSDKUnavailableError` | Fallback to ClassicalApproxBackend |
| Circuit build fail | Raise `CircuitBuildError` with traceback | Log traceback, return error dict |
| Job timeout | Raise `QuantumJobTimeoutError` | Cancel job, offer reduced shots |
| Invalid qubit count | Raise `InvalidQubitCountError` | Validate input before circuit creation |
| Statevector too large | Raise `StatevectorOverflowError` | Cap at 20 qubits, warn user |

---

## Quality Gates

1. **Circuit depth check**: Reject circuits with depth > 1000 without warning
2. **Shot minimum**: Enforce minimum 100 shots for statistical validity
3. **Normalization verify**: Assert `sum(probabilities) ≈ 1.0` within 1e-6 tolerance
4. **Seed reproducibility**: Every quantum run must record its seed
5. **HTML validation**: All templates pass HTML5 validator; no inline scripts without CSP nonce

---

## Extended References

- Qiskit Documentation: https://qiskit.org/documentation/
- Cirq Guide: https://quantumai.google/cirq
- PennyLane API: https://pennylane.ai/documentation/
- Orchestration Patterns: Topological sort, dependency graphs
- MCP-first: All repo operations use MCP tools