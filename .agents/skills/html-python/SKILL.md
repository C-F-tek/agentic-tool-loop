# HTML-Python Skill — Quantum & Pre-Quantum Engineering Edition

## Overview

This skill extends standard HTML/Python web development practices into **quantum computing**, **pre-quantum engineering**, and **quantum-classical hybrid systems** visualization, simulation, and documentation interfaces.

It is designed for building:
- Quantum circuit visualizers
- Qubit state browsers
- Quantum algorithm demonstrators
- Pre-quantum simulation dashboards
- Hybrid classical-quantum workflow interfaces
- Quantum experiment data explorers

---

## Core Principles

### HTML Side
- Semantic structure for quantum concepts (qubit registers, gates, circuits)
- Canvas/SVG-based quantum state visualization
- Responsive layouts for complex quantum circuit diagrams
- Accessible data tables for quantum measurement results
- Client-side rendering of quantum probability distributions

### Python Side
- Quantum simulation backends (Qiskit, Cirq, PennyLane, PyTorchQuantum)
- Pre-quantum classical approximations (density matrix, statevector, Bloch sphere)
- Hybrid classical-quantum API endpoints
- Quantum experiment data pipelines
- Deterministic seeding for reproducible quantum simulations

---

## Quantum-Specific Patterns

### 1. Circuit Visualization Layer
```python
# Backend: Generate circuit description as JSON
from qiskit import QuantumCircuit
from qiskit.circuit.library import HGate, CXGate, XGate

def circuit_to_html_json(qc: QuantumCircuit) -> dict:
    """Convert Qiskit circuit to HTML-renderable JSON structure."""
    layers = []
    wire_count = qc.num_qubits
    for idx, instruction in enumerate(qc.data):
        layers.append({
            "gate": instruction.operation.name,
            "targets": [q._index for q in instruction.qubits],
            "controls": [q._index for q in instruction.clbits],
            "layer_index": idx
        })
    return {
        "num_qubits": wire_count,
        "depth": qc.depth(),
        "gates": layers,
        "measurement_results": None  # populated after run
    }
```

### 2. Statevector Browser
```python
def statevector_to_html_table(statevector: np.ndarray, title: str = "Quantum State") -> str:
    """Render complex statevector amplitudes as an HTML table."""
    probs = np.abs(statevector) ** 2
    html_parts = [f"<h2>{title}</h2>", "<table>",
                  "<tr><th>State</th><th>Amplitude</th><th>Probability</th></tr>"]
    for i, (amp, prob) in enumerate(zip(statevector, probs)):
        amp_str = f"{amp.real:.4f} + {amp.imag:.4f}i" if amp.imag != 0 else f"{amp.real:.4f}"
        html_parts.append(f"<tr><td>|{i:0{int(np.log2(len(statevector)))+1}d>}</td>"
                          f"<td>{amp_str}</td><td>{prob:.4f}</td></tr>")
    html_parts.append("</table>")
    return "\n".join(html_parts)
```

### 3. Bloch Sphere Data Endpoint
```python
def bloch_coordinates(statevector: np.ndarray) -> dict:
    """Compute x, y, z coordinates for single-qubit Bloch representation."""
    rho = statevector @ statevector.conj().T
    trace_x = np.trace(rho * np.array([[0, 1], [1, 0]]))
    trace_y = np.trace(rho * np.array([[0, -1j], [1j, 0]]))
    trace_z = np.trace(rho * np.array([[1, 0], [0, -1]]))
    return {"x": float(trace_x.real), "y": float(trace_y.real), "z": float(trace_z.real)}
```

---

## Pre-Quantum Engineering Patterns

### 4. Classical Approximation Layer
For environments where quantum hardware is unavailable:
```python
def classical_approximate_quantum(num_qubits: int, circuit_depth: int) -> dict:
    """Pre-quantum classical simulation of quantum behavior.
    
    Uses tensor network contraction and Monte Carlo sampling
    to approximate quantum outcomes without full statevector.
    """
    samples = []
    for _ in range(1000):
        sample = []
        for q in range(num_qubits):
            # Classical probabilistic bit simulation
            prob = 0.5
            for gate in range(circuit_depth):
                if gate % 3 == 0:  # Simulate H-gate effect
                    prob = 0.5
                elif gate % 3 == 1:  # Simulate X-gate effect
                    prob = 1.0 - prob
                else:  # Simulate CX correlation
                    if sample:
                        prob = sample[-1]
            sample.append(1 if random.random() < prob else 0)
        samples.append(sample)
    return {"samples": samples, "num_qubits": num_qubits, "method": "classical_approx"}
```

### 5. Hybrid Workflow Orchestrator
```python
class HybridQuantumWorkflow:
    """Manages classical preprocessing → quantum execution → classical postprocessing."""
    
    def __init__(self, backend: str = "qiskit-aer"):
        self.backend = backend
        self.classical_prep_fn = None
        self.quantum_circuit_fn = None
        self.classical_post_fn = None
    
    def set_pipeline(self, prep_fn, circuit_fn, post_fn):
        self.classical_prep_fn = prep_fn
        self.quantum_circuit_fn = circuit_fn
        self.classical_post_fn = post_fn
    
    async def execute(self, input_data: dict) -> dict:
        # Step 1: Classical preprocessing
        prep_result = self.classical_prep_fn(input_data) if self.classical_prep_fn else input_data
        
        # Step 2: Build and run quantum circuit
        qc = self.quantum_circuit_fn(prep_result) if self.quantum_circuit_fn else QuantumCircuit(2)
        simulator = Aer.get_backend(self.backend)
        job = assemble(qc, simulator)
        result = await simulator.run(job).as_completed()
        
        # Step 3: Classical postprocessing
        post_result = self.classical_post_fn(result) if self.classical_post_fn else result
        
        return {
            "preprocessing": prep_result,
            "quantum_result": result.counts,
            "postprocessing": post_result
        }
```

---

## HTML Template Patterns

### Quantum Circuit Display
```html
<div class="quantum-circuit-viewer">
  <div class="circuit-wires" id="circuit-wires"></div>
  <div class="circuit-gates" id="circuit-gates"></div>
  <div class="measurement-results" id="measurement-results"></div>
</div>

<script>
function renderQuantumCircuit(circuitData) {
  const wiresDiv = document.getElementById('circuit-wires');
  const gatesDiv = document.getElementById('circuit-gates');
  
  // Render qubit wires
  for (let i = 0; i < circuitData.num_qubits; i++) {
    const wire = document.createElement('div');
    wire.className = 'qubit-wire';
    wire.textContent = `q${i}: ───`;
    wiresDiv.appendChild(wire);
  }
  
  // Render gates as positioned elements
  circuitData.gates.forEach(gate => {
    const el = document.createElement('div');
    el.className = `gate-${gate.gate.toLowerCase()}`;
    el.style.left = `${gate.layer_index * 40}px`;
    el.style.top = `${gate.targets[0] * 30}px`;
    el.textContent = gate.gate;
    gatesDiv.appendChild(el);
  });
}
</script>
```

### State Probability Bar Chart
```html
<div class="probability-chart">
  <h3>Measurement Distribution</h3>
  <div id="prob-bars"></div>
</div>

<script>
function renderProbabilityBars(counts, total_shots) {
  const container = document.getElementById('prob-bars');
  container.innerHTML = '';
  Object.entries(counts).forEach(([state, count]) => {
    const prob = count / total_shots;
    const bar = document.createElement('div');
    bar.className = 'prob-bar';
    bar.style.width = `${prob * 100}%`;
    bar.title = `${state}: ${count} (${(prob*100).toFixed(2)}%)`;
    container.appendChild(bar);
    
    const label = document.createElement('span');
    label.textContent = `${state} ${prob.toFixed(3)}`;
    container.appendChild(label);
  });
}
</script>
```

---

## Technology Stack Recommendations

| Layer | Tools |
|-------|-------|
| Frontend | HTML5, CSS Grid/SVG, Vanilla JS or Alpine.js |
| Backend | Python 3.11+, FastAPI or Flask |
| Quantum SDK | Qiskit, Cirq, PennyLane, TorchQuantum |
| Simulation | qiskit-aer, numpy, scipy |
| Data | JSON, SQLite for experiment logs |
| Visualization | Canvas API, D3.js (optional), matplotlib (server-side) |

---

## Best Practices

### Quantum-Specific
1. **Deterministic seeding**: Always set `seed_simulator` and `seed_sampler` for reproducible results
2. **Shot budget**: Default to 1024 shots; expose shot count in UI controls
3. **Error mitigation**: Apply measurement error mitigation when hardware backend is used
4. **State validation**: Verify statevector normalization before visualization
5. **Qubit limit**: Client-side rendering caps at ~20 qubits (statevector 2^20 too large)

### Pre-Quantum Fallback
1. **Graceful degradation**: Detect quantum SDK availability; fall back to classical approximation
2. **Label approximations**: Clearly mark when results are classically simulated vs quantum
3. **Performance bounds**: Classical simulation capped at 50 samples × 10 qubits
4. **No false claims**: Never present classical approximation as quantum execution

### HTML/Python Integration
1. **API-first**: Backend returns JSON; frontend renders dynamically
2. **Async execution**: Quantum jobs run asynchronously; show loading states
3. **Result caching**: Store experiment results in SQLite for replay
4. **Template inheritance**: Base HTML template with quantum-specific blocks
5. **Accessibility**: ARIA labels for circuit elements, keyboard navigation for gate selection

---

## File Structure Convention

```
project/
├── templates/
│   └── quantum/
│       ├── base.html              # Base template with circuit viewer
│       ├── circuit_display.html   # Circuit visualization page
│       ├── state_browser.html     # Statevector/Bloch page
│       └── experiment_results.html # Measurement results page
├── static/
│   └── quantum/
│       ├── circuit.css            # Circuit styling
│       └── viz.js                 # Client-side quantum rendering
├── backend/
│   ├── api.py                     # FastAPI endpoints
│   ├── circuits.py                # Circuit builders
│   ├── simulators.py              # Simulation backends
│   └── hybrid_workflow.py         # Classical-quantum pipeline
├── experiments/
│   └── logs.db                    # SQLite experiment archive
└── requirements.txt
    # fastapi, qiskit, qiskit-aer, numpy, scipy
```

---

## Error Handling Contract

| Error Type | HTML Response | Python Action |
|-----------|--------------|---------------|
| SDK unavailable | Show classical approximation notice | Run `classical_approximate_quantum()` |
| Circuit build fail | Display error message in `<pre>` | Log traceback, return error JSON |
| Job timeout | Show "running..." with retry button | Cancel job, offer reduced shots |
| Invalid qubit count | Disable submit button | Validate input before circuit creation |
| Statevector too large | Show truncated view | Cap at 20 qubits, warn user |

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
- Quantum Computing Report: Pre-quantum classical methods for near-term devices
- NISQ Era Patterns: Hybrid algorithms (VQE, QAOA, QNN)

---

## MCP-First Enforcement Layer

This skill operates under aggressive MCP-first tool priority. All repository operations MUST use MCP tools over native Cline tools.

### Tool Priority for Quantum Engineering Tasks

| Operation | MCP Tool (prefer) | Native Cline tool (avoid) |
|-----------|-------------------|--------------------------|
| Read circuit file | `aicarmine_repo_read` | `read_file` |
| Search quantum modules | `aicarmine_repo_search` / `aicarmine_repo_search_fd` | `search_files` |
| List quantum templates | `aicarmine_repo_list_files` | `list_files` |
| Git history of circuits | `aicarmine_git_readonly_log` | `execute_command git` |
| Validate Python code | `aicarmine_repo_validate_ruff` | `execute_command ruff` |
| Query experiment metadata | `aicarmine_project_memory_search` | — |
| Apply HTML template changes | `aicarmine_repo_apply_patch` / `aicarmine_repo_code_apply_patch` | `write_to_file` / `replace_in_file` |

### Quantum Task Classification Rules

When a task involves quantum computing concepts, the following classification applies:

- **QuantumCircuit**: Queries containing `circuit`, `gate`, `quantum.circuit`, `qubit.register` → Use `aicarmine_repo_read` for circuit definition files
- **QuantumState**: Queries containing `statevector`, `bloch`, `density.matrix`, `state.browser` → Use `aicarmine_repo_read` for state data + `aicarmine_project_memory_search` for metadata
- **QuantumExperiment**: Queries containing `experiment`, `shots`, `measurement`, `vqe`, `qaoa`, `qnn`, `nisq` → Use `aicarmine_project_memory_search` for experiment logs
- **PreQuantumSimulation**: Queries containing `pre.quantum`, `classical.approximation`, `simulation`, `hybrid.quantum` → Use `aicarmine_repo_read` for simulation code + `aicarmine_repo_search_fd` for pattern discovery

### MCP-First Constraints for Quantum Tasks

1. **Never use native `read_file`** for circuit/statevector/data files — always use `aicarmine_repo_read` with bounded `max_chars`
2. **Never use native `write_to_file`/`replace_in_file`** for HTML template updates — always use `aicarmine_repo_apply_patch` or `aicarmine_repo_code_apply_patch`
3. **Always seed quantum simulations deterministically** — record seeds in `aicarmine_project_memory_search`
4. **Always label classical approximations** — distinguish from quantum execution in output
5. **Always respect shot budgets** — default 1024 shots, expose in UI controls
6. **Never present classical approximation as quantum execution** — clear labeling required

---

## System Client Integration

This skill integrates with the AICarmine MCP-first enforcement system:

- PreToolUse hook detects quantum task context and emits MCP-first warnings
- PostToolUse hook validates that quantum engineering tasks used MCP tools
- TaskStart hook initializes MCP routing state with preferred quantum tool sequences
- MCP orchestrator classifies quantum query types and selects optimal MCP tools

All quantum/pre-quantum engineering operations MUST pass through these hooks to ensure compliance with MCP-first policy.