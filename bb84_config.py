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
    """Fraction of sifted key consumed for QBER estimation (0-1)."""

    # ── Eve (intercept-resend attack) ─────────────────────────────────
    eve_present: bool = False
    """True → Eve performs an intercept-resend attack."""

    eve_intercept_prob: float = 1.0
    """Fraction of qubits Eve intercepts (0.0-1.0)."""

    # ── Channel noise (Phase 1, legacy) ───────────────────────────────
    noise_enabled: bool = False
    """True → apply depolarising channel noise. Ignored if noise_model is set."""

    depolar_prob: float = 0.01
    """Depolarising error probability per gate (DEPOLARIZING model)."""

    # ── Channel noise (Phase 3) ────────────────────────────────────────
    noise_model: Optional[str] = None
    """
    Phase 3 channel model selector. One of:
    'ideal' | 'depolarizing' | 'amplitude_damping' | 'phase_damping' |
    'combined' | 'fibre_loss'  (see bb84_noise.NoiseModelType).

    Default None → fall back to the legacy ``noise_enabled`` /
    ``depolar_prob`` fields, reproducing Phase 1 behaviour exactly.
    Setting this field explicitly always takes precedence.
    """

    t1_ns: float = 10_000.0
    """T1 energy-relaxation time in ns (amplitude_damping / combined).
    Default 10 us, representative of current transmon hardware."""

    t2_ns: float = 8_000.0
    """T2 dephasing time in ns (phase_damping / combined).
    Must satisfy T2 <= 2*T1; enforced automatically in bb84_noise."""

    gate_time_ns: float = 50.0
    """Single-qubit gate duration in ns."""

    channel_length_km: float = 0.0
    """Fibre-optic channel length in km (fibre_loss model only)."""

    # ── LDPC reconciliation (Phase 5) ─────────────────────────────────
    ldpc_enabled: bool = False
    """True → run LDPC syndrome reconciliation on the post-QBER-sample key."""

    ldpc_block_len: int = 160
    """LDPC operating block length in bits. Must divide evenly with at
    least one (d_v, d_c) entry in reconciliation._LDPC_LADDER; 160 gives
    access to the full rate ladder (0.15-0.875)."""

    ldpc_calibrate: bool = False
    """True → run LDPCReconciler.calibrate() (offline FER-curve Monte
    Carlo) before reconciling, for more accurate rate selection. Slower;
    off by default so interactive runs stay fast."""

    ldpc_seed: Optional[int] = None
    """RNG seed for LDPC code construction/calibration. None → falls
    back to (config.seed or 0), independent of the transmission RNG."""


    def __post_init__(self) -> None:
        """
        Validate the Bloch-sphere physical constraint T2 <= 2*T1.

        This is checked at configuration-creation time so an invalid
        (t1_ns, t2_ns) pair fails immediately and explicitly, rather
        than being silently clamped later inside QuantumChannel.
        """
        if self.t2_ns > 2 * self.t1_ns:
            raise ValueError(
                f"Invalid config: T2 ({self.t2_ns} ns) exceeds 2*T1 "
                f"({2 * self.t1_ns} ns). This violates the physical "
                f"Bloch-sphere bound T2 <= 2*T1 for any real qubit. "
                f"Reduce t2_ns or increase t1_ns."
            )


# ──────────────────────────────────────────────────────────────────────
# QBER RESULT
# ──────────────────────────────────────────────────────────────────────

@dataclass
class QBERResult:
    """Output of ``estimate_qber()``."""

    qber: float
    """Quantum Bit Error Rate (0.0-1.0)."""

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
# LDPC RECONCILIATION RESULT
# ──────────────────────────────────────────────────────────────────────

@dataclass
class LDPCBlockSummary:
    """Outcome of LDPC syndrome reconciliation on one fixed-length block."""

    leaked_bits: int
    """Syndrome bits Alice published for this block (m = H.shape[0])."""

    syndrome_rate: float
    """m / block_len for the code the rate-adaptation logic picked."""

    claimed_success: bool
    """True if belief propagation converged to a consistent syndrome."""

    actually_correct: bool
    """True if the corrected block matches Alice's block exactly.

    Only checkable here because this is a simulation and Alice's block
    is available for comparison - a real deployment would instead use a
    hash/MAC check. See LDPCReconciliationResult docstring.
    """

    work_units: int
    """Belief-propagation iterations used."""


@dataclass
class LDPCReconciliationResult:
    """
    Aggregate output of running LDPC syndrome reconciliation over a
    sifted, post-QBER-sample key, in fixed-length blocks.

    Ground-truth checking (``LDPCBlockSummary.actually_correct``) is only
    possible because Alice's key is available in-process in this
    simulation; a real deployment cannot do this and would instead rely
    on an explicit hash/MAC verification step.

    ``net_key_bits`` / ``total_leaked_bits`` are an information-theoretic
    accounting of what a real deployment would need to strip via privacy
    amplification against an eavesdropper who saw the published syndrome.
    Privacy amplification itself (universal hashing) is NOT implemented -
    ``reconciled_bob_key`` is the full error-corrected key, not a
    shortened one.
    """

    block_len: int
    n_blocks: int
    remainder_bits: int
    """Bits left over after chunking into block_len-sized blocks.
    Dropped entirely - not carried into the reconciled key, reconciled
    or not, since including possibly-erroneous bits under a "reconciled"
    label would be misleading."""
    failed_block_bits: int
    """Bits belonging to blocks whose decode did not actually succeed
    (actually_correct is False). Also excluded from reconciled_*_key for
    the same reason as remainder_bits - a distinct cause (decode failure
    vs. leftover length), reported separately so the UI can distinguish
    them."""
    total_input_bits: int
    total_leaked_bits: int
    """Syndrome bits published across every attempted block (correct and
    failed alike - Alice publishes a block's syndrome before decoding is
    known to succeed)."""
    net_key_bits: int
    """Sum of (block_len - leaked_bits) over successfully reconciled
    blocks only - the Shannon-cost estimate of what would remain as
    secure key after (hypothetical) privacy amplification."""
    any_undetected_error: bool
    """True if any block claimed success but was actually wrong - the
    dangerous failure mode a real deployment would need a hash check to
    catch."""
    all_blocks_correct: bool
    blocks: List[LDPCBlockSummary]
    reconciled_alice_key: List[int]
    """Concatenation of successfully reconciled blocks only (excludes
    the remainder tail and any failed blocks)."""
    reconciled_bob_key: List[int]
    runtime_seconds: float

    @property
    def keys_match(self) -> bool:
        """True when the reconciled keys are identical (full blocks only)."""
        return self.reconciled_alice_key == self.reconciled_bob_key


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
    n_lost: int = 0
    """Qubits never detected by Bob (FIBRE_LOSS model). 0 for all other channels."""
    ldpc_result: Optional["LDPCReconciliationResult"] = None
    """Populated only when config.ldpc_enabled is True. Reconciliation"""

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

    @property
    def photon_survival_rate(self) -> float:
        """Fraction of the transmitted photons that reached Bob."""
        if self.n_transmitted == 0:
            return 0.0
        return (self.n_transmitted - self.n_lost) / self.n_transmitted
