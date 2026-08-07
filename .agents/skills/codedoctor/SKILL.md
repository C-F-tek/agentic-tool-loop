# Code Doctor Skill — Quantum & Pre-Quantum Engineering Edition

## Overview

This skill extends forensic code quality auditing into **quantum computing**, **pre-quantum engineering**, and **quantum-classical hybrid systems**. It covers quantum-specific quality gates, deterministic seed verification, shot budget validation, and MCP-first tool priority for all repository operations.

It is designed for:
- Auditing quantum circuit builder code quality
- Verifying deterministic seeding in quantum simulations
- Validating shot budget enforcement in quantum APIs
- MCP-first: all repo operations use MCP tools

---

## Core Principles

### Code Quality Audit
- Deterministic seeding verification in every quantum run
- Shot budget enforcement at API boundary
- State normalization checks before downstream processing
- Classical approximation labeling verification
- MCP-first: all repo operations use MCP tools

### Quantum-Specific Quality Patterns
- Seed reproducibility: Every quantum run records its seed
- Shot minimum: Minimum 100 shots enforced
- State normalization: `sum(probabilities) ≈ 1.0` within 1e-6 tolerance
- Classical labeling: Clearly distinguish classical simulation from quantum execution
- MCP-first: all file reads use `aicarmine_repo_read`, all writes use `aicarmine_repo_apply_patch`

---

## Code Quality Patterns for Quantum Projects

### 1. Deterministic Seed Audit
```python
# Quality check: Verify seed is recorded in every quantum run
def audit_seed_recording(module_path: str) -> dict:
    """Audit that every quantum run records its seed."""
    issues = []
    
    # Read module using MCP-first approach
    code = read_module_mcp_first(module_path)
    
    # Check for seed recording
    if "seed" not in code or "seed_simulator" not in code:
        issues.append({
            "severity": "error",
            "message": "Quantum run does not record seed value",
            "module": module_path,
            "recommendation": "Add seed parameter to quantum run function"
        })
    
    return {"issues": issues, "passed": len(issues) == 0}
```

### 2. Shot Budget Enforcement Audit
```python
# Quality check: Verify minimum shot count is enforced
def audit_shot_budget(module_path: str) -> dict:
    """Audit that minimum shot count is enforced."""
    issues = []
    
    MIN_SHOTS = 100
    
    # Read module using MCP-first approach
    code = read_module_mcp_first(module_path)
    
    # Check for shot validation
    if "shots" not in code or "MIN_SHOTS" not in code:
        issues.append({
            "severity": "error",
            "message": "Shot budget not enforced",
            "module": module_path,
            "recommendation": "Add minimum shot count validation"
        })
    
    return {"issues": issues, "passed": len(issues) == 0}
```

### 3. State Normalization Audit
```python
# Quality check: Verify statevector normalization
def audit_state_normalization(module_path: str) -> dict:
    """Audit that statevector normalization is verified."""
    issues = []
    
    # Read module using MCP-first approach
    code = read_module_mcp_first(module_path)
    
    # Check for normalization verification
    if "normalize" not in code and "sum(probabilities)" not in code:
        issues.append({
            "severity": "warning",
            "message": "Statevector normalization not verified",
            "module": module_path,
            "recommendation": "Add statevector normalization check"
        })
    
    return {"issues": issues, "passed": len(issues) == 0}
```

---

## MCP-First Enforcement Layer

This skill operates under aggressive MCP-first tool priority. All repository operations MUST use MCP tools over native Cline tools.

### Tool Priority for Code Doctor Tasks

| Operation | MCP Tool (prefer) | Native Cline tool (avoid) |
|-----------|-------------------|--------------------------|
| Read code file | `aicarmine_repo_read` | `read_file` |
| Search code patterns | `aicarmine_repo_search` / `aicarmine_repo_search_fd` | `search_files` |
| List code files | `aicarmine_repo_list_files` | `list_files` |
| Git history of code | `aicarmine_git_readonly_log` | `execute_command git` |
| Validate Python code | `aicarmine_repo_validate_ruff` | `execute_command ruff` |
| Apply fixes | `aicarmine_repo_apply_patch` / `aicarmine_repo_code_apply_patch` | `write_to_file` / `replace_in_file` |

### Code Doctor Classification Rules

- **SeedAudit**: Queries containing `seed`, `reproducibility`, `deterministic` → Use `aicarmine_repo_read` for seed recording code
- **ShotBudgetAudit**: Queries containing `shot`, `budget`, `minimum`, `enforcement` → Use `aicarmine_repo_read` for shot validation code
- **StateNormalizationAudit**: Queries containing `statevector`, `normalization`, `probability` → Use `aicarmine_repo_read` for state validation code
- **ClassicalLabelingAudit**: Queries containing `classical`, `approximation`, `labeling`, `simulation` → Use `aicarmine_repo_read` for classical labeling code

### MCP-First Constraints for Code Doctor Tasks

1. **Never use native `read_file`** for code files — always use `aicarmine_repo_read` with bounded `max_chars`
2. **Never use native `write_to_file`/`replace_in_file`** for code fixes — always use `aicarmine_repo_apply_patch` or `aicarmine_repo_code_apply_patch`
3. **Always verify deterministic seeding** in every quantum run
4. **Always enforce shot budgets** at API boundary
5. **Always verify state normalization** before downstream processing
6. **Always label classical approximation** — distinguish from quantum execution

---

## Best Practices

### Quantum-Specific Code Quality
1. **Seed reproducibility**: Verify every quantum run records its seed value
2. **Shot budget enforcement**: Verify minimum 100 shots enforced at API boundary
3. **State normalization**: Verify `sum(probabilities) ≈ 1.0` within 1e-6 tolerance
4. **Classical labeling**: Verify classical approximations are clearly labeled
5. **Error handling**: Verify consistent exception types for quantum failures

### Pre-Quantum Code Quality
1. **Performance bounds**: Verify classical simulation stays within limits (50 samples × 10 qubits)
2. **No false claims**: Verify classical approximation is never presented as quantum execution
3. **Clear labeling**: Verify explicit labeling of classical approximation results
4. **Sample limits**: Verify sample count bounds in classical approximation

### Code Quality Structure
1. **Seed audit**: Check every quantum run function for seed recording
2. **Shot budget audit**: Check API boundary functions for shot validation
3. **State normalization audit**: Check statevector processing functions for normalization verification
4. **Classical labeling audit**: Check classical approximation functions for explicit labeling
5. **Error handling audit**: Check quantum failure handling for consistent exception types

---

## File Structure Convention

```
project/
├── quality/
│   ├── __init__.py
│   ├── seed_audit.py          # Deterministic seed verification
│   ├── shot_budget_audit.py   # Shot budget enforcement verification
│   ├── state_normalization_audit.py  # State normalization verification
│   └── classical_labeling_audit.py     # Classical approximation labeling verification
├── quantum/                    # Quantum execution layer
│   ├── __init__.py
│   ├── backends.py             # QuantumBackend interface + implementations
│   ├── circuits.py             # Circuit builders
│   └── validators.py           # State/count validation
├── classical/                  # Classical preprocessing/postprocessing
│   ├── __init__.py
│   ├── preprocessors.py        # Input transformation
│   └── postprocessors.py       # Output optimization
└── requirements.txt
    # fastapi, qiskit, qiskit-aer, numpy, scipy
```

---

## Error Handling Contract

| Error Type | Code Doctor Response | Action |
|-----------|--------------|---------------|
| SDK unavailable | Document classical fallback | Run `classical_approximate_quantum()` |
| Circuit build fail | Document error message format | Log traceback, return error dict |
| Job timeout | Document timeout handling | Cancel job, offer reduced shots |
| Invalid qubit count | Document input validation | Validate input before circuit creation |
| Statevector too large | Document cap and warning | Cap at 20 qubits, warn user |

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
- Code Quality: Forensic auditing, quality gates
- MCP-first: All repo operations use MCP tools