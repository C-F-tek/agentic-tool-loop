# Testing Skill — Quantum & Pre-Quantum Engineering Edition

## Overview

This skill extends test design and execution into **quantum computing**, **pre-quantum engineering**, and **quantum-classical hybrid systems**. It covers quantum-specific test strategies, deterministic seed verification, shot budget validation, and MCP-first tool priority for all repository operations.

It is designed for:
- Unit tests for quantum circuit builders
- Integration tests for async quantum job executors
- Property-based tests for statevector normalization
- Regression tests for classical approximation layers
- MCP-first: all file reads use `aicarmine_repo_read`, all writes use `aicarmine_repo_apply_patch`

---

## Core Principles

### Test Design
- Deterministic seeding: every quantum test uses fixed seeds
- Shot budget validation: minimum 100 shots enforced
- State normalization checks: tolerance 1e-6
- Classical approximation labeling: clearly distinguish from quantum execution
- MCP-first: all repo operations use MCP tools

### Quantum-Specific Testing
- Qiskit: `from qiskit.test import QiskitTestCase`
- pytest: `import pytest`, `@pytest.mark.parametrize`
- Hypothesis: `from hypothesis import given, settings`
- unittest: `import unittest`

---

## Quantum Test Patterns

### 1. Deterministic Seed Test
```python
import pytest
from qiskit import QuantumCircuit, Aer, assemble
from qiskit.quantum_info import Statevector

def test_deterministic_seeding():
    """Verify same seed produces identical results."""
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    
    seed = 42
    shots = 1024
    
    # Run twice with same seed
    result1 = Aer.get_backend("aer_simulator").run(
        assemble(qc, shots=shots, seed_simulator=seed)
    ).result()
    result2 = Aer.get_backend("aer_simulator").run(
        assemble(qc, shots=shots, seed_simulator=seed)
    ).result()
    
    assert result1.counts == result2.counts
```

### 2. Statevector Normalization Test
```python
import numpy as np

def test_statevector_normalization():
    """Verify statevector sums to 1.0 within tolerance."""
    from qiskit import QuantumCircuit
    from qiskit.quantum_info import Statevector
    
    qc = QuantumCircuit(2)
    qc.h(0)
    sv = Statevector(qc)
    
    probs = np.abs(sv) ** 2
    assert abs(sum(probs) - 1.0) < 1e-6
```

### 3. Shot Budget Validation Test
```python
def test_shot_budget_enforcement():
    """Verify minimum shot count is enforced."""
    MIN_SHOTS = 100
    
    def run_with_validation(shots: int) -> dict:
        if shots < MIN_SHOTS:
            raise ValueError(f"Shots {shots} below minimum {MIN_SHOTS}")
        return {"shots": shots, "valid": True}
    
    with pytest.raises(ValueError):
        run_with_validation(50)
    
    assert run_with_validation(1024)["valid"]
```

### 4. Classical Approximation Labeling Test
```python
def test_classical_approximation_labeled():
    """Verify classical approximation results are labeled."""
    def classical_approx(num_qubits: int) -> dict:
        return {
            "samples": [[0, 0] for _ in range(10)],
            "num_qubits": num_qubits,
            "method": "classical_approx",  # Must be labeled
            "is_quantum": False
        }
    
    result = classical_approx(3)
    assert result["method"] == "classical_approx"
    assert result["is_quantum"] is False
```

---

## MCP-First Enforcement Layer

This skill operates under aggressive MCP-first tool priority. All repository operations MUST use MCP tools over native Cline tools.

### Tool Priority for Quantum Testing Tasks

| Operation | MCP Tool (prefer) | Native Cline tool (avoid) |
|-----------|-------------------|--------------------------|
| Read test file | `aicarmine_repo_read` | `read_file` |
| Search test patterns | `aicarmine_repo_search` / `aicarmine_repo_search_fd` | `search_files` |
| List test files | `aicarmine_repo_list_files` | `list_files` |
| Git history of tests | `aicarmine_git_readonly_log` | `execute_command git` |
| Validate Python tests | `aicarmine_repo_validate_ruff` | `execute_command ruff` |
| Run pytest | `aicarmine_repo_validate_pytest_run` | `execute_command pytest` |
| Apply test changes | `aicarmine_repo_apply_patch` / `aicarmine_repo_code_apply_patch` | `write_to_file` / `replace_in_file` |

### Quantum Test Classification Rules

- **UnitTest**: Queries containing `test`, `assert`, `unittest`, `pytest` → Use `aicarmine_repo_read` for test files
- **IntegrationTest**: Queries containing `integration`, `e2e`, `end-to-end` → Use `aicarmine_repo_read` for integration test files
- **PropertyTest**: Queries containing `hypothesis`, `property`, `fuzz` → Use `aicarmine_repo_read` for property test files
- **RegressionTest**: Queries containing `regression`, `regress`, `past` → Use `aicarmine_repo_read` for regression test files

### MCP-First Constraints for Quantum Testing Tasks

1. **Never use native `read_file`** for test files — always use `aicarmine_repo_read` with bounded `max_chars`
2. **Never use native `write_to_file`/`replace_in_file`** for test code changes — always use `aicarmine_repo_apply_patch` or `aicarmine_repo_code_apply_patch`
3. **Always seed quantum tests deterministically** — record seeds in `aicarmine_project_memory_search`
4. **Always validate quantum results** — statevector normalization, counts summation
5. **Always enforce shot minimums** — minimum 100 shots
6. **Never present classical approximation as quantum execution** — clear labeling required

---

## Best Practices

### Quantum-Specific Testing
1. **Deterministic seeding**: Every quantum test uses fixed seeds; verify reproducibility
2. **Shot validation**: Enforce minimum 100 shots; test shot budget enforcement
3. **State normalization**: Assert `sum(probabilities) ≈ 1.0` within 1e-6 tolerance
4. **Classical labeling**: Test that classical approximations are properly labeled
5. **Error handling**: Test graceful degradation when quantum SDK unavailable

### Pre-Quantum Testing
1. **Performance bounds**: Classical simulation capped at 50 samples × 10 qubits
2. **No false claims**: Test that classical approximation is never presented as quantum
3. **Graceful degradation**: Test fallback paths when quantum SDK unavailable
4. **Sample limits**: Verify sample count bounds in classical approximation

### Test Structure
1. **Test naming**: Prefix with `test_` for pytest discovery
2. **Fixtures**: Use pytest fixtures for shared quantum circuit setup
3. **Parametrize**: Test multiple qubit counts, depths, shot budgets
4. **Skip decorators**: Skip quantum tests when SDK unavailable
5. **Markers**: Use `@pytest.mark.qiskit`, `@pytest.mark.cirq` for selective execution

---

## File Structure Convention

```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures
├── test_quantum/
│   ├── test_circuits.py     # Circuit builder tests
│   ├── test_simulators.py   # Simulation backend tests
│   ├── test_async_executor.py # Async job executor tests
│   └── test_validators.py   # State/count validation tests
├── test_api/
│   └── test_endpoints.py    # FastAPI endpoint tests
└── test_regression/
    └── test_past_bugs.py    # Regression tests
```

---

## Error Handling Contract

| Error Type | Test Response | Action |
|-----------|--------------|---------------|
| SDK unavailable | `pytest.skip()` with reason | Run classical approximation test instead |
| Circuit build fail | `assertRaises(CircuitBuildError)` | Log traceback, verify error message |
| Job timeout | `assertRaises(QuantumJobTimeoutError)` | Verify timeout handling |
| Invalid qubit count | `assertRaises(InvalidQubitCountError)` | Verify input validation |
| Statevector too large | `assertRaises(StatevectorOverflowError)` | Verify cap and warning |

---

## Quality Gates

1. **Circuit depth check**: Test rejects circuits with depth > 1000 without warning
2. **Shot minimum**: Test enforces minimum 100 shots for statistical validity
3. **Normalization verify**: Test asserts `sum(probabilities) ≈ 1.0` within 1e-6 tolerance
4. **Seed reproducibility**: Test verifies every quantum run records its seed
5. **HTML validation**: Test templates pass HTML5 validator; no inline scripts without CSP nonce

---

## Extended References

- Qiskit Testing: https://qiskit.org/documentation/apidox/test.html
- pytest Documentation: https://docs.pytest.org/
- Hypothesis: https://hypothesis.readthedocs.io/
- Quantum Computing Tests: Property-based testing for quantum algorithms