"""
bb84_noise.py
=============
Phase 3 physically-motivated quantum channel noise models for the BB84
QKD simulator.

This file adds the Phase 3 noise-model support used by the ZNE workflow.
It is intentionally compatible with the smaller project structure here:
- SimulationConfig accepts ``noise_model`` and associated physical params.
- QuantumChannel.from_config(config) returns the appropriate model.
- Legacy depolarising/noise_enabled behaviour remains supported.
"""

from __future__ import annotations

import math
import random
from typing import Optional

from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
from qiskit_aer.noise import (
    NoiseModel,
    amplitude_damping_error,
    depolarizing_error,
    phase_damping_error,
    thermal_relaxation_error,
)

from bb84_config import SimulationConfig


class NoiseModelType:
    IDEAL = "ideal"
    DEPOLARIZING = "depolarizing"
    AMPLITUDE_DAMPING = "amplitude_damping"
    PHASE_DAMPING = "phase_damping"
    COMBINED = "combined"
    FIBRE_LOSS = "fibre_loss"

    ALL = (
        IDEAL,
        DEPOLARIZING,
        AMPLITUDE_DAMPING,
        PHASE_DAMPING,
        COMBINED,
        FIBRE_LOSS,
    )

    LABELS = {
        IDEAL: "Ideal (no noise)",
        DEPOLARIZING: "Depolarising",
        AMPLITUDE_DAMPING: "Amplitude Damping (T1)",
        PHASE_DAMPING: "Phase Damping (T2)",
        COMBINED: "Combined T1+T2",
        FIBRE_LOSS: "Fibre Loss",
    }


_GATE_NOISE_TARGETS = ["x", "h"]


class QuantumChannel:
    def __init__(
        self,
        noise_model: str = NoiseModelType.IDEAL,
        depolar_prob: float = 0.01,
        t1_ns: float = 10_000.0,
        t2_ns: float = 8_000.0,
        gate_time_ns: float = 50.0,
        channel_length_km: float = 0.0,
        fibre_attenuation_db_km: float = 0.2,
        loss_rng: Optional[random.Random] = None,
    ):
        if noise_model not in NoiseModelType.ALL:
            print(f"[bb84_noise] WARNING: unknown noise_model={noise_model!r}; falling back to ideal simulator.")
            noise_model = NoiseModelType.IDEAL

        self.noise_model = noise_model
        self.depolar_prob = depolar_prob
        self.t1_ns = float(t1_ns)
        self.t2_ns = float(min(t2_ns, 2 * t1_ns - 1e-6))
        self.gate_time_ns = float(gate_time_ns)
        self.channel_length_km = float(channel_length_km)
        self.alpha_db_km = float(fibre_attenuation_db_km)
        self._loss_rng = loss_rng if loss_rng is not None else random.Random()
        self._simulator = self._build_simulator()

    @classmethod
    def from_config(
        cls,
        config: SimulationConfig,
        loss_rng: Optional[random.Random] = None,
    ) -> "QuantumChannel":
        model = config.noise_model
        if model is None:
            model = NoiseModelType.DEPOLARIZING if config.noise_enabled else NoiseModelType.IDEAL
        return cls(
            noise_model=model,
            depolar_prob=config.depolar_prob,
            t1_ns=config.t1_ns,
            t2_ns=config.t2_ns,
            gate_time_ns=config.gate_time_ns,
            channel_length_km=config.channel_length_km,
            loss_rng=loss_rng,
        )

    @property
    def survival_probability(self) -> float:
        return 10 ** (-self.alpha_db_km * self.channel_length_km / 10.0)

    @property
    def gamma(self) -> float:
        return 1.0 - math.exp(-self.gate_time_ns / self.t1_ns)

    @property
    def lam(self) -> float:
        return 1.0 - math.exp(-self.gate_time_ns / self.t2_ns)

    @property
    def description(self) -> str:
        if self.noise_model == NoiseModelType.IDEAL:
            return "Ideal channel (no noise)"
        if self.noise_model == NoiseModelType.DEPOLARIZING:
            return f"Depolarising  p = {self.depolar_prob}"
        if self.noise_model == NoiseModelType.AMPLITUDE_DAMPING:
            return f"Amplitude damping  T1={self.t1_ns/1000:.3f} us  (gamma={self.gamma:.5f})"
        if self.noise_model == NoiseModelType.PHASE_DAMPING:
            return f"Phase damping  T2={self.t2_ns/1000:.3f} us  (lambda={self.lam:.5f})"
        if self.noise_model == NoiseModelType.COMBINED:
            return (
                f"Combined T1+T2  T1={self.t1_ns/1000:.3f} us  "
                f"T2={self.t2_ns/1000:.3f} us  t_gate={self.gate_time_ns:.0f} ns"
            )
        if self.noise_model == NoiseModelType.FIBRE_LOSS:
            return f"Fibre loss  L={self.channel_length_km:.1f} km  (P_survive={self.survival_probability:.4f})"
        return "Unknown channel"

    def run_circuit(self, qc: QuantumCircuit, shot_seed: Optional[int] = None, apply_loss: bool = True):
        if self.noise_model == NoiseModelType.FIBRE_LOSS and apply_loss:
            draw = (random.Random(shot_seed).random() if shot_seed is not None else self._loss_rng.random())
            if draw > self.survival_probability:
                return None

        kwargs = {"shots": 1}
        if shot_seed is not None:
            kwargs["seed_simulator"] = int(shot_seed) % (2 ** 31)
        job = self._simulator.run(qc, **kwargs)
        counts = job.result().get_counts()
        return int(list(counts.keys())[0])

    def _build_simulator(self) -> AerSimulator:
        if self.noise_model in (NoiseModelType.IDEAL, NoiseModelType.FIBRE_LOSS):
            return AerSimulator()

        nm = NoiseModel()

        if self.noise_model == NoiseModelType.DEPOLARIZING:
            err = depolarizing_error(self.depolar_prob, 1)
            nm.add_all_qubit_quantum_error(err, ["x", "h", "id"])
        elif self.noise_model == NoiseModelType.AMPLITUDE_DAMPING:
            err = amplitude_damping_error(self.gamma)
            nm.add_all_qubit_quantum_error(err, _GATE_NOISE_TARGETS)
        elif self.noise_model == NoiseModelType.PHASE_DAMPING:
            err = phase_damping_error(self.lam)
            nm.add_all_qubit_quantum_error(err, _GATE_NOISE_TARGETS)
        elif self.noise_model == NoiseModelType.COMBINED:
            err = thermal_relaxation_error(self.t1_ns, self.t2_ns, self.gate_time_ns)
            nm.add_all_qubit_quantum_error(err, _GATE_NOISE_TARGETS)

        return AerSimulator(noise_model=nm)
