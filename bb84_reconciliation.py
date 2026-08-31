"""
bb84_reconciliation.py
======================
Information-reconciliation experiment library for the LDPC-vs-GRAND
comparison on BB84 sifted keys.

Both reconciliation methods are cast in the SAME syndrome-based protocol
so that leakage accounting is identical and the comparison is fair:

    1. Alice and Bob hold sifted keys x, y with y = x XOR e,
       where e is the error vector of a (approximately) BSC(p) channel.
    2. Alice computes s_A = H @ x (mod 2) and publishes it (m bits leaked).
    3. Bob computes s_delta = s_A XOR (H @ y) = H @ e (mod 2) and tries to
       find the most likely e consistent with that syndrome.
    4. Bob's corrected key is y XOR e_hat.

The two methods differ only in the code family and the search for e:

    LDPC  : sparse H from pyldpc, syndrome-target sum-product BP
            (the standard QKD reconciliation decoder).
    GRAND : dense random H, noise guessing - enumerate error patterns in
            increasing Hamming-weight order (ML for a BSC with p < 0.5)
            and accept the first pattern whose syndrome matches.

Leakage for both = m = number of syndrome rows published.

University of Ruhuna - Dept. of Computer Engineering
MIT Licence - see LICENSE
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List, Optional, Tuple

import numpy as np

from bb84_core import Alice, Bob
from bb84_noise import QuantumChannel, NoiseModelType
from bb84_config import SimulationConfig, LDPCBlockSummary, LDPCReconciliationResult


# ──────────────────────────────────────────────────────────────────────
# SHANNON HELPERS & RATE ADAPTATION
# ──────────────────────────────────────────────────────────────────────

def h2(p: float) -> float:
    """Binary entropy in bits."""
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -p * math.log2(p) - (1 - p) * math.log2(1 - p)


def shannon_leak_limit(n: int, p: float) -> float:
    """Minimum syndrome bits for reliable reconciliation: n * h2(p)."""
    return n * h2(p)


def efficiency_margin(n: int) -> float:
    """
    Rate-adaptation safety factor f(n): target leakage = f * n * h2(p).

    Short blocks need a larger margin because both finite-length coding
    losses and QBER-estimate variance grow as n shrinks.
    """
    if n <= 96:
        return 2.2
    if n <= 256:
        return 1.7
    if n <= 1024:
        return 1.40
    return 1.25


def choose_syndrome_length(n: int, p_est: float, available_rates: List[float]) -> Tuple[int, float]:
    """
    Rate adaptation: pick the smallest available syndrome rate m/n that
    is >= f(n) * h2(p_est).  Returns (m, rate).
    """
    target = efficiency_margin(n) * h2(max(p_est, 1e-4))
    for r in sorted(available_rates):
        if r >= target:
            return int(round(r * n)), r
    r = max(available_rates)
    return int(round(r * n)), r


# ──────────────────────────────────────────────────────────────────────
# LDPC: code construction + syndrome-target belief propagation
# ──────────────────────────────────────────────────────────────────────

_LDPC_LADDER: List[Tuple[int, int]] = [
    (3, 20),  # 0.15
    (3, 16),  # 0.1875
    (4, 20),  # 0.20
    (5, 20),  # 0.25
    (3, 10),  # 0.30
    (3, 8),   # 0.375
    (4, 10),  # 0.40
    (4, 8),   # 0.50
    (3, 5),   # 0.60
    (5, 8),   # 0.625
    (7, 10),  # 0.70
    (3, 4),   # 0.75
    (7, 8),   # 0.875
]


class LDPCReconciler:
    """
    Rate-adaptive LDPC syndrome reconciliation.

    Holds a ladder of regular LDPC parity-check matrices for one block
    length n and decodes with syndrome-target sum-product BP.
    """

    def __init__(self, n: int, seed: int = 0):
        """
        Initialize LDPC reconciler with available code ladder.

        Parameters
        ----------
        n : int
            Block length for LDPC codes.
        seed : int
            RNG seed for reproducibility.
        """
        try:
            from pyldpc.code import parity_check_matrix
        except ImportError:
            raise ImportError("pyldpc required for LDPC reconciliation. Install with: pip install pyldpc")

        self.n = n
        self.codes: Dict[float, np.ndarray] = {}
        for d_v, d_c in _LDPC_LADDER:
            if n % d_c != 0:
                continue
            H = parity_check_matrix(n, d_v, d_c, seed=seed)
            H = np.asarray(H.todense() if hasattr(H, "todense") else H, dtype=np.uint8)
            rate = H.shape[0] / n
            self.codes[round(rate, 4)] = H

        if not self.codes:
            raise ValueError(f"No ladder entry divides n={n}; adjust block length.")

    @property
    def available_rates(self) -> List[float]:
        return sorted(self.codes.keys())

    def reconcile(
        self,
        alice_block: np.ndarray,
        bob_block: np.ndarray,
        p_est: float,
        max_iter: int = 120,
        force_rate: Optional[float] = None,
    ) -> "ReconcileResult":
        """
        Run the full syndrome protocol on one block.

        Parameters
        ----------
        alice_block : np.ndarray
            Alice's sifted key block.
        bob_block : np.ndarray
            Bob's sifted key block (may contain errors).
        p_est : float
            Estimated channel crossover probability (QBER).
        max_iter : int
            Maximum BP iterations.
        force_rate : float, optional
            Force use of a specific syndrome rate.

        Returns
        -------
        ReconcileResult
            Outcome of reconciliation attempt.
        """
        n = self.n
        if force_rate is not None:
            rate = force_rate
        else:
            _, rate = choose_syndrome_length(n, p_est, self.available_rates)
        
        H = self.codes[rate]
        m = H.shape[0]

        t0 = time.perf_counter()
        s_a = (H @ alice_block) % 2
        s_b = (H @ bob_block) % 2
        s_delta = (s_a ^ s_b).astype(np.uint8)

        e_hat, converged, iters = _bp_syndrome_decode(H, s_delta, p_est, max_iter)
        dt = time.perf_counter() - t0

        corrected = bob_block ^ e_hat
        return ReconcileResult(
            method="LDPC",
            n=n,
            leaked_bits=m,
            syndrome_rate=m / n,
            claimed_success=converged,
            actually_correct=bool(np.array_equal(corrected, alice_block)),
            time_s=dt,
            work_units=iters,
            corrected_block=corrected,
        )


def _bp_syndrome_decode(
    H: np.ndarray,
    syndrome: np.ndarray,
    p: float,
    max_iter: int = 120,
) -> Tuple[np.ndarray, bool, int]:
    """
    Sum-product BP for syndrome decoding: H e = s (mod 2),
    error prior P(e_i = 1) = p (BSC crossover probability).
    """
    m, n = H.shape
    rows, cols = np.nonzero(H)
    n_edges = len(rows)

    p = np.clip(p, 1e-6, 0.499)
    llr_prior = np.log((1 - p) / p)
    sign_s = np.where(syndrome[rows] == 1, -1.0, 1.0)

    v2c = np.full(n_edges, llr_prior, dtype=float)
    c2v = np.zeros(n_edges)

    for it in range(1, max_iter + 1):
        t = np.tanh(np.clip(v2c / 2.0, -19.0, 19.0))
        t = np.where(np.abs(t) < 1e-12, 1e-12 * np.sign(t + 1e-30), t)
        prod_all = np.ones(m)
        np.multiply.at(prod_all, rows, t)
        ext = prod_all[rows] / t
        ext = np.clip(ext, -0.999999999, 0.999999999)
        c2v = sign_s * 2.0 * np.arctanh(ext)

        sum_all = np.zeros(n)
        np.add.at(sum_all, cols, c2v)
        posterior = llr_prior + sum_all
        v2c = posterior[cols] - c2v

        e_hat = (posterior < 0).astype(np.uint8)
        if np.array_equal((H @ e_hat) % 2, syndrome):
            return e_hat, True, it

    return e_hat, False, max_iter


def reconcile_full_key(
    alice_final: List[int],
    bob_final: List[int],
    p_est: float,
    block_len: int = 160,
    seed: int = 0,
    max_iter: int = 120,
    reconciler: Optional[LDPCReconciler] = None,
) -> LDPCReconciliationResult:
    """
    Reconcile a full key by chunking into blocks and running LDPC
    syndrome reconciliation on each.

    Parameters
    ----------
    alice_final : List[int]
        Alice's final key.
    bob_final : List[int]
        Bob's final key (may contain errors).
    p_est : float
        Estimated QBER.
    block_len : int
        Block length for LDPC codes.
    seed : int
        RNG seed.
    max_iter : int
        Maximum BP iterations per block.
    reconciler : LDPCReconciler, optional
        Pre-built reconciler; if None, creates a new one.

    Returns
    -------
    LDPCReconciliationResult
        Full reconciliation outcome.
    """
    if len(alice_final) != len(bob_final):
        raise ValueError("alice_final and bob_final must be the same length")

    t0 = time.perf_counter()
    n_blocks = len(alice_final) // block_len
    remainder_bits = len(alice_final) - n_blocks * block_len

    if reconciler is None:
        reconciler = LDPCReconciler(n=block_len, seed=seed)

    blocks: List[LDPCBlockSummary] = []
    reconciled_alice: List[int] = []
    reconciled_bob: List[int] = []
    total_leaked_bits = 0
    net_key_bits = 0
    failed_block_bits = 0
    any_undetected_error = False
    all_blocks_correct = True

    for i in range(n_blocks):
        start = i * block_len
        a_block = np.asarray(alice_final[start:start + block_len], dtype=np.uint8)
        b_block = np.asarray(bob_final[start:start + block_len], dtype=np.uint8)
        r = reconciler.reconcile(a_block, b_block, p_est=p_est, max_iter=max_iter)

        blocks.append(LDPCBlockSummary(
            leaked_bits=r.leaked_bits,
            syndrome_rate=r.syndrome_rate,
            claimed_success=r.claimed_success,
            actually_correct=r.actually_correct,
            work_units=r.work_units,
        ))
        total_leaked_bits += r.leaked_bits
        any_undetected_error = any_undetected_error or r.undetected_error
        all_blocks_correct = all_blocks_correct and r.actually_correct

        if r.actually_correct:
            net_key_bits += block_len - r.leaked_bits
            reconciled_alice.extend(int(x) for x in a_block)
            reconciled_bob.extend(int(x) for x in r.corrected_block)
        else:
            failed_block_bits += block_len

    return LDPCReconciliationResult(
        block_len=block_len,
        n_blocks=n_blocks,
        remainder_bits=remainder_bits,
        failed_block_bits=failed_block_bits,
        total_input_bits=n_blocks * block_len,
        total_leaked_bits=total_leaked_bits,
        net_key_bits=net_key_bits,
        any_undetected_error=any_undetected_error,
        all_blocks_correct=all_blocks_correct,
        blocks=blocks,
        reconciled_alice_key=reconciled_alice,
        reconciled_bob_key=reconciled_bob,
        runtime_seconds=time.perf_counter() - t0,
    )


# ──────────────────────────────────────────────────────────────────────
# RESULT RECORDS
# ──────────────────────────────────────────────────────────────────────

@dataclass
class ReconcileResult:
    """Outcome of one reconciliation attempt on one block."""
    method: str
    n: int
    leaked_bits: int
    syndrome_rate: float
    claimed_success: bool
    actually_correct: bool
    time_s: float
    work_units: int
    corrected_block: Optional[np.ndarray] = field(default=None, repr=False, compare=False)

    @property
    def undetected_error(self) -> bool:
        """Decoder claimed success but the key is wrong."""
        return self.claimed_success and not self.actually_correct

    @property
    def net_key_fraction(self) -> float:
        """Fraction of the block surviving as corrected key."""
        if not self.actually_correct:
            return 0.0
        return max(0.0, (self.n - self.leaked_bits) / self.n)
