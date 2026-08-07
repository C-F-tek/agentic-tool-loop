# Code Refactor Skill — Quantum & Pre-Quantum Engineering Edition

## Overview

This skill extends safe code refactoring into **quantum computing**, **pre-quantum engineering**, and **quantum-classical hybrid systems**. It covers quantum-safe transformations, deterministic seed preservation, shot budget consistency, and MCP-first tool priority for all repository operations.

It is designed for:
- Refactoring quantum circuit builder code safely
- Preserving deterministic seeding across refactoring
- Maintaining shot budget enforcement during module changes
- MCP-first: all repo operations use MCP tools

---

## Core Principles

### Safe Refactoring
- Preserve deterministic seeding across refactoring
- Maintain shot budget enforcement at API boundary
- Verify state normalization after refactoring
- Keep classical approximation labeling intact
- MCP-first: all repo operations use MCP tools

### Quantum-Specific Refactoring Patterns
- Seed preservation: Deterministic seeds must survive refactoring
- Shot budget consistency: Minimum 100 shots enforced after refactoring
- State normalization: `sum(probabilities) ≈ 1.0` within 1e-6 tolerance after refactoring
- Classical labeling: Clear distinction between classical simulation and quantum execution preserved
- MCP-first: all file reads use `aicarmine_repo_read`, all writes use `aicarmine_repo_apply_patch`

---

## Code Refactoring Patterns for Quantum Projects

### 1. Safe Quantum Circuit Builder Refactoring
```python
# Before refactoring
def build_bell_state() -> QuantumCircuit:
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    return qc

# After refactoring (preserving seed/shots metadata)
def build_bell_state(config: CircuitConfig) -> QuantumCircuit:
    """Build bell state circuit with configurable parameters."""
    qc = QuantumCircuit(config.num_qubits)
    qc.h(0)
    qc.cx(0, 1)
    
    # Preserve seed/shots metadata in config
    config.seed = 42
    config.shots = 1024
    
    return qc
```

### 2. Shot Budget Enforcement Preservation
```python
# Before refactoring
def run_quantum_job(shots: int = 1024) -> dict:
    return {"shots": shots}

# After refactoring (preserving minimum enforcement)
def run_quantum_job(shots: int = 1024) -> dict:
    MIN_SHOTS = 100
    if shots < MIN_SHOTS:
        raise ValueError(f"Shots {shots} below minimum {MIN_SHOTS}")
    return {"shots": shots, "valid": True}
```

### 3. Classical Approximation Labeling Preservation
```python
# Before refactoring
def classical_approx(num_qubits: int) -> dict:
    return {"samples": [], "num_qubits": num_qubits}

# After refactoring (preserving labeling)
def classical_approx(num_qubits: int) -> dict:
    """Classical approximation of quantum behavior.
    
    This is NOT quantum execution. It is a classical simulation.
    """
    return {
        "samples": [],
        "num_qubits": num_qubits,
        "method": "classical_approx",
        "is_quantum": False  # Explicit labeling preserved
    }
```

---

## MCP-First Enforcement Layer

This skill operates under aggressive MCP-first tool priority. All repository operations MUST use MCP tools over native Cline tools.

### Tool Priority for Code Refactor Tasks

| Operation | MCP Tool (prefer) | Native Cline tool (avoid) |
|-----------|-------------------|--------------------------|
| Read code file | `aicarmine_repo_read` | `read_file` |
| Search code patterns | `aicarmine_repo_search` / `aicarmine_repo_search_fd` | `search_files` |
| List code files | `aicarmine_repo_list_files` | `list_files` |
| Git history of code | `aicarmine_git_readonly_log` | `execute_command git` |
| Apply refactoring changes | `aicarmine_repo_apply_patch` / `aicarmine_repo_code_apply_patch` | `write_to_file` / `replace_in_file` |

### Code Refactor Classification Rules

- **CircuitBuilderRefactor**: Queries containing `circuit`, `builder`, `gate`, `quantum` → Use `aicarmine_repo_read` for circuit builder code
- **ShotBudgetRefactor**: Queries containing `shot`, `budget`, `minimum`, `enforcement` → Use `aicarmine_repo_read` for shot validation code
- **StateNormalizationRefactor**: Queries containing `statevector`, `normalization`, `probability` → Use `aicarmine_repo_read` for state validation code
- **ClassicalLabelingRefactor**: Queries containing `classical`, `approximation`, `labeling`, `simulation` → Use `aicarmine_repo_read` for classical labeling code

### MCP-First Constraints for Code Refactor Tasks

1. **Never use native `read_file`** for code files — always use `aicarmine_repo_read` with bounded `max_chars`
2. **Never use native `write_to_file`/`replace_in_file`** for refactoring changes — always use `aicarmine_repo_apply_patch` or `aicarmine_repo_code_apply_patch`
3. **Always preserve deterministic seeding** across refactoring
4. **Always maintain shot budget enforcement** at API boundary
5. **Always verify state normalization** after refactoring
6. **Always preserve classical approximation labeling** — distinguish from quantum execution

---

## Best Practices

### Quantum-Specific Refactoring
1. **Seed preservation**: Verify deterministic seeds survive refactoring
2. **Shot budget consistency**: Verify minimum 100 shots enforced after refactoring
3. **State normalization**: Verify `sum(probabilities) ≈ 1.0` within 1e-6 tolerance after refactoring
4. **Classical labeling**: Verify classical approximations are clearly labeled after refactoring
5. **Error handling**: Verify consistent exception types for quantum failures after refactoring

### Pre-Quantum Refactoring
1. **Performance bounds**: Verify classical simulation stays within limits (50 samples × 10 qubits) after refactoring
2. **No false claims**: Verify classical approximation is never presented as quantum execution after refactoring
3. **Clear labeling**: Verify explicit labeling of classical approximation results preserved after refactoring
4. **Sample limits**: Verify sample count bounds in classical approximation preserved after refactoring

### Refactoring Structure
1. **Circuit builder refactoring**: Preserve seed/shots metadata in circuit config
2. **Shot budget refactoring**: Maintain minimum enforcement at API boundary
3. **State normalization refactoring**: Preserve normalization verification logic
4. **Classical labeling refactoring**: Preserve explicit labeling of classical approximation
5. **Error handling refactoring**: Preserve consistent exception types for quantum failures

---

## File Structure Convention

```
project/
├── refactor/
│   ├── __init__.py
│   ├── circuit_builder_refactor.py    # Circuit builder safe refactoring
│   ├── shot_budget_refactor.py        # Shot budget consistency preservation
│   ├── state_normalization_refactor.py   # State normalization preservation
│   └── classical_labeling_refactor.py     # Classical approximation labeling preservation
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

| Error Type | Code Refactor Response | Action |
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
- Code Refactoring: Safe transformations, preservation patterns
