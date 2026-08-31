"""
bb84_zne.py
===========
Zero-Noise Extrapolation utilities for the BB84 QKD simulator.

This adds the functionality present in the more advanced project and lets
this repo run the same ZNE analyses against the simpler BB84 simulator.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import curve_fit

from bb84_config import SimulationConfig
from bb84_noise import NoiseModelType
from bb84_runner import run_simulation


def scale_depolar(p: float, f_scale: float) -> float:
    return min(max(p * f_scale, 0.0), 1.0)


def scale_amplitude_damping(t1_ns: float, gate_time_ns: float, f_scale: float) -> float:
    gamma = 1.0 - math.exp(-gate_time_ns / t1_ns)
    gamma_scaled = min(max(gamma * f_scale, 0.0), 0.999999)
    if gamma_scaled <= 0.0:
        return 1e12
    return -gate_time_ns / math.log(1.0 - gamma_scaled)


def scale_phase_damping(t2_ns: float, gate_time_ns: float, f_scale: float) -> float:
    lam = 1.0 - math.exp(-gate_time_ns / t2_ns)
    lam_scaled = min(max(lam * f_scale, 0.0), 0.999999)
    if lam_scaled <= 0.0:
        return 1e12
    return -gate_time_ns / math.log(1.0 - lam_scaled)


def linear_extrapolate(
    f_scales: List[float],
    qbers: List[float],
    weights: Optional[List[float]] = None,
) -> Tuple[float, float]:
    f = np.asarray(f_scales, dtype=float)
    q = np.asarray(qbers, dtype=float)
    if weights is None:
        w = np.ones_like(f)
    else:
        w = np.asarray(weights, dtype=float)
        w = np.where(w <= 0, 1e-6, w)

    W = np.sum(w)
    Wf = np.sum(w * f)
    Wq = np.sum(w * q)
    Wff = np.sum(w * f * f)
    Wfq = np.sum(w * f * q)

    denom = W * Wff - Wf ** 2
    if abs(denom) < 1e-12:
        return float(np.average(q, weights=w)), 0.0

    b = (W * Wfq - Wf * Wq) / denom
    a = (Wq - b * Wf) / W
    return float(a), float(b)


def exponential_extrapolate(
    f_scales: List[float],
    qbers: List[float],
) -> Dict[str, float]:
    f = np.asarray(f_scales, dtype=float)
    q = np.asarray(qbers, dtype=float)

    def model(x, A, B, c):
        return A - B * np.exp(-c * x)

    a_lin, b_lin = linear_extrapolate(list(f_scales), list(qbers))
    fail = dict(A=a_lin, B=0.0, c=0.0, estimate_raw=a_lin,
                estimate=max(0.0, a_lin), se_estimate=float('nan'),
                converged=False)

    try:
        p0 = [max(q.max(), a_lin) + 1.0, max(q.max() - q.min(), 0.5), 1.0]
        bounds = ([-50, -50, 1e-4], [100, 100, 10])
        popt, pcov = curve_fit(model, f, q, p0=p0, bounds=bounds, maxfev=10000)
        A, B, c = (float(v) for v in popt)
        estimate_raw = A - B

        if c <= 1.5e-4 or not np.all(np.isfinite(pcov)):
            return fail

        var_A, var_B, cov_AB = pcov[0, 0], pcov[1, 1], pcov[0, 1]
        var_est = var_A + var_B - 2 * cov_AB
        if var_est < 0 or not np.isfinite(var_est):
            return fail
        se_estimate = float(np.sqrt(var_est))

        relative_uncertainty = se_estimate / max(1.0, abs(estimate_raw))
        converged = relative_uncertainty < 0.5

        return dict(A=A, B=B, c=c, estimate_raw=estimate_raw,
                    estimate=max(0.0, estimate_raw),
                    se_estimate=se_estimate, converged=converged)
    except Exception:
        return fail


def zne_estimate_exponential(f_scales, qbers) -> Tuple[float, bool, float]:
    r = exponential_extrapolate(f_scales, qbers)
    return r['estimate'], r['converged'], r['estimate_raw']


def zne_estimate_linear(f_scales, qbers, weights=None) -> float:
    a, _ = linear_extrapolate(f_scales, qbers, weights)
    return max(0.0, a)


def build_scaled_config(
    base_noise_model: str,
    f_scale: float,
    n_qubits: int,
    seed: int,
    p_eve: float,
    base_depolar_prob: float = 0.05,
    base_t1_ns: float = 500.0,
    base_t2_ns: float = 200.0,
    gate_time_ns: float = 50.0,
    sample_fraction: float = 0.15,
) -> SimulationConfig:
    kwargs = dict(
        n_qubits=n_qubits,
        seed=seed,
        eve_present=(p_eve > 0),
        eve_intercept_prob=p_eve,
        sample_fraction=sample_fraction,
        label=f"ZNE f={f_scale:.2f} pEve={p_eve:.1f}",
    )

    if base_noise_model == NoiseModelType.DEPOLARIZING:
        kwargs["noise_model"] = NoiseModelType.DEPOLARIZING
        kwargs["depolar_prob"] = scale_depolar(base_depolar_prob, f_scale)
    elif base_noise_model == NoiseModelType.AMPLITUDE_DAMPING:
        kwargs["noise_model"] = NoiseModelType.AMPLITUDE_DAMPING
        kwargs["t1_ns"] = scale_amplitude_damping(base_t1_ns, gate_time_ns, f_scale)
        kwargs["gate_time_ns"] = gate_time_ns
    elif base_noise_model == NoiseModelType.PHASE_DAMPING:
        kwargs["noise_model"] = NoiseModelType.PHASE_DAMPING
        kwargs["t1_ns"] = 10_000.0
        kwargs["t2_ns"] = scale_phase_damping(base_t2_ns, gate_time_ns, f_scale)
        kwargs["gate_time_ns"] = gate_time_ns
    else:
        raise ValueError(f"ZNE not supported for noise_model={base_noise_model!r}")

    return SimulationConfig(**kwargs)


def bootstrap_zne_intercept(
    per_seed_qbers: Dict[float, List[float]],
    f_scales: List[float],
    n_boot: int = 2000,
    seed: int = 0,
) -> Tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    n_seeds = len(next(iter(per_seed_qbers.values())))
    intercepts = []
    for _ in range(n_boot):
        idx = rng.integers(0, n_seeds, size=n_seeds)
        means = [float(np.mean([per_seed_qbers[f][i] for i in idx])) for f in f_scales]
        a, _ = linear_extrapolate(f_scales, means)
        intercepts.append(max(0.0, a))
    intercepts = np.array(intercepts)
    return (
        float(np.mean(intercepts)),
        float(np.percentile(intercepts, 2.5)),
        float(np.percentile(intercepts, 97.5)),
    )


def quadratic_extrapolate(
    f_scales: List[float],
    qbers: List[float],
    weights: Optional[List[float]] = None,
) -> Tuple[float, np.ndarray]:
    f = np.asarray(f_scales, dtype=float)
    q = np.asarray(qbers, dtype=float)
    w = np.ones_like(f) if weights is None else np.asarray(weights, dtype=float)
    w = np.where(w <= 0, 1e-6, w)

    if len(f) < 3:
        a, _ = linear_extrapolate(list(f_scales), list(qbers), weights)
        return a, np.array([0.0, 0.0, a])

    coeffs = np.polyfit(f, q, deg=2, w=np.sqrt(w))
    a0 = float(np.polyval(coeffs, 0.0))
    return max(0.0, a0), coeffs


def zne_estimate_quadratic(f_scales, qbers, weights=None) -> float:
    a0, _ = quadratic_extrapolate(f_scales, qbers, weights)
    return a0


_ZNE_SUPPORTED_MODELS = (
    NoiseModelType.DEPOLARIZING,
    NoiseModelType.AMPLITUDE_DAMPING,
    NoiseModelType.PHASE_DAMPING,
)


@dataclass
class ZNEResult:
    base_label: str
    noise_model: str
    f_scales: List[float]
    n_seeds: int
    per_f_qber: Dict[float, Tuple[float, float, float]]
    linear_intercept: float
    linear_slope: float
    exponential: Dict[str, float]
    quadratic_intercept: float
    bootstrap_ci: Optional[Tuple[float, float, float]]
    qber_at_f1: float
    recommended_estimate: float
    runtime_seconds: float


def run_zne_analysis(
    base_config: SimulationConfig,
    f_scales: List[float],
    n_seeds: int = 5,
    method: str = "linear",
    bootstrap: bool = False,
) -> ZNEResult:
    if base_config.noise_model not in _ZNE_SUPPORTED_MODELS:
        raise ValueError(
            f"ZNE not supported for noise_model={base_config.noise_model!r}; "
            f"must be one of {_ZNE_SUPPORTED_MODELS}."
        )

    t0 = time.perf_counter()
    p_eve = base_config.eve_intercept_prob if base_config.eve_present else 0.0
    base_seed = base_config.seed if base_config.seed is not None else 0

    per_f_qber: Dict[float, Tuple[float, float, float]] = {}
    per_seed_qbers: Dict[float, List[float]] = {}
    mean_qbers: List[float] = []
    weights: List[float] = []

    for f_scale in f_scales:
        qbers_here: List[float] = []
        halfwidths: List[float] = []
        for i in range(n_seeds):
            cfg = build_scaled_config(
                base_config.noise_model,
                f_scale,
                n_qubits=base_config.n_qubits,
                seed=base_seed + i,
                p_eve=p_eve,
                base_depolar_prob=base_config.depolar_prob,
                base_t1_ns=base_config.t1_ns,
                base_t2_ns=base_config.t2_ns,
                gate_time_ns=base_config.gate_time_ns,
                sample_fraction=base_config.sample_fraction,
            )
            r = run_simulation(cfg, verbose=False)
            qr = r.qber_result
            qbers_here.append(qr.qber * 100)
            halfwidths.append(max(1e-3, (qr.confidence_high - qr.confidence_low) * 100 / 2))

        mean_q = float(np.mean(qbers_here))
        per_f_qber[f_scale] = (mean_q, mean_q, mean_q)
        per_seed_qbers[f_scale] = qbers_here
        mean_qbers.append(mean_q)
        weights.append(1.0 / (float(np.mean(halfwidths)) ** 2))

    linear_a, linear_b = linear_extrapolate(f_scales, mean_qbers, weights)
    exp_result = exponential_extrapolate(f_scales, mean_qbers)
    quad_a, _ = quadratic_extrapolate(f_scales, mean_qbers, weights)

    boot_ci = None
    if bootstrap:
        boot_ci = bootstrap_zne_intercept(per_seed_qbers, f_scales)

    if method == "exponential" and exp_result["converged"]:
        recommended = exp_result["estimate"]
    else:
        recommended = max(0.0, linear_a)

    qber_at_f1 = per_f_qber[1.0][0] if 1.0 in per_f_qber else mean_qbers[0]

    return ZNEResult(
        base_label=base_config.label,
        noise_model=base_config.noise_model,
        f_scales=list(f_scales),
        n_seeds=n_seeds,
        per_f_qber=per_f_qber,
        linear_intercept=max(0.0, linear_a),
        linear_slope=linear_b,
        exponential=exp_result,
        quadratic_intercept=quad_a,
        bootstrap_ci=boot_ci,
        qber_at_f1=qber_at_f1,
        recommended_estimate=recommended,
        runtime_seconds=time.perf_counter() - t0,
    )
