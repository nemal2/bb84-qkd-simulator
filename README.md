# BB84 QKD Simulator

A modular, reproducible Python simulator for the **BB84 Quantum Key Distribution protocol** that integrates depolarising channel noise, intercept-resend eavesdropping, and Wilson confidence-interval QBER estimation - deployable without prior Qiskit experience.

**University of Ruhuna - Dept. of Computer Engineering**  
MIT Licence

---

## Features

- **Alice & Bob** - qubit preparation and measurement in rectilinear / diagonal bases
- **Eve** - configurable intercept-resend attack (0 – 100 % interception rate)
- **Depolarising noise** - Qiskit Aer noise model with per-gate error probability
- **QBER estimation** - random sampling with 95 % Wilson confidence intervals
- **Security thresholds** - automatic SECURE / WARNING / ABORT classification
- **Publication-quality plots** - IEEE-style bar chart and QBER sweep figure
- **Fully reproducible** - all runs seeded; results are deterministic

---

## Repository Structure

```
bb84-qkd-simulator/
├── bb84_config.py          # SimulationConfig, QBERResult, SimulationResult
├── bb84_core.py            # Alice, Bob, Eve, QuantumChannel, sift_keys, estimate_qber
├── bb84_runner.py          # run_simulation(), run_comparison(), PRESET_SCENARIOS
├── bb84_plots.py           # plot_comparison(), plot_qber_vs_intercept_rate()
├── examples/
│   ├── bb84_simulation.ipynb   # Full demonstration notebook (8 sections)
│   └── run_all_scenarios.py    # Run all presets from the command line
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

## Configuration Reference

```python
SimulationConfig(
    n_qubits        = 1000,    # qubits Alice transmits
    seed            = 42,      # RNG seed (None = random)
    label           = "Run",   # name for plots / tables
    sample_fraction = 0.15,    # fraction of sifted key used for QBER
    eve_present     = False,   # enable intercept-resend attack
    eve_intercept_prob = 1.0,  # fraction Eve intercepts (0–1)
    noise_enabled   = False,   # enable depolarising noise
    depolar_prob    = 0.01,    # per-gate depolarising probability
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

| Package | Version | Purpose |
|---------|---------|---------|
| `qiskit` | ≥ 1.0 | Quantum circuit construction |
| `qiskit-aer` | ≥ 0.14 | Noisy quantum simulation |
| `numpy` | ≥ 1.24 | Numerical operations |
| `matplotlib` | ≥ 3.7 | Plots |
| `jupyter` | ≥ 1.0 | Notebook (optional) |

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
