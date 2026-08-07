# Python Expert Skill — Quantum & Pre-Quantum Engineering Edition

## Overview

This skill extends Python development expertise into **quantum computing**, **pre-quantum engineering**, and **quantum-classical hybrid systems**. It covers quantum SDK integration, async quantum job execution, type hints for quantum data structures, and MCP-first tool priority for all repository operations.

It is designed for:
- Qiskit/Cirq/PennyLane backend development
- Async quantum job orchestration
- Statevector/density matrix manipulation
- Hybrid classical-quantum API endpoints
- Quantum experiment data pipelines

---

## Core Principles

### Python Side
- Type hints for quantum data structures (`Statevector`, `QuantumCircuit`, `DensityMatrix`)
- Async execution for non-blocking quantum job submission
- Deterministic seeding for reproducible quantum simulations
- Graceful degradation when quantum SDK unavailable
- MCP-first: all file reads/writes use `aicarmine_repo_read`/`aicarmine_repo_apply_patch`

### Quantum SDK Integration
- Qiskit: `from qiskit import QuantumCircuit, Aer, assemble`
- Cirq: `import cirq`
- PennyLane: `import pennylane as pwl`
- PyTorchQuantum: `import torchquantum`

---

## Quantum-Specific Patterns

### 1. Type-Hinted Quantum Data Structures
```python
from __future__ import annotations
from typing import NamedTuple, Optional
import numpy as np

class QuantumResult(NamedTuple):
    counts: dict[str, int]
    statevector: Optional[np.ndarray] = None
    shots: int
    seed: int
    backend: str

class CircuitConfig(NamedTuple):
    num_qubits: int
    depth: int
    gates: list[tuple[str, list[int], list[int]]]
    measurements: list[int]
```

### 2. Async Quantum Job Executor
```python
import asyncio
from qiskit import Aer, assemble
from qiskit.quantum_info import Statevector

async def run_quantum_job(circuit: "QuantumCircuit", shots: int = 1024, seed: int = 42) -> QuantumResult:
    """Execute quantum circuit asynchronously with deterministic seeding."""
    simulator = Aer.get_backend("aer_simulator_statevector")
    job = assemble(circuit, shots=shots, seed_simulator=seed, seed_sampler=seed)
    
    async def _execute() -> QuantumResult:
        result = await simulator.run(job).as_completed()
        return QuantumResult(
            counts=result.counts,
            statevector=result.statevector if hasattr(result, 'statevector') else None,
            shots=shots,
            seed=seed,
            backend="qiskit-aer"
        )
    
    return await _execute()
```

### 3. Quantum State Validation
```python
def validate_statevector(sv: np.ndarray, tolerance: float = 1e-6) -> bool:
    """Verify statevector normalization."""
    if sv is None:
        return False
    probs = np.abs(sv) ** 2
    return abs(sum(probs) - 1.0) < tolerance

def validate_counts(counts: dict[str, int], total_shots: int) -> bool:
    """Verify measurement counts sum to expected shots."""
    return sum(counts.values()) == total_shots
```

---

## MCP-First Enforcement Layer

This skill operates under aggressive MCP-first tool priority. All repository operations MUST use MCP tools over native Cline tools.

### Tool Priority for Python Quantum Tasks

| Operation | MCP Tool (prefer) | Native Cline tool (avoid) |
|-----------|-------------------|--------------------------|
| Read quantum module | `aicarmine_repo_read` | `read_file` |
| Search quantum patterns | `aicarmine_repo_search` / `aicarmine_repo_search_fd` | `search_files` |
| List Python files | `aicarmine_repo_list_files` | `list_files` |
| Git history of changes | `aicarmine_git_readonly_log` | `execute_command git` |
| Validate Python code | `aicarmine_repo_validate_ruff` | `execute_command ruff` |
| Apply code changes | `aicarmine_repo_apply_patch` / `aicarmine_repo_code_apply_patch` | `write_to_file` / `replace_in_file` |

### Python Quantum Task Classification Rules

- **QuantumBackend**: Queries containing `qiskit`, `cirq`, `pennylane`, `torchquantum` → Use `aicarmine_repo_read` for SDK integration files
- **AsyncJob**: Queries containing `async`, `await`, `job`, `executor` → Use `aicarmine_repo_read` for async execution patterns
- **TypeHint**: Queries containing `type`, `hint`, `NamedTuple`, `TypedDict` → Use `aicarmine_repo_read` for type definition files
- **Validation**: Queries containing `validate`, `check`, `verify`, `gate` → Use `aicarmine_repo_validate_ruff` for Python validation

### MCP-First Constraints for Python Quantum Tasks

1. **Never use native `read_file`** for Python quantum modules — always use `aicarmine_repo_read` with bounded `max_chars`
2. **Never use native `write_to_file`/`replace_in_file`** for Python code changes — always use `aicarmine_repo_apply_patch` or `aicarmine_repo_code_apply_patch`
3. **Always seed quantum simulations deterministically** — record seeds in `aicarmine_project_memory_search`
4. **Always validate quantum results** — statevector normalization, counts summation
5. **Always use type hints** for quantum data structures
6. **Never block the event loop** with synchronous quantum SDK calls

---

## Best Practices

### Quantum-Specific
1. **Deterministic seeding**: Always set `seed_simulator` and `seed_sampler` for reproducible results
2. **Shot budget**: Default to 1024 shots; expose shot count in API responses
3. **Error mitigation**: Apply measurement error mitigation when hardware backend is used
4. **State validation**: Verify statevector normalization before downstream processing
5. **Qubit limit**: Client-side rendering caps at ~20 qubits (statevector 2^20 too large)

### Pre-Quantum Fallback
1. **Graceful degradation**: Detect quantum SDK availability; fall back to classical approximation
2. **Label approximations**: Clearly mark when results are classically simulated vs quantum
3. **Performance bounds**: Classical simulation capped at 50 samples × 10 qubits
4. **No false claims**: Never present classical approximation as quantum execution

### Python Integration
1. **Type hints**: Use `typing.NamedTuple`, `typing.Optional`, `typing.Literal` for quantum data
2. **Async execution**: Quantum jobs run asynchronously; show loading states
3. **Result caching**: Store experiment results in SQLite for replay
4. **Error contracts**: Consistent exception types for quantum failures
5. **Logging**: Record seed, shots, backend for every quantum run

---

## File Structure Convention

```
project/
├── quantum/
│   ├── __init__.py
│   ├── circuits.py            # Circuit builders
│   ├── simulators.py          # Simulation backends
│   ├── async_executor.py      # Async quantum job runner
│   └── validators.py          # State/count validation
├── api/
│   ├── __init__.py
│   └── endpoints.py           # FastAPI quantum endpoints
├── experiments/
│   └── logs.db                # SQLite experiment archive
└── requirements.txt
    # fastapi, qiskit, qiskit-aer, numpy, scipy
```

---

## Error Handling Contract

| Error Type | Python Response | Action |
|-----------|--------------|---------------|
| SDK unavailable | Raise `QuantumSDKUnavailableError` | Run `classical_approximate_quantum()` |
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
5. **Type hint coverage**: All quantum data structures must have type hints

---

## Extended References

- Qiskit Documentation: https://qiskit.org/documentation/
- Cirq Guide: https://quantumai.google/cirq
- PennyLane API: https://pennylane.ai/documentation/
- Python typing: https://docs.python.org/3/library/typing.html
- Asyncio: https://docs.python.org/3/library/asyncio.html