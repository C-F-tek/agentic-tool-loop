# Software Architect Skill — Quantum & Pre-Quantum Engineering Edition

## Overview

This skill extends software architecture analysis into **quantum computing**, **pre-quantum engineering**, and **quantum-classical hybrid systems**. It covers hybrid system design patterns, module boundary separation, dependency management between classical and quantum components, and MCP-first tool priority for all repository operations.

It is designed for:
- Architecture of quantum-classical hybrid workflows
- Module boundary design between classical preprocessing/postprocessing and quantum execution
- Dependency injection for quantum SDK abstraction
- Scalability patterns for quantum simulation
- MCP-first: all repo operations use MCP tools

---

## Core Principles

### Architecture Design
- Separation of concerns: classical vs quantum phases
- Dependency inversion: quantum SDK abstraction layer
- Graceful degradation: fallback when quantum SDK unavailable
- Bounded execution: async quantum jobs with timeouts
- MCP-first: all repo operations use MCP tools

### Hybrid System Architecture
- Classical preprocessing → Quantum execution → Classical postprocessing pipeline
- Quantum SDK abstraction via interface/protocol
- Deterministic seeding for reproducibility
- Shot budget enforcement at API boundary
- MCP-first: all file reads use `aicarmine_repo_read`, all writes use `aicarmine_repo_apply_patch`

---

## Architecture Patterns

### 1. Quantum SDK Abstraction Layer
```python
from abc import ABC, abstractmethod
from typing import NamedTuple
import numpy as np

class QuantumResult(NamedTuple):
    counts: dict[str, int]
    shots: int
    seed: int
    backend: str

class QuantumBackend(ABC):
    """Abstract base for quantum backends."""
    
    @abstractmethod
    async def execute(self, circuit: "QuantumCircuit", shots: int = 1024, seed: int = 42) -> QuantumResult:
        pass

class QiskitBackend(QuantumBackend):
    """Concrete implementation using Qiskit."""
    
    async def execute(self, circuit: "QuantumCircuit", shots: int = 1024, seed: int = 42) -> QuantumResult:
        # Implementation using qiskit
        pass

class ClassicalApproxBackend(QuantumBackend):
    """Fallback for when quantum SDK unavailable."""
    
    async def execute(self, circuit: "QuantumCircuit", shots: int = 1024, seed: int = 42) -> QuantumResult:
        # Classical approximation
        pass
```

### 2. Hybrid Workflow Pipeline Architecture
```python
class HybridWorkflowPipeline:
    """Classical → Quantum → Classical pipeline."""
    
    def __init__(self, backend: QuantumBackend):
        self.backend = backend
        self.preprocessors: list[callable] = []
        self.postprocessors: list[callable] = []
    
    def add_preprocessor(self, fn: callable) -> "HybridWorkflowPipeline":
        self.preprocessors.append(fn)
        return self
    
    def add_postprocessor(self, fn: callable) -> "HybridWorkflowPipeline":
        self.postprocessors.append(fn)
        return self
    
    async def run(self, input_data: dict) -> dict:
        # Stage 1: Classical preprocessing
        prep_result = input_data
        for fn in self.preprocessors:
            prep_result = fn(prep_result)
        
        # Stage 2: Quantum execution
        quantum_result = await self.backend.execute(
            circuit=prep_result.get("circuit"),
            shots=prep_result.get("shots", 1024),
            seed=prep_result.get("seed", 42)
        )
        
        # Stage 3: Classical postprocessing
        post_result = quantum_result
        for fn in self.postprocessors:
            post_result = fn(post_result)
        
        return {
            "preprocessing": prep_result,
            "quantum_result": quantum_result,
            "postprocessing": post_result
        }
```

### 3. Module Boundary Design
```
project/
├── classical/                    # Classical preprocessing/postprocessing
│   ├── __init__.py
│   ├── preprocessors.py         # Input transformation
│   └── postprocessors.py        # Output optimization
├── quantum/                      # Quantum execution layer
│   ├── __init__.py
│   ├── backends.py              # QuantumBackend interface + implementations
│   ├── circuits.py              # Circuit builders
│   └── validators.py            # State/count validation
├── pipeline/                     # Hybrid workflow orchestration
│   ├── __init__.py
│   └── pipeline.py              # HybridWorkflowPipeline
├── api/                          # FastAPI endpoints
│   ├── __init__.py
│   └── endpoints.py             # REST API
└── config/                       # Configuration
    ├── __init__.py
    └── settings.py              # Shot budgets, seeds, backend selection
```

---

## MCP-First Enforcement Layer

This skill operates under aggressive MCP-first tool priority. All repository operations MUST use MCP tools over native Cline tools.

### Tool Priority for Architecture Tasks

| Operation | MCP Tool (prefer) | Native Cline tool (avoid) |
|-----------|-------------------|--------------------------|
| Read architecture file | `aicarmine_repo_read` | `read_file` |
| Search module boundaries | `aicarmine_repo_search` / `aicarmine_repo_search_fd` | `search_files` |
| List module files | `aicarmine_repo_list_files` | `list_files` |
| Git history of architecture | `aicarmine_git_readonly_log` | `execute_command git` |
| Apply architecture changes | `aicarmine_repo_apply_patch` / `aicarmine_repo_code_apply_patch` | `write_to_file` / `replace_in_file` |

### Architecture Classification Rules

- **ModuleBoundary**: Queries containing `module`, `boundary`, `interface`, `protocol` → Use `aicarmine_repo_read` for interface files
- **DependencyInjection**: Queries containing `dependency`, `injection`, `abstraction`, `mock` → Use `aicarmine_repo_read` for DI files
- **PipelineArchitecture**: Queries containing `pipeline`, `workflow`, `stage`, `phase` → Use `aicarmine_repo_read` for pipeline files
- **ScalabilityPattern**: Queries containing `scale`, `performance`, `optimization` → Use `aicarmine_repo_read` for performance files

### MCP-First Constraints for Architecture Tasks

1. **Never use native `read_file`** for architecture files — always use `aicarmine_repo_read` with bounded `max_chars`
2. **Never use native `write_to_file`/`replace_in_file`** for architecture changes — always use `aicarmine_repo_apply_patch` or `aicarmine_repo_code_apply_patch`
3. **Always abstract quantum SDK** — never couple classical code directly to Qiskit/Cirq
4. **Always enforce shot budgets** at API boundary
5. **Always seed deterministically** — record seeds in `aicarmine_project_memory_search`
6. **Always label classical approximation** — distinguish from quantum execution

---

## Best Practices

### Quantum-Specific Architecture
1. **SDK abstraction**: Define `QuantumBackend` interface; never couple classical code to specific SDK
2. **Graceful degradation**: Detect SDK availability; fallback to classical approximation
3. **Shot budget enforcement**: Enforce minimum 100 shots at API boundary
4. **Deterministic seeding**: Record seed, shots, backend for every quantum run
5. **State validation**: Verify statevector normalization before downstream processing

### Pre-Quantum Architecture
1. **Performance bounds**: Classical simulation capped at 50 samples × 10 qubits
2. **No false claims**: Never present classical approximation as quantum execution
3. **Clear labeling**: Mark classical approximation results explicitly
4. **Sample limits**: Enforce sample count bounds in classical approximation

### Architecture Structure
1. **Separation of concerns**: Classical vs quantum phases clearly separated
2. **Dependency inversion**: Quantum SDK abstraction layer
3. **Bounded execution**: Async quantum jobs with timeouts
4. **Result caching**: Store experiment results in SQLite for replay
5. **Error contracts**: Consistent exception types for quantum failures

---

## File Structure Convention

```
project/
├── classical/
│   ├── __init__.py
│   ├── preprocessors.py
│   └── postprocessors.py
├── quantum/
│   ├── __init__.py
│   ├── backends.py
│   ├── circuits.py
│   └── validators.py
├── pipeline/
│   ├── __init__.py
│   └── pipeline.py
├── api/
│   ├── __init__.py
│   └── endpoints.py
├── config/
│   ├── __init__.py
│   └── settings.py
└── requirements.txt
    # fastapi, qiskit, qiskit-aer, numpy, scipy
```

---

## Error Handling Contract

| Error Type | Architecture Response | Action |
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
- Architecture Patterns: Clean Architecture, Hexagonal Architecture
- Dependency Injection: https://martinfowler.com/articles/injection.html