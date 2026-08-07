# Documentation Skill — Quantum & Pre-Quantum Engineering Edition

## Overview

This skill extends technical documentation practices into **quantum computing**, **pre-quantum engineering**, and **quantum-classical hybrid systems**. It covers quantum API reference creation, experiment log documentation, circuit diagram annotations, and MCP-first tool priority for all repository operations.

It is designed for:
- Quantum SDK API documentation (Qiskit, Cirq, PennyLane)
- Experiment log documentation with seed/shots/backend metadata
- Circuit depth and gate composition annotations
- Hybrid workflow pipeline documentation
- MCP-first: all file reads use `aicarmine_repo_read`, all writes use `aicarmine_repo_apply_patch`

---

## Core Principles

### Documentation Structure
- Quantum API docs follow Google Python Style Guide
- Experiment logs include seed, shots, backend, timestamp
- Circuit diagrams annotated with gate composition and depth
- Hybrid workflows documented with classical/quantum phase boundaries
- MCP-first: all repo operations use MCP tools

### Quantum-Specific Documentation
- Qiskit: https://qiskit.org/documentation/
- Cirq: https://quantumai.google/cirq
- PennyLane: https://pennylane.ai/documentation/
- Sphinx: https://sphinx-doc.org/
- MkDocs: https://www.mkdocs.org/

---

## Quantum Documentation Patterns

### 1. Quantum API Reference Template
```markdown
# QuantumCircuit Documentation

## Overview
`QuantumCircuit` represents a quantum computation diagram.

## Parameters
- `num_qubits` (int): Number of qubits in the circuit
- `name` (str): Circuit name for identification
- `qregs` (list): Quantum registers
- `cregs` (list): Classical registers

## Methods

### `h(qubit)`
Applies Hadamard gate to specified qubit.

**Parameters:**
- `qubit` (int): Qubit index

**Returns:** None

**Example:**
```python
from qiskit import QuantumCircuit
qc = QuantumCircuit(2)
qc.h(0)  # Superposition on qubit 0
```

### `cx(control, target)`
Applies controlled-NOT gate.

**Parameters:**
- `control` (int): Control qubit index
- `target` (int): Target qubit index

**Returns:** None

**Example:**
```python
qc.cx(0, 1)  # Entangle qubit 0 with qubit 1
```
```

### 2. Experiment Log Template
```markdown
# Experiment Log: Bell State Generation

## Metadata
- **Date**: 2026-08-07
- **Seed**: 42
- **Shots**: 1024
- **Backend**: qiskit-aer/statevector_simulator
- **Circuit Depth**: 2
- **Qubits**: 2

## Circuit Description
Bell state circuit: H on qubit 0, CX(0,1) to entangle.

## Results
| State | Counts | Probability |
|-------|--------|-------------|
| 00    | 512    | 0.50        |
| 11    | 512    | 0.50        |

## Notes
Classical approximation available via `classical_approximate_quantum()` if quantum SDK unavailable.
```

### 3. Hybrid Workflow Documentation
```markdown
# Hybrid Quantum-Classical Workflow: VQE

## Pipeline Stages

### Stage 1: Classical Preprocessing
Input molecular geometry → Generate initial parameter vector.

**Tool**: `aicarmine_repo_read` for parameter initialization code.

### Stage 2: Quantum Execution
Build ansatz circuit → Execute on simulator/hardware → Measure expectation value.

**Tool**: `aicarmine_repo_read` for ansatz builder, `aicarmine_project_memory_search` for parameter history.

### Stage 3: Classical Postprocessing
Optimize parameters → Converge to ground state energy.

**Tool**: `aicarmine_repo_apply_patch` for optimizer updates.

## MCP-First Tool Usage
- Read ansatz code: `aicarmine_repo_read` (never `read_file`)
- Search optimizer patterns: `aicarmine_repo_search` (never `search_files`)
- Apply parameter updates: `aicarmine_repo_apply_patch` (never `write_to_file`)
```

---

## MCP-First Enforcement Layer

This skill operates under aggressive MCP-first tool priority. All repository operations MUST use MCP tools over native Cline tools.

### Tool Priority for Quantum Documentation Tasks

| Operation | MCP Tool (prefer) | Native Cline tool (avoid) |
|-----------|-------------------|--------------------------|
| Read doc file | `aicarmine_repo_read` | `read_file` |
| Search doc patterns | `aicarmine_repo_search` / `aicarmine_repo_search_fd` | `search_files` |
| List doc files | `aicarmine_repo_list_files` | `list_files` |
| Git history of docs | `aicarmine_git_readonly_log` | `execute_command git` |
| Apply doc changes | `aicarmine_repo_apply_patch` / `aicarmine_repo_code_apply_patch` | `write_to_file` / `replace_in_file` |

### Quantum Documentation Classification Rules

- **APIRef**: Queries containing `api`, `reference`, `documentation`, `docs` → Use `aicarmine_repo_read` for API doc files
- **ExperimentLog**: Queries containing `experiment`, `log`, `result`, `measurement` → Use `aicarmine_repo_read` for experiment log files
- **WorkflowDoc**: Queries containing `workflow`, `pipeline`, `hybrid` → Use `aicarmine_repo_read` for workflow documentation
- **CircuitDiagram**: Queries containing `circuit`, `diagram`, `gate`, `annotation` → Use `aicarmine_repo_read` for circuit diagram files

### MCP-First Constraints for Quantum Documentation Tasks

1. **Never use native `read_file`** for documentation files — always use `aicarmine_repo_read` with bounded `max_chars`
2. **Never use native `write_to_file`/`replace_in_file`** for documentation changes — always use `aicarmine_repo_apply_patch` or `aicarmine_repo_code_apply_patch`
3. **Always record experiment metadata** — seed, shots, backend, timestamp in every experiment log
4. **Always annotate circuit depth** — document gate composition and depth in circuit diagrams
5. **Always label classical approximation** — distinguish from quantum execution in documentation
6. **Never present classical approximation as quantum execution** — clear labeling required

---

## Best Practices

### Quantum-Specific Documentation
1. **Deterministic seeding**: Document seed value for every experiment
2. **Shot budget**: Document shot count and minimum enforcement
3. **Backend identification**: Always specify simulator vs hardware backend
4. **State validation**: Document normalization tolerance (1e-6)
5. **Qubit limits**: Document client-side rendering caps (~20 qubits)

### Pre-Quantum Documentation
1. **Graceful degradation**: Document fallback paths when quantum SDK unavailable
2. **Label approximations**: Clearly mark classical simulation vs quantum execution
3. **Performance bounds**: Document classical simulation limits (50 samples × 10 qubits)
4. **No false claims**: Never present classical approximation as quantum execution

### Documentation Structure
1. **Markdown first**: Use Markdown for API references and experiment logs
2. **Sphinx/MkDocs**: Use Sphinx for Python API docs, MkDocs for project documentation
3. **Code examples**: Include runnable code examples for every API method
4. **Metadata headers**: Include seed, shots, backend in experiment logs
5. **Cross-references**: Link related experiments and workflows

---

## File Structure Convention

```
docs/
├── api/
│   ├── quantum_circuit.md    # QuantumCircuit API reference
│   ├── async_executor.md     # Async job executor API
│   └── validators.md         # State/count validation API
├── experiments/
│   └── logs/
│       └── bell-state-20260807.md  # Experiment log
├── workflows/
│   └── vqe-hybrid.md         # VQE hybrid workflow documentation
├── circuits/
│   └── bell-state-diagram.md # Circuit diagram annotations
└── README.md                 # Project overview
```

---

## Error Handling Contract

| Error Type | Documentation Response | Action |
|-----------|--------------|---------------|
| SDK unavailable | Document classical fallback | Run `classical_approximate_quantum()` |
| Circuit build fail | Document error message format | Log traceback, return error dict |
| Job timeout | Document timeout handling | Cancel job, offer reduced shots |
| Invalid qubit count | Document input validation | Validate input before circuit creation |
| Statevector too large | Document cap and warning | Cap at 20 qubits, warn user |

---

## Quality Gates

1. **Circuit depth check**: Document circuits with depth > 1000 with warning
2. **Shot minimum**: Document minimum 100 shots for statistical validity
3. **Normalization verify**: Document `sum(probabilities) ≈ 1.0` within 1e-6 tolerance
4. **Seed reproducibility**: Document every quantum run seed value
5. **HTML validation**: Document templates pass HTML5 validator; no inline scripts without CSP nonce

---

## Extended References

- Qiskit Documentation: https://qiskit.org/documentation/
- Cirq Guide: https://quantumai.google/cirq
- PennyLane API: https://pennylane.ai/documentation/
- Sphinx: https://sphinx-doc.org/
- MkDocs: https://www.mkdocs.org/
- Google Python Style: https://google.github.io/styleguide/pyguide.html