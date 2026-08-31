"""
bb84_runner.py
==============
Simulation orchestrator for the BB84 QKD simulator.

Public API
----------
run_simulation(config, verbose=True)  → SimulationResult
run_comparison(scenarios)             → List[SimulationResult]
PRESET_SCENARIOS                      - five canonical scenario list

Pipeline steps
--------------
1. Quantum Transmission  (Alice → [Eve] → Bob)
2. Key Sifting           (basis reconciliation)
3. QBER Estimation       (random sample with Wilson CI)
4. Key Distillation      (remove QBER sample bits)

University of Ruhuna - Dept. of Computer Engineering
MIT Licence - see LICENSE
"""

from __future__ import annotations

import random
import time
from typing import List, Optional, Tuple

import numpy as np

from bb84_config import SimulationConfig, SimulationResult
from bb84_core   import Alice, Bob, Eve, estimate_qber
from bb84_noise  import QuantumChannel, NoiseModelType


# ──────────────────────────────────────────────────────────────────────
# PRESET SCENARIOS
# ──────────────────────────────────────────────────────────────────────

PRESET_SCENARIOS: List[Tuple[str, SimulationConfig]] = [
    (
        "Ideal (no noise, no Eve)",
        SimulationConfig(n_qubits=600, seed=42, label="Ideal"),
    ),
    (
        "Eve - Partial Intercept (30 %)",
        SimulationConfig(n_qubits=600, seed=42,
                         eve_present=True, eve_intercept_prob=0.30,
                         label="Eve 30%"),
    ),
    (
        "Eve - Partial Intercept (50 %)",
        SimulationConfig(n_qubits=600, seed=42,
                         eve_present=True, eve_intercept_prob=0.50,
                         label="Eve 50%"),
    ),
    (
        "Eve - Full Intercept (100 %)",
        SimulationConfig(n_qubits=600, seed=42,
                         eve_present=True, eve_intercept_prob=1.0,
                         label="Eve 100%"),
    ),
    (
        "Channel Noise Only (p = 0.05)",
        SimulationConfig(n_qubits=600, seed=42,
                         noise_enabled=True, depolar_prob=0.05,
                         label="Noise p=0.05"),
    ),
    (
        "Eve (100 %) + Channel Noise",
        SimulationConfig(n_qubits=600, seed=42,
                         eve_present=True, eve_intercept_prob=1.0,
                         noise_enabled=True, depolar_prob=0.05,
                         label="Eve+Noise"),
    ),
]

PHASE3_SCENARIOS: List[Tuple[str, SimulationConfig]] = [
    (
        "Ideal (no noise)",
        SimulationConfig(n_qubits=500, seed=42, noise_model=NoiseModelType.IDEAL, label="Ideal"),
    ),
    (
        "Depolarising (p = 0.05)",
        SimulationConfig(n_qubits=500, seed=42, noise_model=NoiseModelType.DEPOLARIZING, depolar_prob=0.05, label="Depolarising p=0.05"),
    ),
    (
        "Amplitude Damping (T1 = 10 µs)",
        SimulationConfig(n_qubits=500, seed=42, noise_model=NoiseModelType.AMPLITUDE_DAMPING, t1_ns=10_000.0, gate_time_ns=50.0, label="Amplitude Damping"),
    ),
    (
        "Phase Damping (T2 = 8 µs)",
        SimulationConfig(n_qubits=500, seed=42, noise_model=NoiseModelType.PHASE_DAMPING, t2_ns=8_000.0, gate_time_ns=50.0, label="Phase Damping"),
    ),
    (
        "Combined T1+T2 (T1=10 µs, T2=8 µs)",
        SimulationConfig(n_qubits=500, seed=42, noise_model=NoiseModelType.COMBINED, t1_ns=10_000.0, t2_ns=8_000.0, gate_time_ns=50.0, label="Combined T1+T2"),
    ),
    (
        "Fibre Loss (50 km)",
        SimulationConfig(n_qubits=500, seed=42, noise_model=NoiseModelType.FIBRE_LOSS, channel_length_km=50.0, label="Fibre Loss 50 km"),
    ),
]


# ──────────────────────────────────────────────────────────────────────
# SINGLE SIMULATION
# ──────────────────────────────────────────────────────────────────────

def run_simulation(
    config:  SimulationConfig,
    verbose: bool = True,
    ldpc_reconciler=None,
) -> SimulationResult:
    """
    Run one complete BB84 simulation.

    Parameters
    ----------
    config  : SimulationConfig instance.
    verbose : print step-by-step progress and a result summary.

    Returns
    -------
    SimulationResult with keys, QBER, timing, and statistics.

    Example
    -------
    >>> from bb84_config import SimulationConfig
    >>> from bb84_runner import run_simulation
    >>> result = run_simulation(SimulationConfig(n_qubits=500, seed=0))
    """
    if verbose:
        _print_header(config)

    start = time.time()

    if config.seed is not None:
        random.seed(config.seed)
        np.random.seed(config.seed)

    # ── Instantiate parties ───────────────────────────────────────────
    alice   = Alice(config.n_qubits, seed=config.seed)
    bob     = Bob(config.n_qubits,   seed=config.seed)
    loss_rng = random.Random(config.seed if config.seed is not None else None)
    channel = QuantumChannel.from_config(config, loss_rng=loss_rng)
    eve = Eve(config.eve_intercept_prob, seed=config.seed) if config.eve_present else None

    # ── Step 1: Quantum Transmission ─────────────────────────────────
    if verbose:
        print(f"\n  [1/4] Quantum Transmission  ({config.n_qubits} qubits)...")
        print(f"        Channel : {channel.description}")

    lost_qubits: set = set()
    for i in range(config.n_qubits):
        if verbose and i % 200 == 0:
            print(f"        ↳ {i}/{config.n_qubits}", end="\r")
        qc = alice.prepare_qubit(i)
        if eve is not None:
            qc = eve.intercept(qc, i, channel)
        bit = bob.measure(qc, i, channel)
        if bit is None:
            lost_qubits.add(i)

    if verbose:
        print(f"        ↳ {config.n_qubits}/{config.n_qubits} transmitted  ({len(lost_qubits)} lost) ✓   ")

    # ── Step 2: Key Sifting ───────────────────────────────────────────
    if verbose:
        print(f"\n  [2/4] Key Sifting...")

    matching_indices = [
        i for i in range(config.n_qubits)
        if alice.bases[i] == bob.bases[i]
        and i not in lost_qubits
    ]
    alice_sifted = alice.sift_key(matching_indices)
    bob_sifted   = bob.sift_key(matching_indices)
    sift_rate    = len(matching_indices) / config.n_qubits

    if verbose:
        print(f"        ↳ {len(matching_indices)} bits retained  ({sift_rate:.1%}, expected ~50 % of arriving qubits)")

    # ── Step 3: QBER Estimation ───────────────────────────────────────
    if verbose:
        print(f"\n  [3/4] QBER Estimation  (sample fraction = {config.sample_fraction:.0%})...")

    if len(alice_sifted) == 0:
        if verbose:
            print("        ↳ No sifted bits (all photons lost) — skipping QBER.")
        from bb84_config import QBERResult
        empty_qber = QBERResult(qber=0.0, errors=0, sample_size=0, security_status="SECURE ok", confidence_low=0.0, confidence_high=1.0)
        return SimulationResult(config=config, n_transmitted=config.n_qubits, n_sifted=0, sifted_key_rate=0.0, qber_result=empty_qber, alice_final_key=[], bob_final_key=[], key_agreement_rate=0.0, eve_interception_rate=0.0, runtime_seconds=time.time()-start, n_lost=len(lost_qubits))

    qber_result = estimate_qber(
        alice_sifted,
        bob_sifted,
        config.sample_fraction,
        seed=(config.seed + 1000) if config.seed is not None else None,
    )

    if verbose:
        print(f"        ↳ QBER   : {qber_result.qber * 100:.2f} %  "
              f"(95 % CI [{qber_result.confidence_low * 100:.1f}, "
              f"{qber_result.confidence_high * 100:.1f}] %)")
        print(f"        ↳ Errors : {qber_result.errors} / {qber_result.sample_size}")
        print(f"        ↳ Status : {qber_result.security_status}")

    # ── Step 4: Key Distillation ──────────────────────────────────────
    s           = qber_result.sample_size
    alice_final = alice_sifted[s:]
    bob_final   = bob_sifted[s:]

    if verbose:
        print(f"\n  [4/4] Key Distillation  →  {len(alice_final)} bits")

    agreement = (
        sum(a == b for a, b in zip(alice_final, bob_final)) / len(alice_final)
        if alice_final else 0.0
    )
    eve_rate = (
        eve.intercepted_count / config.n_qubits if eve is not None else 0.0
    )

    result = SimulationResult(
        config=config,
        n_transmitted=config.n_qubits,
        n_sifted=len(matching_indices),
        sifted_key_rate=sift_rate,
        qber_result=qber_result,
        alice_final_key=alice_final,
        bob_final_key=bob_final,
        key_agreement_rate=agreement,
        eve_interception_rate=eve_rate,
        runtime_seconds=time.time() - start,
        n_lost=len(lost_qubits),
    )

    if verbose:
        _print_summary(result)

    return result


# ──────────────────────────────────────────────────────────────────────
# MULTI-SCENARIO COMPARISON
# ──────────────────────────────────────────────────────────────────────

def run_comparison(
    scenarios: Optional[List[Tuple[str, SimulationConfig]]] = None,
    phase3: bool = False,
) -> List[SimulationResult]:
    """
    Run a list of scenarios and print a compact comparison table.

    Parameters
    ----------
    scenarios : list of ``(name, SimulationConfig)`` pairs.
                Defaults to ``PRESET_SCENARIOS``.

    Returns
    -------
    List of SimulationResult objects in the same order as *scenarios*.

    Example
    -------
    >>> from bb84_runner import run_comparison, PRESET_SCENARIOS
    >>> results = run_comparison(PRESET_SCENARIOS)
    """
    if scenarios is None:
        scenarios = PHASE3_SCENARIOS if phase3 else PRESET_SCENARIOS

    max_name = max(len(name) for name, _ in scenarios)
    col      = max(max_name + 2, 40)

    print("\n" + "═" * (col + 42))
    print("  BB84 QKD – MULTI-SCENARIO COMPARISON")
    print("  University of Ruhuna – Dept. of Computer Engineering")
    print("═" * (col + 42))
    print(f"  {'Scenario':<{col}} {'QBER':>6}  {'Key':>5}  {'Lost':>5}  Status")
    print("  " + "─" * (col + 36))

    results: List[SimulationResult] = []
    for name, cfg in scenarios:
        r = run_simulation(cfg, verbose=False)
        results.append(r)
        lost_str = f"{r.n_lost:>4}" if r.n_lost > 0 else "   –"
        print(f"  {name:<{col}} {r.qber_result.qber * 100:>5.1f}%  "
              f"{r.key_length:>5}b  {lost_str}   {r.qber_result.security_status}")

    print("═" * (col + 42))
    return results


# ──────────────────────────────────────────────────────────────────────
# PRINT HELPERS
# ──────────────────────────────────────────────────────────────────────

def _print_header(config: SimulationConfig) -> None:
    w = 66
    print("\n" + "═" * w)
    print("  BB84 QKD SIMULATOR  –  Phase 3")
    print("  University of Ruhuna – Dept. of Computer Engineering")
    print("═" * w)
    print(f"  Label        : {config.label}")
    print(f"  Qubits       : {config.n_qubits}")
    if config.eve_present:
        print(f"  Eve Present  : True  (intercept p = {config.eve_intercept_prob})")
    else:
        print(f"  Eve Present  : False")

    if config.noise_model is not None:
        print(f"  Noise Model  : {config.noise_model}")
    elif config.noise_enabled:
        print(f"  Noise        : Depolarising  p = {config.depolar_prob}  (legacy)")
    else:
        print(f"  Noise        : Ideal (none)")

    print(f"  QBER Sample  : {config.sample_fraction:.0%} of sifted key")
    print(f"  Seed         : {config.seed}")
    print("═" * w)


def _print_summary(r: SimulationResult) -> None:
    w = 66
    qr = r.qber_result
    print(f"\n{'─' * w}")
    print("  RESULT SUMMARY")
    print(f"{'─' * w}")
    print(f"  Transmitted          : {r.n_transmitted} qubits")
    if r.n_lost > 0:
        print(f"  Lost (fibre)         : {r.n_lost} qubits  (survival {r.photon_survival_rate:.1%})")
    print(f"  After sifting        : {r.n_sifted} bits  ({r.sifted_key_rate:.1%})")
    print(f"  Final key length     : {r.key_length} bits")
    print(f"  Key generation rate  : {r.key_generation_rate:.4f} bits/qubit")
    print(f"  QBER                 : {qr.qber * 100:.2f} %")
    print(f"  95 % CI              : [{qr.confidence_low * 100:.1f} %, "
          f"{qr.confidence_high * 100:.1f} %]")
    print(f"  Security status      : {qr.security_status}")
    print(f"  Key agreement        : {r.key_agreement_rate * 100:.2f} %")
    if r.eve_interception_rate > 0:
        print(f"  Eve intercept rate   : {r.eve_interception_rate * 100:.1f} %")
    print(f"  Runtime              : {r.runtime_seconds:.2f} s")
    print(f"{'─' * w}")
    ak = r.alice_final_key[:30]
    bk = r.bob_final_key[:30]
    print(f"\n  Alice key (first {len(ak)}) : {ak}")
    print(f"  Bob   key (first {len(bk)}) : {bk}")
    print(f"  Keys fully match     : {r.keys_match}")
