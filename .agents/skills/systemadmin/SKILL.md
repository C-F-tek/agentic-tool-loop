# System Admin Skill — Quantum & Pre-Quantum Engineering Edition

## Overview

This skill extends system administration into **quantum computing**, **pre-quantum engineering**, and **quantum-classical hybrid systems**. It covers quantum service management, NPU/GPU runtime monitoring, quantum SDK environment configuration, and MCP-first tool priority for all repository operations.

It is designed for:
- Managing quantum simulation services (Qiskit Aer, Cirq simulator)
- Monitoring NPU/GPU runtime for quantum execution
- Configuring quantum SDK environments and dependencies
- MCP-first: all repo operations use MCP tools

---

## Core Principles

### System Administration
- Quantum SDK environment isolation (virtual environments)
- NPU/GPU runtime monitoring for quantum execution
- Service health checks for quantum simulators
- Shot budget enforcement at system level
- MCP-first: all repo operations use MCP tools

### Quantum-Specific System Patterns
- Virtual environment per quantum SDK version
- NPU/GPU availability checks before quantum execution
- Service ports for quantum API endpoints
- Environment variable configuration for seeds/shots
- MCP-first: all file reads use `aicarmine_repo_read`, all writes use `aicarmine_repo_apply_patch`

---

## System Administration Patterns

### 1. Quantum SDK Environment Management
```bash
# Create virtual environment for quantum SDK
python -m venv ~/.venvs/qiskit-env
source ~/.venvs/qiskit-env/bin/activate  # Linux/Mac
~/.venvs/qiskit-env/Scripts/activate.bat  # Windows

# Install quantum SDK
pip install qiskit qiskit-aer numpy scipy

# Verify installation
python -c "from qiskit import QuantumCircuit; print('Qiskit OK')"
python -c "import cirq; print('Cirq OK')"
python -c "import pennylane as pwl; print('PennyLane OK')"
```

### 2. NPU/GPU Runtime Monitoring for Quantum Execution
```powershell
# Check NPU/GPU availability for quantum simulation
Get-Process | Where-Object { $_.Name -like "*quantum*" }
Get-NetTCPConnection | Where-Object { $_.LocalPort -eq 3572 }  # Quantum API port
Get-Service | Where-Object { $_.Name -like "*quantum*" }

# Monitor NPU/GPU utilization
Get-WmiObject -Class Win32_GPU | Select-Object Name, Status, DriverVersion
```

### 3. Service Health Check for Quantum Simulators
```bash
# Check quantum API endpoint health
curl http://localhost:3572/health
curl http://localhost:3572/api/quantum/status

# Check quantum SDK environment
python -c "import qiskit; print(qiskit.__version__)"
python -c "import cirq; print(cirq.__version__)"
python -c "import pennylane; print(pennylane.__version__)"
```

---

## MCP-First Enforcement Layer

This skill operates under aggressive MCP-first tool priority. All repository operations MUST use MCP tools over native Cline tools.

### Tool Priority for System Admin Tasks

| Operation | MCP Tool (prefer) | Native Cline tool (avoid) |
|-----------|-------------------|--------------------------|
| Read service config | `aicarmine_repo_read` | `read_file` |
| Search service patterns | `aicarmine_repo_search` / `aicarmine_repo_search_fd` | `search_files` |
| List service files | `aicarmine_repo_list_files` | `list_files` |
| Git history of services | `aicarmine_git_readonly_log` | `execute_command git` |
| Validate Python services | `aicarmine_repo_validate_ruff` | `execute_command ruff` |
| Apply service changes | `aicarmine_repo_apply_patch` / `aicarmine_repo_code_apply_patch` | `write_to_file` / `replace_in_file` |

### System Admin Classification Rules

- **ServiceHealth**: Queries containing `health`, `status`, `service`, `monitor` → Use `aicarmine_repo_read` for service config files
- **EnvironmentConfig**: Queries containing `environment`, `config`, `virtual-env`, `venv` → Use `aicarmine_repo_read` for environment files
- **NPU-GPUMonitor**: Queries containing `npu`, `gpu`, `runtime`, `utilization` → Use `aicarmine_repo_read` for NPU/GPU monitoring files
- **SDKVersion**: Queries containing `sdk`, `version`, `qiskit`, `cirq`, `pennylane` → Use `aicarmine_repo_read` for SDK version files

### MCP-First Constraints for System Admin Tasks

1. **Never use native `read_file`** for service config files — always use `aicarmine_repo_read` with bounded `max_chars`
2. **Never use native `write_to_file`/`replace_in_file`** for service configuration changes — always use `aicarmine_repo_apply_patch` or `aicarmine_repo_code_apply_patch`
3. **Always check NPU/GPU availability** before quantum execution
4. **Always enforce shot budgets** at system level
5. **Always seed deterministically** — record seeds in `aicarmine_project_memory_search`
6. **Always label classical approximation** — distinguish from quantum execution

---

## Best Practices

### Quantum-Specific System Administration
1. **SDK environment isolation**: Maintain separate virtual environments per quantum SDK version
2. **NPU/GPU monitoring**: Check NPU/GPU availability before quantum execution
3. **Service health checks**: Verify quantum API endpoints are healthy
4. **Shot budget enforcement**: Enforce minimum 100 shots at system level
5. **Deterministic seeding**: Record seed, shots, backend for every quantum run

### Pre-Quantum System Administration
1. **Classical approximation services**: Ensure fallback services are available when quantum SDK unavailable
2. **No false claims**: Never present classical approximation as quantum execution
3. **Clear labeling**: Mark classical approximation results explicitly
4. **Sample limits**: Enforce sample count bounds in classical approximation

### System Structure
1. **Virtual environments**: One per quantum SDK version
2. **NPU/GPU monitoring**: Continuous monitoring for quantum execution availability
3. **Service ports**: Quantum API endpoints on dedicated ports (3572, 3579)
4. **Environment variables**: Configure seeds, shots, backend selection
5. **Health checks**: Regular health checks for quantum simulators

---

## File Structure Convention

```
project/
├── services/
│   ├── __init__.py
│   ├── quantum_api.py           # Quantum API endpoint service
│   ├── simulator_service.py     # Quantum simulator service
│   └── health_check.py          # Service health check
├── config/
│   ├── __init__.py
│   └── env_config.py            # Environment variable configuration
├── monitoring/
│   ├── __init__.py
│   └── npu_gpu_monitor.py       # NPU/GPU runtime monitoring
└── requirements.txt
    # fastapi, qiskit, qiskit-aer, numpy, scipy
```

---

## Error Handling Contract

| Error Type | System Admin Response | Action |
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
- System Administration: Service management, environment configuration
- MCP-first: All repo operations use MCP tools