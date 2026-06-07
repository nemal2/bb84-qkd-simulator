"""
bb84_core.py
============
Quantum parties and classical post-processing for BB84 QKD.

Classes
-------
Alice           - qubit preparation
Bob             - qubit measurement
Eve             - intercept-resend attack
QuantumChannel  - depolarising noise model backed by Qiskit Aer

Functions
---------
sift_keys()     - basis reconciliation (classical post-processing)
estimate_qber() - QBER with 95 % Wilson confidence interval

Encoding table
--------------
bit=0, basis=0  →  |0⟩   (no gates)
bit=1, basis=0  →  |1⟩   (X gate)
bit=0, basis=1  →  |+⟩   (H gate)
bit=1, basis=1  →  |−⟩   (X → H)

Bases: 0 = Rectilinear (+),  1 = Diagonal (×)

University of Ruhuna - Dept. of Computer Engineering
MIT Licence - see LICENSE
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional

import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error

from bb84_config import QBERResult


# ──────────────────────────────────────────────────────────────────────
# QUANTUM CHANNEL
# ──────────────────────────────────────────────────────────────────────

class QuantumChannel:
    """
    Depolarising quantum channel backed by Qiskit Aer.

    Parameters
    ----------
    noise_enabled : bool
        False → ideal (noiseless) simulation.
    depolar_prob  : float
        Depolarising error probability per gate (0.0–1.0).

    Example
    -------
    >>> ch = QuantumChannel(noise_enabled=True, depolar_prob=0.05)
    >>> bit = ch.run_circuit(qc)           # returns 0 or 1
    """

    def __init__(
        self,
        noise_enabled: bool = False,
        depolar_prob:  float = 0.01,
    ):
        self.noise_enabled = noise_enabled
        self.depolar_prob  = depolar_prob
        self._simulator    = self._build_simulator()

    def run_circuit(
        self,
        qc: QuantumCircuit,
        shot_seed: Optional[int] = None,
    ) -> int:
        """
        Simulate *qc* through this channel and return the measured bit (0 or 1).

        Parameters
        ----------
        qc        : single-qubit circuit with one measurement.
        shot_seed : per-shot seed for reproducibility without collapsing
                    all outcomes to the same value.
        """
        kwargs = {"shots": 1}
        if shot_seed is not None:
            kwargs["seed_simulator"] = int(shot_seed) % (2 ** 31)
        job    = self._simulator.run(transpile(qc, self._simulator), **kwargs)
        counts = job.result().get_counts()
        return int(list(counts.keys())[0])

    @property
    def description(self) -> str:
        """Short human-readable summary."""
        if not self.noise_enabled:
            return "Ideal channel (no noise)"
        return f"Depolarising  p = {self.depolar_prob}"

    def _build_simulator(self) -> AerSimulator:
        if not self.noise_enabled:
            return AerSimulator()
        nm  = NoiseModel()
        err = depolarizing_error(self.depolar_prob, 1)
        nm.add_all_qubit_quantum_error(err, ["x", "h", "id"])
        return AerSimulator(noise_model=nm)


# ──────────────────────────────────────────────────────────────────────
# ALICE - qubit preparation
# ──────────────────────────────────────────────────────────────────────

class Alice:
    """
    Alice randomly selects bits and bases, then encodes each bit as a qubit.

    Parameters
    ----------
    n_qubits : number of qubits to prepare.
    seed     : RNG seed (None → random).
    """

    def __init__(self, n_qubits: int, seed: Optional[int] = None):
        self.n_qubits = n_qubits
        rng = np.random.default_rng(seed)
        self.bits:  List[int] = rng.integers(0, 2, n_qubits).tolist()
        self.bases: List[int] = rng.integers(0, 2, n_qubits).tolist()

    def prepare_qubit(self, index: int) -> QuantumCircuit:
        """Return a 1-qubit circuit encoding ``bits[index]`` in ``bases[index]``."""
        qc = QuantumCircuit(1, 1, name=f"A{index}")
        if self.bits[index] == 1:
            qc.x(0)
        if self.bases[index] == 1:
            qc.h(0)
        return qc

    def sift_key(self, matching_indices: List[int]) -> List[int]:
        """Alice's bits at positions where bases agreed with Bob's."""
        return [self.bits[i] for i in matching_indices]


# ──────────────────────────────────────────────────────────────────────
# BOB - qubit measurement
# ──────────────────────────────────────────────────────────────────────

class Bob:
    """
    Bob randomly selects a measurement basis for each qubit.

    When his basis matches Alice's the outcome is deterministic;
    otherwise it is uniformly random (superposition collapse).

    Parameters
    ----------
    n_qubits : must equal Alice's n_qubits.
    seed     : RNG seed (offset internally so bases are independent of Alice's).
    """

    def __init__(self, n_qubits: int, seed: Optional[int] = None):
        self.n_qubits = n_qubits
        rng = np.random.default_rng(None if seed is None else seed + 99)
        self.bases: List[int]                  = rng.integers(0, 2, n_qubits).tolist()
        self.measured_bits: List[Optional[int]] = [None] * n_qubits
        self._shot_seed_base = (seed * 7919) if seed is not None else None

    def measure(
        self,
        qc:      QuantumCircuit,
        index:   int,
        channel: QuantumChannel,
    ) -> int:
        """
        Measure qubit *index* in Bob's chosen basis.

        Returns the measured bit and stores it in ``measured_bits[index]``.
        """
        meas_qc = qc.copy()
        if self.bases[index] == 1:
            meas_qc.h(0)          # rotate to diagonal basis before measuring
        meas_qc.measure(0, 0)
        shot_seed = (self._shot_seed_base + index) if self._shot_seed_base is not None else None
        bit = channel.run_circuit(meas_qc, shot_seed=shot_seed)
        self.measured_bits[index] = bit
        return bit

    def sift_key(self, matching_indices: List[int]) -> List[int]:
        """Bob's measured bits at positions where bases agreed with Alice's."""
        return [self.measured_bits[i] for i in matching_indices]


# ──────────────────────────────────────────────────────────────────────
# EVE - intercept-resend attack
# ──────────────────────────────────────────────────────────────────────

class Eve:
    """
    Intercept-resend eavesdropper.

    Eve intercepts each qubit with probability ``intercept_prob``,
    measures in a random basis, then forwards a freshly prepared qubit
    to Bob.  At full interception (p = 1.0) the expected QBER is 25 %.

    Parameters
    ----------
    intercept_prob : fraction of qubits Eve intercepts (0.0–1.0).
    seed           : RNG seed.
    """

    def __init__(
        self,
        intercept_prob: float = 1.0,
        seed:           Optional[int] = None,
    ):
        self.intercept_prob    = intercept_prob
        self._rng              = np.random.default_rng(None if seed is None else seed + 200)
        self.intercepted_count = 0
        self._eve_bases: Dict[int, int] = {}
        self._eve_bits:  Dict[int, int] = {}
        self._shot_seed_base = (seed * 6271) if seed is not None else None

    def intercept(
        self,
        qc:      QuantumCircuit,
        index:   int,
        channel: QuantumChannel,
    ) -> QuantumCircuit:
        """
        Optionally intercept qubit *index*.

        Returns the original circuit (pass-through) or a freshly
        prepared circuit encoding Eve's measured result.
        """
        if random.random() > self.intercept_prob:
            return qc                          # Eve passes this qubit through

        self.intercepted_count += 1

        # Step 1: pick a random basis
        eve_base = int(self._rng.integers(0, 2))
        self._eve_bases[index] = eve_base

        # Step 2: measure Alice's qubit in Eve's basis
        meas_qc = qc.copy()
        if eve_base == 1:
            meas_qc.h(0)
        meas_qc.measure(0, 0)
        shot_seed = (
            (self._shot_seed_base + index)
            if self._shot_seed_base is not None else None
        )
        measured_bit = channel.run_circuit(meas_qc, shot_seed=shot_seed)
        self._eve_bits[index] = measured_bit

        # Step 3: re-prepare qubit from Eve's result
        new_qc = QuantumCircuit(1, 1, name=f"E{index}")
        if measured_bit == 1:
            new_qc.x(0)
        if eve_base == 1:
            new_qc.h(0)

        return new_qc                          # Bob receives this, not Alice's

    @property
    def stats(self) -> dict:
        """Summary statistics of Eve's interception activity."""
        return {
            "intercepted": self.intercepted_count,
            "bases":       self._eve_bases,
            "bits":        self._eve_bits,
        }


# ──────────────────────────────────────────────────────────────────────
# KEY SIFTING  (classical post-processing)
# ──────────────────────────────────────────────────────────────────────

def sift_keys(alice_bases: List[int], bob_bases: List[int]) -> List[int]:
    """
    Publicly compare bases (NOT bits) and return matching indices.

    Expected retention: ~50 % of transmitted qubits.

    Parameters
    ----------
    alice_bases, bob_bases : basis lists from Alice and Bob.

    Returns
    -------
    List of qubit indices where both parties chose the same basis.
    """
    return [i for i in range(len(alice_bases)) if alice_bases[i] == bob_bases[i]]


# ──────────────────────────────────────────────────────────────────────
# QBER ESTIMATION  (classical post-processing)
# ──────────────────────────────────────────────────────────────────────

def estimate_qber(
    alice_key:       List[int],
    bob_key:         List[int],
    sample_fraction: float = 0.15,
    seed:            Optional[int] = None,
) -> QBERResult:
    """
    Publicly compare a random sample of the sifted key to estimate QBER.

    The sampled bits are *consumed* (revealed) and not used in the final key.

    Security thresholds (BB84 standard)
    ------------------------------------
    QBER <  5 %          → ``SECURE ok``
    5 % ≤ QBER < 11 %    → ``WARNING ``   (eavesdropping possible)
    QBER ≥ 11 %          → ``ABORT x``    (channel compromised - abort)

    Parameters
    ----------
    alice_key, bob_key : sifted key lists (equal length).
    sample_fraction    : fraction of the sifted key to sample (default 15 %).
    seed               : RNG seed for reproducible sampling.

    Returns
    -------
    QBERResult with QBER estimate, error count, sample size,
    security status, and 95 % Wilson confidence interval.
    """
    assert len(alice_key) == len(bob_key), (
        f"Key length mismatch: Alice={len(alice_key)}, Bob={len(bob_key)}"
    )

    n           = len(alice_key)
    sample_size = max(1, int(n * sample_fraction))

    rng     = random.Random(seed)
    indices = rng.sample(range(n), min(sample_size, n))

    errors = sum(1 for i in indices if alice_key[i] != bob_key[i])
    qber   = errors / len(indices)

    # 95 % Wilson confidence interval
    p, z, n_s = qber, 1.96, len(indices)
    denom  = 1 + z ** 2 / n_s
    center = (p + z ** 2 / (2 * n_s)) / denom
    margin = (z * (p * (1 - p) / n_s + z ** 2 / (4 * n_s ** 2)) ** 0.5) / denom
    ci_low  = max(0.0, center - margin)
    ci_high = min(1.0, center + margin)

    if qber < 0.05:
        status = "SECURE ok"
    elif qber < 0.11:
        status = "WARNING "
    else:
        status = "ABORT x"

    return QBERResult(
        qber=qber,
        errors=errors,
        sample_size=len(indices),
        security_status=status,
        confidence_low=ci_low,
        confidence_high=ci_high,
    )
