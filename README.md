# BB84 QKD Simulator

A modular, reproducible Python simulator for the **BB84 Quantum Key Distribution protocol** that integrates depolarising channel noise, intercept-resend eavesdropping, and Wilson confidence-interval QBER estimation - deployable without prior Qiskit experience.


---

## Features

### Phase 1–2 
- **Alice & Bob** - qubit preparation and measurement in rectilinear / diagonal bases
- **Eve** - configurable intercept-resend attack (0 – 100 % interception rate)
- **Depolarising noise** - Qiskit Aer noise model with per-gate error probability
- **QBER estimation** - random sampling with 95 % Wilson confidence intervals
- **Security thresholds** - automatic SECURE / WARNING / ABORT classification
- **Publication-quality plots** - IEEE-style bar chart and QBER sweep figure

### Phase 3 
- **6 Advanced Noise Models** - Ideal, Depolarizing, Amplitude Damping, Phase Damping, Combined, Fibre Loss
- **Physical Decoherence Parameters** - T1 (relaxation), T2 (dephasing), gate time, fibre distance
- **Zero-Noise Extrapolation (ZNE)** - Quantum error mitigation via noise scaling and polynomial extrapolation
- **Bootstrap Confidence Intervals** - Statistical uncertainty quantification for ZNE estimates
- **Photon Loss Tracking** - Fibre-loss model with distance-dependent attenuation

### General
- **Fully reproducible** - all runs seeded; results are deterministic
- **Backward compatible** - existing Phase 1 code works unchanged

---

## Repository Structure

```
bb84-qkd-simulator/
├── bb84_config.py          # SimulationConfig, QBERResult, SimulationResult (Phase 3 extended)
├── bb84_core.py            # Alice, Bob, Eve, sift_keys, estimate_qber
├── bb84_runner.py          # run_simulation(), run_comparison(), PRESET_SCENARIOS, PHASE3_SCENARIOS
├── bb84_noise.py           # [NEW] QuantumChannel, NoiseModelType, advanced noise models
├── bb84_zne.py             # [NEW] Zero-Noise Extrapolation orchestration & analysis
├── bb84_plots.py           # plot_comparison(), plot_qber_vs_intercept_rate()
├── examples/
│   ├── bb84_simulation.ipynb   # Full demonstration notebook (8 sections)
│   └── run_all_scenarios.py    # Run all presets from the command line
├── tests/
│   └── test_zne_integration.py # [NEW] ZNE regression test
├── figures/                # Auto-created; plot outputs saved here
├── requirements.txt
├── LICENSE
└── README.md
```

---

## Installation

**Python 3.9 – 3.12 is required.**

```bash
# 1. Clone the repository
git clone https://github.com/nemal2/bb84-qkd-simulator.git
cd bb84-qkd-simulator

# 2. (Recommended) Create a virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Quick Start

### Run all preset scenarios (single command)

```bash
python examples/run_all_scenarios.py
```

This prints a comparison table and saves two figures to `figures/`.

### Interactive notebook

```bash
jupyter notebook examples/bb84_simulation.ipynb
```

### Python API

```python
from bb84_config import SimulationConfig
from bb84_runner import run_simulation, run_comparison, PRESET_SCENARIOS

# Single run - verbose
result = run_simulation(SimulationConfig(n_qubits=600, seed=42))

# Multi-scenario comparison table
results = run_comparison(PRESET_SCENARIOS)
```

### Phase 3: Advanced Noise & ZNE

```python
from bb84_config import SimulationConfig
from bb84_noise import NoiseModelType
from bb84_runner import run_simulation, run_comparison, PHASE3_SCENARIOS
from bb84_zne import run_zne_analysis

# Run Phase 3 scenario (e.g., amplitude damping)
cfg = SimulationConfig(
    n_qubits=500,
    noise_model=NoiseModelType.AMPLITUDE_DAMPING,
    t1_ns=10_000.0,
    gate_time_ns=50.0
)
result = run_simulation(cfg, verbose=True)

# Compare all Phase 3 scenarios
results = run_comparison(phase3=True)

# Run Zero-Noise Extrapolation analysis
zne_result = run_zne_analysis(
    cfg,
    f_scales=[1.0, 1.5, 2.0],
    n_seeds=5,
    method='linear'
)
print(f"Ideal QBER estimate: {zne_result.recommended_estimate:.4f}%")
```

---

## Preset Scenarios

| # | Scenario | n_qubits | Eve | Noise | Expected QBER |
|---|----------|----------|-----|-------|---------------|
| 1 | Ideal (no noise, no Eve) | 600 | - | - | ~0 % |
| 2 | Eve - 30 % intercept | 600 | 30 % | - | ~7.5 % |
| 3 | Eve - 50 % intercept | 600 | 50 % | - | ~12.5 % |
| 4 | Eve - 100 % intercept | 600 | 100 % | - | ~25 % |
| 5 | Channel noise only (p = 0.05) | 600 | - | depolar 5 % | ~5 % |
| 6 | Eve (100 %) + noise | 600 | 100 % | depolar 5 % | >25 % |

---

## Phase 3 Scenarios (Advanced Noise Models)

| # | Scenario | n_qubits | Noise Model | Parameters | Features |
|---|----------|----------|-------------|------------|----------|
| 1 | Ideal (no noise) | 500 | Ideal | - | Baseline, ~0 % QBER |
| 2 | Depolarising (p = 0.05) | 500 | Depolarizing | depolar_prob=0.05 | Bit-flip errors |
| 3 | Amplitude Damping | 500 | Amplitude Damping | T1=10 µs, gate_time=50 ns | Energy relaxation |
| 4 | Phase Damping | 500 | Phase Damping | T2=8 µs, gate_time=50 ns | Dephasing (T2 effects) |
| 5 | Combined T1+T2 | 500 | Combined | T1=10 µs, T2=8 µs | Realistic decoherence |
| 6 | Fibre Loss (50 km) | 500 | Fibre Loss | channel_length_km=50 | Photon loss over distance |

Use `run_comparison(phase3=True)` to execute all Phase 3 scenarios.

---

## Security Thresholds

| QBER | Status | Meaning |
|------|--------|---------|
| < 5 % | **SECURE** | Safe to use key |
| 5 – 11 % | **WARNING** | Possible eavesdropping; investigate |
| ≥ 11 % | **ABORT** | Channel compromised; discard key |

---

## BB84 Protocol - Brief Overview

```
Alice                  Quantum Channel              Bob
  │                                                  │
  │── prepare qubit (bit, basis) ──[Eve?]──────────> │ measure (random basis)
  │                                                  │
  │<════ classical channel: compare BASES only ═════>│
  │                                                  │
  │  discard qubits where bases differ (~50 %)       │
  │                                                  │
  │<═ publicly reveal random sample → estimate QBER ═│
  │                                                  │
  │  QBER < 11% → use remaining bits as secret key   │
```

**Why does Eve get caught?**  
Eve must guess Alice's basis. She is wrong ~50 % of the time. When she
measures in the wrong basis and re-sends, she introduces a 50 % error
on that qubit. Net effect: each intercepted qubit has a 25 % probability
of causing a QBER error → QBER ≈ 0.25 × p_intercept.

---

## Phase 3: Advanced Noise Models & Zero-Noise Extrapolation

### Quantum Noise Channels

Phase 3 introduces 6 physically motivated noise models via **Qiskit Aer**:

| Model | Description | Use Case | Parameters |
|-------|-------------|----------|------------|
| **Ideal** | No noise | Baseline reference | - |
| **Depolarizing** | Random bit flips per gate | Generic errors | `depolar_prob` |
| **Amplitude Damping** | Energy relaxation to ground state | Transmon qubits | `t1_ns`, `gate_time_ns` |
| **Phase Damping** | Pure dephasing (no energy loss) | Spin qubits | `t2_ns`, `gate_time_ns` |
| **Combined** | T1 + T2 decoherence simultaneously | Realistic hardware | `t1_ns`, `t2_ns`, `gate_time_ns` |
| **Fibre Loss** | Photon attenuation over optical channel | Long-distance QKD | `channel_length_km` |

**Physical Constraints:**
- Bloch sphere constraint: T2 ≤ 2×T1 (enforced at configuration time)
- Gate time ≥ 0 (physical causality)

### Zero-Noise Extrapolation (ZNE)

ZNE is a **quantum error mitigation technique** that scales noise to higher levels, fits a curve through the noisy results, and extrapolates back to zero noise to estimate the ideal result.

**How it works:**

1. Run simulations at multiple noise scales: f ∈ {1.0, 1.5, 2.0, ...}
2. For each scale, apply noise scaling: depolar_prob_scaled = f × depolar_prob
3. Fit polynomial to (f, QBER) curve: QBER(f) = a + b×f + c×f²
4. Extrapolate to f→0 to estimate ideal QBER: QBER(0) = a

**Supported fitting methods:**
- **Linear**: Simple intercept (recommended for small scales)
- **Exponential**: Realistic error growth (for larger scales)
- **Quadratic**: Higher-order polynomial fitting

**Usage:**

```python
from bb84_config import SimulationConfig
from bb84_noise import NoiseModelType
from bb84_zne import run_zne_analysis

cfg = SimulationConfig(
    n_qubits=200,
    noise_model=NoiseModelType.DEPOLARIZING,
    depolar_prob=0.02
)

# Run ZNE analysis with 3 noise scales, 5 trials each
zne_result = run_zne_analysis(
    cfg,
    f_scales=[1.0, 1.5, 2.0],
    n_seeds=5,
    method='linear',
    bootstrap=True  # Compute 95% CI
)

print(f"Ideal QBER estimate: {zne_result.recommended_estimate:.4f}%")
print(f"Linear fit: a={zne_result.linear_intercept:.4f}, b={zne_result.linear_slope:.4f}")
```

---

## Configuration Reference

### Phase 1 (Legacy)

```python
SimulationConfig(
    # Core
    n_qubits        = 1000,    # qubits Alice transmits
    seed            = 42,      # RNG seed (None = random)
    label           = "Run",   # name for plots / tables
    sample_fraction = 0.15,    # fraction of sifted key used for QBER
    
    # Eve attack
    eve_present     = False,   # enable intercept-resend attack
    eve_intercept_prob = 1.0,  # fraction Eve intercepts (0–1)
    
    # Phase 1 noise (legacy)
    noise_enabled   = False,   # enable depolarising noise
    depolar_prob    = 0.01,    # per-gate depolarising probability
)
```

### Phase 3 (NEW)

```python
SimulationConfig(
    # ... all Phase 1 fields above, plus:
    
    # Phase 3 noise model selector (optional; omit for Phase 1 behavior)
    noise_model     = NoiseModelType.DEPOLARIZING,  # or IDEAL, AMPLITUDE_DAMPING, PHASE_DAMPING, COMBINED, FIBRE_LOSS
    
    # T1 relaxation time (amplitude damping / combined models)
    t1_ns           = 10_000.0,    # nanoseconds; default 10 µs (transmon)
    
    # T2 dephasing time (phase damping / combined models)
    t2_ns           = 8_000.0,     # nanoseconds; default 8 µs; must satisfy T2 <= 2*T1
    
    # Single-qubit gate duration
    gate_time_ns    = 50.0,        # nanoseconds
    
    # Fibre-optic channel length (fibre loss model only)
    channel_length_km = 0.0,       # kilometres; affects photon survival rate
)
```

**Example Phase 3 usage:**

```python
# Amplitude damping (T1 relaxation)
cfg = SimulationConfig(
    n_qubits=500,
    noise_model=NoiseModelType.AMPLITUDE_DAMPING,
    t1_ns=10_000.0,
    gate_time_ns=50.0
)

# Fibre loss over 50 km
cfg = SimulationConfig(
    n_qubits=500,
    noise_model=NoiseModelType.FIBRE_LOSS,
    channel_length_km=50.0
)
```

---

## Generating Plots

```python
from bb84_runner import run_comparison, PRESET_SCENARIOS
from bb84_plots  import plot_comparison, plot_qber_vs_intercept_rate

# Bar chart of all preset scenarios
results = run_comparison(PRESET_SCENARIOS)
plot_comparison(PRESET_SCENARIOS, results,
                subtitle="BB84 QKD - Scenario Comparison")

# QBER vs Eve sweep (theory vs simulation)
plot_qber_vs_intercept_rate(n_qubits=600, steps=10)
```

---

## Dependencies

| Package | Version | Purpose | Phase |
|---------|---------|---------|-------|
| `qiskit` | ≥ 1.0 | Quantum circuit construction | 1–3 |
| `qiskit-aer` | ≥ 0.14 | Noisy quantum simulation | 3 |
| `numpy` | ≥ 1.24 | Numerical operations | 1–3 |
| `scipy` | ≥ 1.10 | Curve fitting (ZNE) | 3 |
| `matplotlib` | ≥ 3.7 | Plots | 1–3 |
| `pytest` | ≥ 7.0 | Testing | 3 (optional) |
| `jupyter` | ≥ 1.0 | Notebook | All (optional) |

All dependencies are specified in `requirements.txt` and installed by `pip install -r requirements.txt`.

---

## Citation

If you use this simulator in academic work, please cite:

```bibtex
@software{bb84_qkd_simulator,
  author    = {University of Ruhuna, Dept. of Computer Engineering},
  title     = {BB84 QKD Simulator},
  year      = {2026},
  url       = {https://github.com/nemal2/bb84-qkd-simulator},
  doi       = {10.5281/zenodo.20584084},
  license   = {MIT}
}
```

---

## Licence

MIT - see [LICENSE](LICENSE).
