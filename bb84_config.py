"""
bb84_config.py
==============
Configuration dataclasses for the BB84 QKD simulator.

SimulationConfig  - all tunable parameters in one place
QBERResult        - QBER estimation output with Wilson CI
SimulationResult  - full output of one simulation run

University of Ruhuna - Dept. of Computer Engineering
MIT Licence - see LICENSE
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# ──────────────────────────────────────────────────────────────────────
# SIMULATION CONFIGURATION
# ──────────────────────────────────────────────────────────────────────

@dataclass
class SimulationConfig:
    """
    One complete BB84 simulation configuration.

    All parameters have safe defaults so the simplest usage is just::

        cfg = SimulationConfig()          # 1000 qubits, ideal channel
        cfg = SimulationConfig(n_qubits=500, eve_present=True)
    """

    # ── Core ──────────────────────────────────────────────────────────
    n_qubits: int = 1000
    """Total qubits Alice transmits."""

    seed: Optional[int] = 42
    """RNG seed.  None → new random run each time; int → reproducible."""

    label: str = "Simulation"
    """Human-readable name used in plots and console output."""

    sample_fraction: float = 0.15
    """Fraction of sifted key consumed for QBER estimation (0–1)."""

    # ── Eve (intercept-resend attack) ─────────────────────────────────
    eve_present: bool = False
    """True → Eve performs an intercept-resend attack."""

    eve_intercept_prob: float = 1.0
    """Fraction of qubits Eve intercepts (0.0–1.0)."""

    # ── Channel noise ─────────────────────────────────────────────────
    noise_enabled: bool = False
    """True → apply depolarising channel noise."""

    depolar_prob: float = 0.01
    """Depolarising error probability per gate (used when noise_enabled=True)."""


# ──────────────────────────────────────────────────────────────────────
# QBER RESULT
# ──────────────────────────────────────────────────────────────────────

@dataclass
class QBERResult:
    """Output of ``estimate_qber()``."""

    qber: float
    """Quantum Bit Error Rate (0.0–1.0)."""

    errors: int
    """Bit disagreements found in the sample."""

    sample_size: int
    """Number of bits consumed for estimation."""

    security_status: str
    """``'SECURE ok'`` | ``'WARNING '`` | ``'ABORT x'``"""

    confidence_low: float
    """Lower bound of the 95 % Wilson confidence interval."""

    confidence_high: float
    """Upper bound of the 95 % Wilson confidence interval."""


# ──────────────────────────────────────────────────────────────────────
# SIMULATION RESULT
# ──────────────────────────────────────────────────────────────────────

@dataclass
class SimulationResult:
    """Complete output of one ``run_simulation()`` call."""

    config: SimulationConfig
    n_transmitted: int
    n_sifted: int
    sifted_key_rate: float
    qber_result: QBERResult
    alice_final_key: List[int]
    bob_final_key: List[int]
    key_agreement_rate: float
    eve_interception_rate: float
    runtime_seconds: float

    @property
    def key_length(self) -> int:
        """Number of bits in the final (post-QBER-sample) key."""
        return len(self.alice_final_key)

    @property
    def keys_match(self) -> bool:
        """True when Alice's and Bob's final keys are identical."""
        return self.alice_final_key == self.bob_final_key

    @property
    def key_generation_rate(self) -> float:
        """Final key bits produced per transmitted qubit."""
        return self.key_length / self.n_transmitted if self.n_transmitted else 0.0
