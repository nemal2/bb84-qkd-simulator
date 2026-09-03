"""
bb84_gate_schemes.py
=====================
Control-experiment gate-exposure schemes for the caveat in Sec. VII-C/D
of the report: "the observed error correlation occurred under an
idealized noise model where one basis/bit preparation path had zero
noisy gate exposure."

Each scheme below gives every (basis, bit) preparation path >=1 noisy
gate (except scheme C's deliberately-relocated bare path, included for
comparison), using `id` gates as logically-inert noise carriers -- an
`id` gate is the identity operation, so it never changes which state is
prepared, but IS a Kraus-noise attachment point (bb84_noise.py's
_GATE_NOISE_TARGETS includes 'id'), so it gives that path real, non-zero
noisy-gate exposure.

This module is never imported by any existing experiment path. It is
only reached when SimulationConfig.gate_scheme (or Alice.prepare_qubit's
gate_scheme kwarg) is explicitly set to 'A', 'B', or 'C'.

Encoding table (unchanged from bb84_core.py)
---------------------------------------------
bit=0, basis=0  ->  |0>
bit=1, basis=0  ->  |1>
bit=0, basis=1  ->  |+>
bit=1, basis=1  ->  |->

Schemes
-------
A - Minimal fix: one `id` gate added on top of the existing encoding.
    |0> -> id            (1 gate)
    |1> -> id, x         (2 gates)
    |+> -> id, h         (2 gates)
    |-> -> id, x, h      (3 gates)
    Tests: does removing the literal zero-gate path soften/kill the
    P=1.000 certainty? Gate-count asymmetry (1,2,2,3) still exists, so a
    softened-but-nonzero correlation is the expected outcome if the
    mechanism is genuine gate-count asymmetry.

B - Equalized gate count: every path gets exactly 2 gates.
    |0> -> id, id        (2 gates)
    |1> -> id, x         (2 gates)
    |+> -> id, h         (2 gates)
    |-> -> x, h          (2 gates)
    Tests: is it gate-COUNT asymmetry driving the leak, or something
    about which gate types (X vs H vs id) sit under the Kraus map? If
    the correlation nearly vanishes here, count-asymmetry was the
    mechanism (clean confirmation). If it persists, gate-type matters
    too (a genuine secondary finding, not a null result).

C - Relocated bare path: same "one path is exactly noise-free" logic as
    the original model, but the zero-gate path is moved from |0> to |->.
    |0> -> id, id, id    (3 gates)
    |1> -> id, id        (2 gates)
    |+> -> id            (1 gate)
    |-> -> (0 gates)
    Tests: is the certainty tied specifically to the |0> path, or does
    it follow whichever path is bare? Expect P(bit=1|error) to flip
    toward the OTHER bit value on the rectilinear basis (since bit=1 is
    now the bare path, rectilinear errors should now imply bit=0), which
    would confirm the mechanism is "bare path -> certainty", not an
    artifact tied to |0> specifically.
"""

from __future__ import annotations

from qiskit import QuantumCircuit

VALID_SCHEMES = ("A", "B", "C")


def _gates_for(bit: int, basis: int, scheme: str):
    """Return the ordered gate-name sequence for one (bit, basis) path."""
    key = (bit, basis)  # (bit, basis): 0=rectilinear/+z-x, matches bb84_core encoding

    if scheme == "A":
        table = {
            (0, 0): ["id"],
            (1, 0): ["id", "x"],
            (0, 1): ["id", "h"],
            (1, 1): ["id", "x", "h"],
        }
    elif scheme == "B":
        table = {
            (0, 0): ["id", "id"],
            (1, 0): ["id", "x"],
            (0, 1): ["id", "h"],
            (1, 1): ["x", "h"],
        }
    elif scheme == "C":
        table = {
            (0, 0): ["id", "id", "id"],
            (1, 0): ["id", "id"],
            (0, 1): ["id"],
            (1, 1): [],
        }
    else:
        raise ValueError(f"Unknown gate_scheme {scheme!r}; must be one of {VALID_SCHEMES}")

    return table[key]


def build_scheme_circuit(bit: int, basis: int, scheme: str, name: str = "A") -> QuantumCircuit:
    """
    Build the state-preparation circuit for (bit, basis) under a control
    gate-exposure scheme. `id` gates are logically inert (identity) but
    ARE noisy-gate exposure points once bb84_noise.py attaches Kraus
    error to them.
    """
    qc = QuantumCircuit(1, 1, name=name)
    for gate in _gates_for(bit, basis, scheme):
        if gate == "id":
            qc.id(0)
        elif gate == "x":
            qc.x(0)
        elif gate == "h":
            qc.h(0)
        else:
            raise ValueError(f"unknown gate {gate!r}")
    return qc


def gate_count_table(scheme: str) -> dict:
    """Human-readable {(bit,basis): n_gates} summary, for sanity-printing."""
    return {k: len(_gates_for(k[0], k[1], scheme)) for k in [(0, 0), (1, 0), (0, 1), (1, 1)]}