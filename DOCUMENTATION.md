# BB84 QKD Simulator — Documentation

This document explains what this project is, the basic idea behind it, and how the
code works. It is written for someone who is new to the project and wants a plain,
non-technical starting point before reading the source code.

---

## 1. What is this project?

This is a Python simulator for **BB84**, the first and most well-known protocol for
**Quantum Key Distribution (QKD)**. QKD is a method that lets two people (traditionally
called Alice and Bob) agree on a secret encryption key using quantum physics, in a way
that lets them detect whether anyone (Eve) was eavesdropping on the transmission.

This project does not use real quantum hardware. It uses **Qiskit** (an open-source
quantum computing library) to simulate qubits on a normal computer, so the whole
protocol can be studied, tested, and visualized without needing access to a quantum
computer.

The simulator also goes beyond the basic protocol and adds:
- Realistic noise models (imperfect quantum channels)
- An eavesdropper (Eve) that can be turned on or off
- Statistical tools to detect eavesdropping
- Error mitigation (Zero-Noise Extrapolation)
- Error correction (LDPC and GRAND) so Alice and Bob's keys actually match

---

## 2. The BB84 protocol, in plain terms

BB84 lets Alice send Bob a secret key using single photons (qubits) instead of
classical bits. The key idea is that measuring a quantum state disturbs it, so if
someone eavesdrops, they inevitably introduce detectable errors.

Basic steps:

1. **Alice** picks a random bit (0 or 1) and a random basis (rectilinear or diagonal)
   for each qubit, and sends the encoded qubit to Bob.
2. **Bob** measures each qubit using his own randomly chosen basis.
3. **Alice and Bob** publicly compare (over a normal, non-secret channel) which basis
   they used for each qubit — not the bit values themselves. Whenever their bases
   match, the bit is kept. This step is called **sifting**, and on average keeps
   about 50% of the transmitted qubits.
4. Alice and Bob sacrifice a small random sample of the sifted key and compare those
   bits directly. The error rate in this sample is the **QBER** (Quantum Bit Error
   Rate).
5. If QBER is low, the channel is considered secure and the remaining (unsampled)
   bits become the final shared secret key. If QBER is high, it suggests
   eavesdropping or a very noisy channel, and the key is discarded.

### Why does eavesdropping get caught?

If Eve (the eavesdropper) intercepts a qubit, she does not know which basis Alice
used, so she has to guess. About half the time she guesses wrong, which disturbs the
qubit's state. When Eve then re-sends a qubit to Bob, this disturbance shows up as
extra errors. On average, each qubit Eve intercepts has a 25% chance of causing a
wrong bit at Bob's end. So:

```
Expected QBER ≈ 0.25 × (fraction of qubits Eve intercepts)
```

This is why comparing a small sample and measuring QBER is enough to reveal Eve's
presence, without needing to know anything about how she attacked.

### Security thresholds used in this simulator

| QBER          | Status  | Meaning                                   |
|---------------|---------|--------------------------------------------|
| below 5%      | SECURE  | Safe to use the key                        |
| 5% – 11%      | WARNING | Possible eavesdropping; investigate further|
| 11% or higher | ABORT   | Channel is compromised; discard the key    |

---

## 3. Project structure

```
bb84-qkd-simulator/
├── bb84_config.py          Configuration and result data structures
├── bb84_core.py             Alice, Bob, Eve, and the basic quantum channel
├── bb84_noise.py            Advanced, physically realistic noise models
├── bb84_runner.py           Orchestrates a full simulation run, start to finish
├── bb84_zne.py               Zero-Noise Extrapolation (error mitigation)
├── bb84_reconciliation.py   LDPC-based error correction
├── bb84_grand.py             GRAND-based error correction
├── bb84_plots.py             Chart generation for results
├── examples/                Example scripts and a Jupyter notebook
├── tests/                    Automated tests
├── figures/                  Output folder for generated plots
├── requirements.txt          Python package dependencies
└── README.md                 Project overview and quick-start guide
```

Each file has one clear responsibility, described below.

---

## 4. How the code is organized

### bb84_config.py — Settings and results

Defines the data structures used everywhere else:

- **SimulationConfig** — a single object holding every setting for one simulation
  run: how many qubits to send, whether Eve is present, which noise model to use,
  whether to run error correction, and so on. Sensible defaults mean you can create
  one with no arguments at all: `SimulationConfig()`.
- **QBERResult** — the outcome of the QBER estimation step (the error rate, a
  confidence interval, and a security status).
- **SimulationResult** — the full outcome of one simulation run (final keys, key
  length, QBER result, timing, etc).
- **LDPCReconciliationResult** / **LDPCBlockSummary** — results from the optional
  LDPC error-correction step.

### bb84_core.py — The people and the channel

This is where the three participants of the protocol are implemented:

- **Alice** — generates random bits and random bases, and builds the quantum circuit
  (qubit) representing each one.
- **Bob** — measures each incoming qubit using his own randomly chosen basis.
- **Eve** — an optional eavesdropper. If enabled, she intercepts a configurable
  fraction of qubits, measures them in a random basis, and re-sends a freshly
  prepared qubit to Bob (the "intercept-resend" attack).
- **QuantumChannel** — the basic (legacy) simulated channel, which can optionally
  apply depolarizing noise using Qiskit Aer.

It also defines two important functions used for classical post-processing:

- **sift_keys()** — compares Alice's and Bob's bases and returns the positions where
  they matched.
- **estimate_qber()** — samples a fraction of the sifted key, compares it, and
  computes the QBER together with a 95% confidence interval and a security status.

### bb84_noise.py — Realistic channel noise

Real quantum hardware is never perfect. This file adds several physically motivated
noise models on top of the basic depolarizing model:

| Model              | What it represents                                  |
|--------------------|------------------------------------------------------|
| Ideal              | No noise (perfect channel, used as a baseline)        |
| Depolarizing       | Random bit flips, a generic error model               |
| Amplitude Damping  | Energy loss over time (characterized by T1)           |
| Phase Damping      | Loss of phase information over time (characterized by T2) |
| Combined           | Amplitude and phase damping together (more realistic) |
| Fibre Loss         | Photons get lost over long optical fibre distances     |

The class **QuantumChannel** in this file builds the correct Qiskit Aer noise model
based on the chosen `noise_model` and its parameters (T1, T2, gate time, fibre
length).

### bb84_runner.py — Running a full simulation

This is the main entry point most users will call. **run_simulation(config)** runs
one complete BB84 exchange, step by step:

1. **Quantum Transmission** — Alice prepares each qubit, Eve optionally intercepts
   it, and Bob measures it through the chosen noisy channel.
2. **Key Sifting** — bases are compared and mismatched qubits are discarded.
3. **QBER Estimation** — a sample is compared to estimate the error rate and decide
   SECURE / WARNING / ABORT.
4. **Key Distillation** — the sampled bits are removed, leaving the final shared key.

It also provides **run_comparison()**, which runs several scenarios back-to-back and
prints a summary table, plus two ready-made scenario lists:

- **PRESET_SCENARIOS** — basic scenarios (ideal, Eve at different intercept rates,
  noise only, Eve + noise).
- **PHASE3_SCENARIOS** — one scenario per advanced noise model.

### bb84_zne.py — Zero-Noise Extrapolation (ZNE)

ZNE is a technique for estimating what the QBER *would have been* on a perfect,
noiseless channel, using only noisy simulation results. The idea:

1. Deliberately run the simulation at several noise levels (for example, 1x, 1.5x,
   2x the normal noise).
2. Record the QBER at each level.
3. Fit a curve through these points (linear, quadratic, or exponential).
4. Extrapolate the curve back to "zero noise" to estimate the ideal QBER.

The main entry point is **run_zne_analysis()**, which returns a **ZNEResult**
containing the fitted curve, the extrapolated estimate, and (optionally) a bootstrap
confidence interval.

### bb84_reconciliation.py — LDPC error correction

BB84 by itself only *detects* how noisy the channel was — it does not fix the errors
in the key Alice and Bob keep. This file implements **information reconciliation**
using LDPC (Low-Density Parity-Check) codes, so Bob's key can be corrected to match
Alice's:

1. Alice computes a short "syndrome" from her key and publicly sends it to Bob.
2. Bob uses the syndrome and a belief-propagation decoding algorithm to figure out
   where the errors likely are and fix them.
3. The number of syndrome bits published is tracked, since this information must
   later be discarded from the key length (an eavesdropper could have seen it too).

The main class is **LDPCReconciler**, and **reconcile_full_key()** runs this process
over an entire key, block by block.

### bb84_grand.py — GRAND error correction

GRAND (Guessing Random Additive Noise Decoding) is a different, simpler approach to
error correction. Instead of using a formal code structure like LDPC, it guesses
possible error patterns starting from the most likely (fewest bit flips) and checks
each guess until one passes validation. This file implements **GRANDDecoder** and a
convenience function **correct_sifted_key_with_grand()** for using it on a BB84 key.

### bb84_plots.py — Charts

Generates two kinds of plots used to visualize results:

- **plot_comparison()** — a bar chart comparing QBER across several scenarios, with
  confidence-interval error bars and SECURE/WARNING/ABORT coloring.
- **plot_qber_vs_intercept_rate()** — a line chart sweeping Eve's intercept
  probability from 0% to 100%, comparing simulated QBER against the 0.25 × p
  theoretical prediction.

Plots are saved to the `figures/` folder as PNG images.

---

## 5. Installation

Requires Python 3.9–3.12.

```bash
git clone https://github.com/nemal2/bb84-qkd-simulator.git
cd bb84-qkd-simulator

python -m venv .venv
.venv\Scripts\activate        # on Windows
# source .venv/bin/activate   # on macOS/Linux

pip install -r requirements.txt
```

---

## 6. Running the simulator

### Quickest way: run all preset scenarios

```bash
python examples/run_all_scenarios.py
```

This prints a comparison table to the console and saves two chart images into
`figures/`.

### Interactive notebook

```bash
jupyter notebook examples/bb84_simulation.ipynb
```

### From your own Python code

```python
from bb84_config import SimulationConfig
from bb84_runner import run_simulation

# A single, simple run: 600 qubits, no noise, no eavesdropper
result = run_simulation(SimulationConfig(n_qubits=600, seed=42))

print(result.qber_result.qber)              # the measured error rate
print(result.qber_result.security_status)   # SECURE / WARNING / ABORT
print(result.key_length)                    # length of the final shared key
```

To add an eavesdropper:

```python
cfg = SimulationConfig(n_qubits=600, eve_present=True, eve_intercept_prob=0.5)
result = run_simulation(cfg)
```

To add channel noise:

```python
from bb84_noise import NoiseModelType

cfg = SimulationConfig(
    n_qubits=500,
    noise_model=NoiseModelType.AMPLITUDE_DAMPING,
    t1_ns=10_000.0,
)
result = run_simulation(cfg)
```

---

## 7. A typical end-to-end flow

1. Choose a `SimulationConfig` (how many qubits, whether Eve is present, which noise
   model, whether to run LDPC reconciliation).
2. Call `run_simulation(config)`. Internally this creates Alice, Bob, an optional
   Eve, and a `QuantumChannel`, then runs the four steps described in section 4
   (transmission, sifting, QBER estimation, distillation).
3. Inspect the returned `SimulationResult` — key length, QBER, security status,
   whether Alice's and Bob's keys actually match.
4. Optionally, run `run_zne_analysis()` to estimate the ideal (zero-noise) QBER, or
   run LDPC/GRAND reconciliation to correct any remaining mismatches between Alice's
   and Bob's keys.
5. Optionally, use `bb84_plots.py` to turn one or more results into charts.

---

## 8. Where to go next

- `README.md` in the project root has more detail on configuration options, preset
  scenario tables, and dependency versions.
- `examples/bb84_simulation.ipynb` is the best place to see the whole pipeline run
  step by step with explanations.
- `tests/test_zne_integration.py` shows a working example of the ZNE analysis.
