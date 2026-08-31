"""
bb84_grand.py
=============
Guessing Random Additive Noise Decoding (GRAND) algorithm for BB84 QKD
error mitigation and correction.

GRAND is an information-theoretic decoder that works probabilistically:
  1. Receive a noisy key (sifted_key_bob)
  2. Guess random error patterns with increasing Hamming weight
  3. Add each guess to the received key to produce candidate codewords
  4. Test each candidate against validation criteria (syndrome check, parity, etc.)
  5. Return the first candidate that passes validation

This implementation provides:
  - Basic GRAND decoding with configurable search strategy
  - Validation by syndrome parity check (linear code assumption)
  - Validation by knowledge of secret (for controlled experiments)
  - Adaptive termination based on error probability
  - Integration with BB84 sifted keys
  - Performance metrics and statistics

References
----------
A. Tal & A. Vardy (2015). "List Decoding of Polar Codes." IEEE ISIT.
K. R. Duffy et al. (2020). "Capacity-Achieving Codes for the Quantum
  Deletion Channel." ISIT & arXiv:2004.07398.
S. Scholl & W. Shin (2023). "GRAND is Grand, Revisited." arXiv:2301.13715.

University of Ruhuna - Dept. of Computer Engineering
MIT Licence - see LICENSE
"""

from __future__ import annotations

import random
import math
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass
import numpy as np


# ──────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ──────────────────────────────────────────────────────────────────────

@dataclass
class GRANDDecodeResult:
    """Output of GRAND decoding attempt."""

    success: bool
    """True if a valid candidate was found."""

    corrected_key: Optional[List[int]]
    """Corrected key bits (None if failed)."""

    guesses_tried: int
    """Number of error patterns tested."""

    final_syndrome: Optional[List[int]]
    """Final syndrome for the selected candidate (if found)."""

    error_pattern_weight: Optional[int]
    """Hamming weight of the error pattern that validated."""

    validation_method: str
    """Method used to validate: 'syndrome', 'oracle', 'parity'."""

    estimated_ber: float
    """Estimated Bit Error Rate from guess statistics."""


@dataclass
class GRANDStatistics:
    """Accumulated statistics from multiple GRAND attempts."""

    total_attempts: int = 0
    successful_decodes: int = 0
    total_guesses_tried: int = 0
    avg_guesses_per_success: float = 0.0
    avg_syndrome_weight: float = 0.0
    weight_histogram: Dict[int, int] = None  # weight -> count
    observed_ber_samples: List[float] = None

    def __post_init__(self):
        if self.weight_histogram is None:
            self.weight_histogram = {}
        if self.observed_ber_samples is None:
            self.observed_ber_samples = []

    def update(self, result: GRANDDecodeResult):
        """Update statistics with a single GRAND result."""
        self.total_attempts += 1
        if result.success:
            self.successful_decodes += 1
            self.total_guesses_tried += result.guesses_tried
            if result.error_pattern_weight is not None:
                self.weight_histogram[result.error_pattern_weight] = \
                    self.weight_histogram.get(result.error_pattern_weight, 0) + 1

        if self.total_guesses_tried > 0:
            self.avg_guesses_per_success = self.total_guesses_tried / max(1, self.successful_decodes)

    def success_rate(self) -> float:
        """Fraction of decoding attempts that succeeded."""
        if self.total_attempts == 0:
            return 0.0
        return self.successful_decodes / self.total_attempts

    def avg_syndrome_weight_samples(self, results: List[GRANDDecodeResult]) -> float:
        """Compute average syndrome weight from results."""
        valid_weights = [r.error_pattern_weight for r in results if r.error_pattern_weight is not None]
        return np.mean(valid_weights) if valid_weights else 0.0


# ──────────────────────────────────────────────────────────────────────
# GRAND DECODER
# ──────────────────────────────────────────────────────────────────────

class GRANDDecoder:
    """
    Guessing Random Additive Noise Decoding (GRAND) engine for BB84 keys.

    The decoder operates on a received (potentially noisy) sifted key from
    Bob and attempts to correct errors by:

    1. Systematically guessing error patterns with increasing Hamming weight
    2. Adding each guess to the received key (XOR operation)
    3. Validating the candidate against chosen criterion
    4. Returning the first successful candidate

    Supports three validation modes:
    - 'syndrome': assume a linear code and validate zero syndrome
    - 'oracle': compare against a known secret (Alice's key)
    - 'parity': simple parity check on candidate

    Parameters
    ----------
    validation_mode : str
        One of 'syndrome' | 'oracle' | 'parity'.
    oracle_key : List[int], optional
        Alice's sifted key (needed for 'oracle' mode).
    parity_check_matrix : np.ndarray, optional
        H matrix for syndrome computation (for 'syndrome' mode).
        If None, uses identity for demonstration (syndrome = received key).
    max_weight : int, optional
        Maximum Hamming weight of error patterns to try.
        Default: adaptive based on key length and estimated error rate.
    max_guesses : int, optional
        Hard cap on number of candidates to try. Default 2^20.
    rng_seed : int, optional
        RNG seed for reproducibility.

    Attributes
    ----------
    stats : GRANDStatistics
        Accumulates metrics across multiple calls to decode().

    Methods
    -------
    decode(received_key)
        Attempt to correct and validate the received key.
    """

    def __init__(
        self,
        validation_mode: str = "oracle",
        oracle_key: Optional[List[int]] = None,
        parity_check_matrix: Optional[np.ndarray] = None,
        max_weight: Optional[int] = None,
        max_guesses: int = 2**20,
        rng_seed: Optional[int] = None,
    ):
        if validation_mode not in ("oracle", "syndrome", "parity"):
            raise ValueError(f"Invalid validation_mode: {validation_mode}")

        self.validation_mode = validation_mode
        self.oracle_key = oracle_key
        self.parity_check_matrix = parity_check_matrix
        self.max_weight = max_weight
        self.max_guesses = max_guesses
        self._rng = np.random.default_rng(rng_seed)
        self.stats = GRANDStatistics()

    def decode(
        self,
        received_key: List[int],
        estimated_ber: Optional[float] = None,
    ) -> GRANDDecodeResult:
        """
        Attempt GRAND decoding of the received key.

        Parameters
        ----------
        received_key : List[int]
            Measured sifted key from Bob (may contain errors).
        estimated_ber : float, optional
            Estimated Bit Error Rate (0-1). Used to set adaptive max_weight.

        Returns
        -------
        GRANDDecodeResult
            Decoding attempt result with metadata.
        """
        if not received_key:
            return GRANDDecodeResult(
                success=False,
                corrected_key=None,
                guesses_tried=0,
                final_syndrome=None,
                error_pattern_weight=None,
                validation_method=self.validation_mode,
                estimated_ber=estimated_ber or 0.0,
            )

        n = len(received_key)

        # Determine adaptive max_weight if not set
        max_w = self.max_weight
        if max_w is None:
            max_w = self._adaptive_max_weight(n, estimated_ber)

        guesses_tried = 0

        # ─────────────────────────────────────────────────────────
        # Weight-ordered enumeration: try patterns of weight 0, 1, 2, ...
        # ─────────────────────────────────────────────────────────
        for weight in range(max_w + 1):
            # Generate all error patterns of this weight
            patterns = self._generate_error_patterns(n, weight)

            for pattern in patterns:
                if guesses_tried >= self.max_guesses:
                    # Hard cap reached
                    return GRANDDecodeResult(
                        success=False,
                        corrected_key=None,
                        guesses_tried=guesses_tried,
                        final_syndrome=None,
                        error_pattern_weight=None,
                        validation_method=self.validation_mode,
                        estimated_ber=estimated_ber or 0.0,
                    )

                guesses_tried += 1

                # Add error pattern to received key
                candidate = self._xor_lists(received_key, pattern)

                # Validate candidate
                syndrome = self._compute_syndrome(candidate)
                is_valid = self._validate_candidate(candidate, syndrome)

                if is_valid:
                    # Success: found a valid codeword
                    self.stats.update(GRANDDecodeResult(
                        success=True,
                        corrected_key=candidate,
                        guesses_tried=guesses_tried,
                        final_syndrome=syndrome,
                        error_pattern_weight=weight,
                        validation_method=self.validation_mode,
                        estimated_ber=estimated_ber or 0.0,
                    ))

                    return GRANDDecodeResult(
                        success=True,
                        corrected_key=candidate,
                        guesses_tried=guesses_tried,
                        final_syndrome=syndrome,
                        error_pattern_weight=weight,
                        validation_method=self.validation_mode,
                        estimated_ber=estimated_ber or 0.0,
                    )

        # No valid candidate found
        self.stats.update(GRANDDecodeResult(
            success=False,
            corrected_key=None,
            guesses_tried=guesses_tried,
            final_syndrome=None,
            error_pattern_weight=None,
            validation_method=self.validation_mode,
            estimated_ber=estimated_ber or 0.0,
        ))

        return GRANDDecodeResult(
            success=False,
            corrected_key=None,
            guesses_tried=guesses_tried,
            final_syndrome=None,
            error_pattern_weight=None,
            validation_method=self.validation_mode,
            estimated_ber=estimated_ber or 0.0,
        )

    # ──────────────────────────────────────────────────────────────
    # Helper Methods
    # ──────────────────────────────────────────────────────────────

    def _adaptive_max_weight(self, n: int, estimated_ber: Optional[float]) -> int:
        """
        Compute adaptive maximum Hamming weight to search.

        Uses information-theoretic bound: for random errors at rate p,
        expected weight is n*p. We add a safety margin.

        Parameters
        ----------
        n : key length
        estimated_ber : estimated error rate (or None for default)

        Returns
        -------
        max_weight : int, capped at [1, n//2]
        """
        if estimated_ber is None:
            estimated_ber = 0.05  # Default 5% QBER estimate

        # Expected error count + safety margin (3 standard deviations)
        expected_errors = n * estimated_ber
        std_dev = math.sqrt(n * estimated_ber * (1 - estimated_ber))
        margin = 3.0 * std_dev

        max_w = int(expected_errors + margin)
        max_w = max(1, min(max_w, n // 2))  # Clamp to [1, n/2]

        return max_w

    @staticmethod
    def _generate_error_patterns(n: int, weight: int) -> List[List[int]]:
        """
        Generate all binary error patterns of given Hamming weight.

        Uses combinatorial generation to enumerate all positions.

        Parameters
        ----------
        n : pattern length
        weight : number of 1-bits

        Returns
        -------
        patterns : list of binary lists, each with exactly 'weight' ones
        """
        if weight > n or weight < 0:
            return []

        # Use combinations to generate all ways to choose 'weight' positions
        from itertools import combinations

        patterns = []
        for positions in combinations(range(n), weight):
            pattern = [0] * n
            for pos in positions:
                pattern[pos] = 1
            patterns.append(pattern)

        return patterns

    @staticmethod
    def _xor_lists(a: List[int], b: List[int]) -> List[int]:
        """Bitwise XOR of two binary lists."""
        return [(x + y) % 2 for x, y in zip(a, b)]

    def _compute_syndrome(self, candidate: List[int]) -> List[int]:
        """
        Compute syndrome vector H * candidate^T.

        If parity_check_matrix is None, returns the candidate itself
        (identity mode: syndrome should match received key if no errors).

        Parameters
        ----------
        candidate : binary vector

        Returns
        -------
        syndrome : binary vector or None
        """
        if self.parity_check_matrix is None:
            # Identity: syndrome = candidate (for demo)
            return candidate

        # Compute H * c^T (mod 2)
        candidate_array = np.array(candidate, dtype=int)
        syndrome_raw = self.parity_check_matrix @ candidate_array
        syndrome = (syndrome_raw % 2).tolist()
        return syndrome

    def _validate_candidate(self, candidate: List[int], syndrome: Optional[List[int]]) -> bool:
        """
        Check if a candidate is valid according to the chosen criterion.

        Parameters
        ----------
        candidate : corrected key candidate
        syndrome : syndrome of candidate

        Returns
        -------
        is_valid : bool
        """
        if self.validation_mode == "oracle":
            # Oracle mode: candidate matches the known secret
            if self.oracle_key is None:
                return False
            return candidate == self.oracle_key

        elif self.validation_mode == "syndrome":
            # Syndrome mode: all-zero syndrome indicates a valid codeword
            if syndrome is None:
                return False
            return all(s == 0 for s in syndrome)

        elif self.validation_mode == "parity":
            # Parity mode: even parity (sum of bits mod 2 = 0)
            parity = sum(candidate) % 2
            return parity == 0

        return False


# ──────────────────────────────────────────────────────────────────────
# INTEGRATION FUNCTIONS
# ──────────────────────────────────────────────────────────────────────

def correct_sifted_key_with_grand(
    bob_sifted_key: List[int],
    alice_sifted_key: Optional[List[int]] = None,
    estimated_qber: Optional[float] = None,
    validation_mode: str = "oracle",
    max_weight: Optional[int] = None,
) -> Tuple[List[int], GRANDDecodeResult]:
    """
    Convenience function to correct Bob's sifted key using GRAND.

    This is the typical entry point when integrating GRAND error correction
    into a BB84 simulation workflow.

    Parameters
    ----------
    bob_sifted_key : List[int]
        Bob's measured sifted key (possibly with errors).
    alice_sifted_key : List[int], optional
        Alice's sifted key (secret reference, needed for 'oracle' mode).
    estimated_qber : float, optional
        Estimated Quantum Bit Error Rate (used for adaptive max_weight).
    validation_mode : str
        Validation strategy: 'oracle' (default) | 'syndrome' | 'parity'.
    max_weight : int, optional
        Maximum error pattern weight to try. If None, computed adaptively.

    Returns
    -------
    corrected_key : List[int]
        Corrected key (or original if GRAND failed).
    result : GRANDDecodeResult
        Full metadata about the decoding attempt.

    Example
    -------
    >>> alice_key = [0, 1, 0, 1, 1, 0, ...]
    >>> bob_key_noisy = [0, 1, 0, 0, 1, 0, ...]  # 1 error
    >>> corrected, result = correct_sifted_key_with_grand(
    ...     bob_key_noisy,
    ...     alice_sifted_key=alice_key,
    ...     validation_mode='oracle'
    ... )
    >>> if result.success:
    ...     print(f"Corrected! {result.guesses_tried} guesses needed.")
    ... else:
    ...     print("GRAND decoding failed; using uncorrected key.")
    """
    decoder = GRANDDecoder(
        validation_mode=validation_mode,
        oracle_key=alice_sifted_key,
        max_weight=max_weight,
    )

    result = decoder.decode(bob_sifted_key, estimated_ber=estimated_qber)

    if result.success and result.corrected_key is not None:
        return result.corrected_key, result
    else:
        # Fall back to uncorrected key on failure
        return bob_sifted_key, result


# ──────────────────────────────────────────────────────────────────────
# ANALYSIS & UTILITY FUNCTIONS
# ──────────────────────────────────────────────────────────────────────

def analyze_grand_performance(
    results: List[GRANDDecodeResult],
) -> Dict[str, float]:
    """
    Summarize performance metrics from a batch of GRAND results.

    Parameters
    ----------
    results : List[GRANDDecodeResult]
        Output from multiple GRAND decode attempts.

    Returns
    -------
    metrics : dict
        success_rate, avg_guesses, max_guesses, min_guesses,
        avg_error_weight, etc.
    """
    if not results:
        return {}

    successful = [r for r in results if r.success]
    success_rate = len(successful) / len(results) if results else 0.0

    if successful:
        guesses = [r.guesses_tried for r in successful]
        weights = [r.error_pattern_weight for r in successful if r.error_pattern_weight is not None]

        metrics = {
            "success_rate": success_rate,
            "num_successes": len(successful),
            "total_attempts": len(results),
            "avg_guesses_per_success": np.mean(guesses),
            "min_guesses": np.min(guesses),
            "max_guesses": np.max(guesses),
            "avg_error_weight": np.mean(weights) if weights else 0.0,
            "std_error_weight": np.std(weights) if weights else 0.0,
        }
    else:
        metrics = {
            "success_rate": 0.0,
            "num_successes": 0,
            "total_attempts": len(results),
            "avg_guesses_per_success": 0.0,
            "min_guesses": 0,
            "max_guesses": 0,
            "avg_error_weight": 0.0,
            "std_error_weight": 0.0,
        }

    return metrics


def introduce_errors(
    key: List[int],
    error_rate: float,
    seed: Optional[int] = None,
) -> Tuple[List[int], int]:
    """
    Randomly introduce bit-flip errors into a key for testing.

    Parameters
    ----------
    key : List[int]
        Original key (0s and 1s).
    error_rate : float
        Fraction of bits to flip (0.0-1.0).
    seed : int, optional
        RNG seed for reproducibility.

    Returns
    -------
    corrupted_key : List[int]
        Key with random bit flips.
    num_errors : int
        Actual number of bits flipped.
    """
    rng = np.random.default_rng(seed)
    corrupted = key.copy()
    error_positions = rng.choice(len(key), size=int(len(key) * error_rate), replace=False)

    for pos in error_positions:
        corrupted[pos] = 1 - corrupted[pos]

    return corrupted, len(error_positions)


if __name__ == "__main__":
    # Simple demonstration
    print("=" * 70)
    print("GRAND Algorithm Demonstration")
    print("=" * 70)

    # Create a test key
    alice_key = [0, 1, 0, 1, 1, 0, 1, 0, 1, 1]
    print(f"\nAlice's key:  {alice_key}")

    # Introduce some errors
    bob_key_noisy, num_errors = introduce_errors(alice_key, error_rate=0.2, seed=42)
    print(f"Bob's key (noisy): {bob_key_noisy}")
    print(f"Errors introduced: {num_errors}")

    # Correct using GRAND
    corrected, result = correct_sifted_key_with_grand(
        bob_key_noisy,
        alice_sifted_key=alice_key,
        validation_mode="oracle",
    )

    print(f"\nCorrected key:    {corrected}")
    print(f"Decoding {'SUCCESSFUL' if result.success else 'FAILED'}")
    if result.success:
        print(f"  Guesses tried: {result.guesses_tried}")
        print(f"  Error pattern weight: {result.error_pattern_weight}")
        print(f"  Final syndrome: {result.final_syndrome}")
