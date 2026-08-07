# Git Master Skill — Quantum & Pre-Quantum Engineering Edition

## Overview

This skill extends Git operations into **quantum computing**, **pre-quantum engineering**, and **quantum-classical hybrid systems**. It covers experiment branch strategies, seed-based commit organization, quantum SDK version tracking, and MCP-first tool priority for all repository operations.

It is designed for:
- Managing quantum experiment branches with deterministic seeds
- Tracking quantum SDK version changes across commits
- Organizing classical approximation vs quantum execution code
- MCP-first: all repo operations use MCP tools

---

## Core Principles

### Git Strategy
- Experiment branches named with seed/shots metadata
- Quantum SDK version tracked in commit messages
- Classical approximation code separated from quantum execution
- Deterministic seeding preserved across branches
- MCP-first: all repo operations use MCP tools

### Quantum-Specific Git Patterns
- Branch naming: `experiment/bell-state-seed42-shots1024`
- Commit messages: Include seed, shots, backend metadata
- Tags: Mark quantum SDK version milestones
- Cherry-pick: Select specific experiment commits

---

## Git Patterns for Quantum Projects

### 1. Experiment Branch Naming Convention
```bash
# Quantum experiment branches
git checkout -b experiment/bell-state-seed42-shots1024
git checkout -b experiment/vqe-h2-seed99-shots2048
git checkout -b experiment/qnn-circuit-depth50-seed7-shots512

# Classical approximation branches
git checkout -b classical-approx/qubit3-depth10
git checkout -b classical-approx/hybrid-vqe-pipeline

# SDK version branches
git checkout -b sdk/qiskit-1.0.0
git checkout -b sdk/cirq-1.3.0
git checkout -b sdk/pennylane-0.35.0
```

### 2. Commit Message Template for Quantum Experiments
```markdown
feat(quantum): add bell state circuit builder

- Implement H gate on qubit 0, CX(0,1) for entanglement
- Deterministic seed: 42, shots: 1024
- Backend: qiskit-aer/statevector_simulator
- Circuit depth: 2, num_qubits: 2

MCP-first: Used aicarmine_repo_read for circuit definition files.
```

### 3. Tagging Quantum SDK Versions
```bash
# Tag quantum SDK milestones
git tag -a v1.0.0-qiskit -m "Quantum SDK milestone: Qiskit 1.0.0 integration"
git tag -a v1.1.0-classical-approx -m "Classical approximation layer added"
git tag -a v1.2.0-hybrid-pipeline -m "Hybrid classical-quantum pipeline introduced"
```

---

## MCP-First Enforcement Layer

This skill operates under aggressive MCP-first tool priority. All repository operations MUST use MCP tools over native Cline tools.

### Tool Priority for Git Tasks

| Operation | MCP Tool (prefer) | Native Cline tool (avoid) |
|-----------|-------------------|--------------------------|
| Read git log | `aicarmine_git_readonly_log` | `execute_command git log` |
| Read git diff | `aicarmine_git_readonly_diff` | `execute_command git diff` |
| Read commit | `aicarmine_git_readonly_show` | `execute_command git show` |
| List tracked files | `aicarmine_repo_list_files` | `list_files` |
| Search repo | `aicarmine_repo_search` / `aicarmine_repo_search_fd` | `search_files` |
| Apply patches | `aicarmine_repo_apply_patch` / `aicarmine_repo_code_apply_patch` | `write_to_file` / `replace_in_file` |

### Git Classification Rules

- **ExperimentBranch**: Queries containing `experiment`, `branch`, `seed`, `shots` → Use `aicarmine_git_readonly_log` for experiment history
- **SDKVersion**: Queries containing `sdk`, `version`, `qiskit`, `cirq`, `pennylane` → Use `aicarmine_git_readonly_log` for SDK version tracking
- **CommitMetadata**: Queries containing `commit`, `message`, `metadata`, `seed` → Use `aicarmine_git_readonly_show` for commit details
- **CherryPick**: Queries containing `cherry-pick`, `select`, `specific` → Use `aicarmine_git_readonly_log` for commit selection

### MCP-First Constraints for Git Tasks

1. **Never use native `execute_command git`** for git operations — always use `aicarmine_git_readonly_*` MCP tools
2. **Never use native `read_file`** for git-related files — always use `aicarmine_repo_read`
3. **Never use native `write_to_file`/`replace_in_file`** for git configuration changes — always use `aicarmine_repo_apply_patch` or `aicarmine_repo_code_apply_patch`
4. **Always include seed/shots/backend in commit messages** for quantum experiments
5. **Always tag quantum SDK version milestones**
6. **Always separate classical approximation code from quantum execution code** in branches

---

## Best Practices

### Quantum-Specific Git Practices
1. **Experiment branches**: Name branches with seed/shots metadata for reproducibility
2. **Commit messages**: Include seed, shots, backend metadata in every quantum experiment commit
3. **SDK version tags**: Tag quantum SDK version milestones for tracking
4. **Branch separation**: Keep classical approximation code separate from quantum execution
5. **Cherry-pick experiments**: Select specific experiment commits for integration

### Pre-Quantum Git Practices
1. **Classical approximation branches**: Clearly label classical simulation vs quantum execution
2. **No false claims**: Never commit classical approximation as quantum execution
3. **Clear labeling**: Mark classical approximation results explicitly in commit messages
4. **Sample limits**: Document sample count bounds in commit descriptions

### Git Structure
1. **Main branch**: Stable quantum-classical hybrid system
2. **Experiment branches**: Individual quantum experiments with deterministic seeds
3. **SDK version branches**: Track quantum SDK version changes
4. **Classical approximation branches**: Classical fallback code
5. **Release tags**: Mark production-ready quantum-classical systems

---

## File Structure Convention

```
project/
├── .git/
├── quantum/                    # Quantum execution layer
│   ├── __init__.py
│   ├── backends.py             # QuantumBackend interface + implementations
│   ├── circuits.py             # Circuit builders
│   └── validators.py           # State/count validation
├── classical/                  # Classical preprocessing/postprocessing
│   ├── __init__.py
│   ├── preprocessors.py        # Input transformation
│   └── postprocessors.py       # Output optimization
├── pipeline/                   # Hybrid workflow orchestration
│   ├── __init__.py
│   └── pipeline.py             # HybridWorkflowPipeline
├── api/                        # FastAPI endpoints
│   ├── __init__.py
│   └── endpoints.py            # REST API
└── config/                     # Configuration
    ├── __init__.py
    └── settings.py             # Shot budgets, seeds, backend selection
```

---

## Error Handling Contract

| Error Type | Git Response | Action |
|-----------|--------------|---------------|
| SDK unavailable | Document classical fallback in commit | Run `classical_approximate_quantum()` |
| Circuit build fail | Document error message format in commit | Log traceback, return error dict |
| Job timeout | Document timeout handling in commit | Cancel job, offer reduced shots |
| Invalid qubit count | Document input validation in commit | Validate input before circuit creation |
| Statevector too large | Document cap and warning in commit | Cap at 20 qubits, warn user |

---

## Quality Gates

1. **Circuit depth check**: Reject commits with circuits depth > 1000 without warning
2. **Shot minimum**: Enforce minimum 100 shots for statistical validity in commit metadata
3. **Normalization verify**: Assert `sum(probabilities) ≈ 1.0` within 1e-6 tolerance in commit messages
4. **Seed reproducibility**: Every quantum run must record its seed in commit metadata
5. **HTML validation**: All templates pass HTML5 validator; no inline scripts without CSP nonce

---

## Extended References

- Qiskit Documentation: https://qiskit.org/documentation/
- Cirq Guide: https://quantumai.google/cirq
- PennyLane API: https://pennylane.ai/documentation/
- Git Flow: https://nvie.com/posts/a-git-branching-model/
- Conventional Commits: https://www.conventionalcommits.org/
- MCP-first: All git operations use MCP tools