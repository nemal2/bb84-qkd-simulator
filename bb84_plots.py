"""
bb84_plots.py
=============
Publication-quality visualisations for the BB84 QKD simulator.

Exports
-------
plot_comparison(scenarios, results, ...)
    Single-panel QBER bar chart with Wilson CI error bars.

plot_qber_vs_intercept_rate(n_qubits, steps, ...)
    Sweep Eve's intercept probability and compare simulated vs theoretical QBER.

University of Ruhuna - Dept. of Computer Engineering
MIT Licence - see LICENSE
"""

from __future__ import annotations

import textwrap
from typing import List, Optional, Tuple

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker

from bb84_config import SimulationConfig, SimulationResult
from bb84_runner import run_simulation


# ──────────────────────────────────────────────────────────────────────
# GLOBAL STYLE  (IEEE / research-paper defaults)
# ──────────────────────────────────────────────────────────────────────

plt.rcParams.update({
    "font.family":        "serif",
    "font.serif":         ["Times New Roman", "DejaVu Serif"],
    "font.size":          8,
    "axes.titlesize":     9,
    "axes.labelsize":     8,
    "xtick.labelsize":    7,
    "ytick.labelsize":    7,
    "legend.fontsize":    7,
    "figure.dpi":         150,
    "axes.spines.top":    True,
    "axes.spines.right":  True,
    "axes.spines.bottom": True,
    "axes.spines.left":   True,
    "axes.linewidth":     0.8,
    "xtick.major.width":  0.8,
    "ytick.major.width":  0.8,
    "xtick.minor.width":  0.5,
    "ytick.minor.width":  0.5,
    "xtick.direction":    "in",
    "ytick.direction":    "in",
    "grid.linewidth":     0.45,
    "grid.alpha":         0.35,
    "grid.color":         "#aaaaaa",
})


# ──────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────

def _status_color(r: SimulationResult) -> str:
    s = r.qber_result.security_status
    if "SECURE"  in s: return "#2ca02c"
    if "WARNING" in s: return "#ff7f0e"
    return "#d62728"


def _wrap(text: str, width: int = 72) -> str:
    """Word-wrap *text* to at most *width* characters per line."""
    return textwrap.fill(text, width=width, break_long_words=False)


_LEGEND_PATCHES = [
    mpatches.Patch(facecolor="#2ca02c", edgecolor="black", linewidth=0.5,
                   label="Secure  (QBER < 5 %)"),
    mpatches.Patch(facecolor="#ff7f0e", edgecolor="black", linewidth=0.5,
                   label="Warning (5 %–11 %)"),
    mpatches.Patch(facecolor="#d62728", edgecolor="black", linewidth=0.5,
                   label="Abort   (QBER ≥ 11 %)"),
]


# ──────────────────────────────────────────────────────────────────────
# PLOT 1 - QBER COMPARISON BAR CHART
# ──────────────────────────────────────────────────────────────────────

def plot_comparison(
    scenarios:  List[Tuple[str, SimulationConfig]],
    results:    List[SimulationResult],
    save_path:  Optional[str] = "figures/qkd_comparison.png",
    subtitle:   Optional[str] = None,
) -> None:
    """
    Single-panel QBER bar chart with 95 % Wilson CI error bars.

    Parameters
    ----------
    scenarios  : list of ``(name, config)`` pairs - names become x-axis labels.
    results    : SimulationResult objects in the same order as *scenarios*.
    save_path  : output PNG path (300 dpi); ``None`` → do not save.
    subtitle   : descriptive title (auto-wrapped); ``None`` → no title.

    Example
    -------
    >>> from bb84_runner import PRESET_SCENARIOS, run_comparison
    >>> from bb84_plots  import plot_comparison
    >>> results = run_comparison(PRESET_SCENARIOS)
    >>> plot_comparison(PRESET_SCENARIOS, results,
    ...                 subtitle="BB84 QKD - Scenario Comparison")
    """
    labels     = [s[0] for s in scenarios]
    qbers      = [r.qber_result.qber * 100            for r in results]
    ci_low     = [r.qber_result.confidence_low  * 100 for r in results]
    ci_high    = [r.qber_result.confidence_high * 100 for r in results]
    colors     = [_status_color(r)                    for r in results]
    yerr_low   = [max(0.0, q - lo) for q, lo in zip(qbers, ci_low)]
    yerr_high  = [max(0.0, hi - q) for q, hi in zip(qbers, ci_high)]

    n, x, bw = len(labels), np.arange(len(labels)), 0.52

    title_lines = _wrap(subtitle).count("\n") + 1 if subtitle else 0
    fig, ax = plt.subplots(figsize=(5.8, 3.4 + 0.08 * title_lines),
                           constrained_layout=False)
    fig.subplots_adjust(
        left=0.10, right=0.97,
        top=0.82 if title_lines >= 2 else 0.88,
        bottom=0.30,
    )

    if subtitle:
        ax.set_title(_wrap(subtitle, 72), fontsize=8, fontweight="bold",
                     pad=7, loc="center", linespacing=1.4)

    bars = ax.bar(x, qbers, width=bw, color=colors, alpha=0.88,
                  edgecolor="black", linewidth=0.6, zorder=3)

    ax.errorbar(x, qbers, yerr=[yerr_low, yerr_high],
                fmt="none", color="#111111",
                capsize=3.5, capthick=0.9, elinewidth=0.9, zorder=4)

    ax.axhline(11, color="#d62728", linestyle="--", linewidth=1.0,
               label="Abort threshold (11 %)", zorder=2)
    ax.axhline(5,  color="#ff7f0e", linestyle=":",  linewidth=1.0,
               label="Warning threshold (5 %)", zorder=2)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=28, ha="right", fontsize=7)
    ax.set_ylabel("QBER (%)", fontsize=8)
    y_top = max(max(q + hi for q, hi in zip(qbers, yerr_high)) + 6, 32)
    ax.set_ylim(0, y_top)
    ax.set_xlim(-0.6, n - 0.4)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f"))
    ax.yaxis.set_minor_locator(mticker.AutoMinorLocator(2))
    ax.tick_params(which="major", top=True, right=True, length=4, width=0.8)
    ax.tick_params(which="minor", top=True, right=True, length=2, width=0.5)
    ax.grid(axis="y", zorder=0, which="major")

    leg = ax.legend(fontsize=6.5, loc="upper left",
                    framealpha=0.90, edgecolor="#888888")
    leg.get_frame().set_linewidth(0.5)

    for idx, (bar, val) in enumerate(zip(bars, qbers)):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + yerr_high[idx] + 0.7,
                f"{val:.1f}", ha="center", va="bottom",
                fontsize=6.5, fontweight="bold", color="#111111")

    leg2 = fig.legend(handles=_LEGEND_PATCHES, loc="lower center", ncol=3,
                      fontsize=7, bbox_to_anchor=(0.535, 0.01),
                      framealpha=0.92, edgecolor="#888888")
    leg2.get_frame().set_linewidth(0.5)

    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
        print(f"  [✓] Saved → {save_path}  (300 dpi)")
    plt.show()


# ──────────────────────────────────────────────────────────────────────
# PLOT 2 - QBER vs EVE INTERCEPT RATE
# ──────────────────────────────────────────────────────────────────────

def plot_qber_vs_intercept_rate(
    n_qubits:        int           = 600,
    steps:           int           = 10,
    sample_fraction: float         = 0.15,
    save_path:       Optional[str] = "figures/qkd_qber_vs_eve.png",
    subtitle:        Optional[str] = None,
) -> None:
    """
    Sweep Eve's intercept probability from 0 % → 100 % and plot simulated
    versus theoretical QBER (theory: QBER = 0.25 × p_intercept).

    Parameters
    ----------
    n_qubits        : qubits per simulation run.
    steps           : number of probability steps (default 10 → 0, 10, …, 100 %).
    sample_fraction : QBER estimation sample fraction.
    save_path       : output PNG path; ``None`` → do not save.
    subtitle        : descriptive plot title; ``None`` → no title.

    Example
    -------
    >>> from bb84_plots import plot_qber_vs_intercept_rate
    >>> plot_qber_vs_intercept_rate(subtitle="QBER vs Eve Intercept Rate")
    """
    print("\n  [Sweep] QBER vs Eve intercept probability...")

    probs:  List[float] = []
    qbers:  List[float] = []
    ci_low: List[float] = []
    ci_hi:  List[float] = []

    for p in np.linspace(0, 1, steps + 1):
        cfg = SimulationConfig(
            n_qubits=n_qubits,
            eve_present=(p > 0),
            eve_intercept_prob=float(p),
            sample_fraction=sample_fraction,
            noise_enabled=False,
            seed=42,
        )
        r = run_simulation(cfg, verbose=False)
        q = r.qber_result.qber * 100
        probs.append(float(p))
        qbers.append(q)
        ci_low.append(max(0.0, r.qber_result.confidence_low  * 100))
        ci_hi.append(r.qber_result.confidence_high * 100)
        print(f"    p = {p:.2f}  →  QBER = {q:.1f} %")

    probs_pct   = [p * 100 for p in probs]
    theoretical = [0.25 * p * 100 for p in probs]

    title_lines = _wrap(subtitle, 60).count("\n") + 1 if subtitle else 0
    fig, ax = plt.subplots(figsize=(3.8, 2.9 + 0.08 * title_lines),
                           constrained_layout=False)
    fig.subplots_adjust(
        left=0.13, right=0.97,
        top=0.82 if title_lines >= 2 else 0.88,
        bottom=0.14,
    )

    if subtitle:
        ax.set_title(_wrap(subtitle, 60), fontsize=8, fontweight="bold",
                     pad=7, loc="center", linespacing=1.4)

    ax.plot(probs_pct, qbers, "b-o", linewidth=1.2, markersize=4,
            label="Simulated QBER")
    ax.fill_between(probs_pct, ci_low, ci_hi,
                    alpha=0.18, color="steelblue",
                    label="95 % Confidence Interval")
    ax.plot(probs_pct, theoretical, "r--", linewidth=1.0,
            label=r"Theory: QBER = 0.25$p$")
    ax.axhline(11, color="#d62728", linestyle=":", linewidth=0.9,
               label="Abort threshold (11 %)")
    ax.axhline(5,  color="#ff7f0e", linestyle=":", linewidth=0.9,
               label="Warning threshold (5 %)")

    ax.set_xlabel("Eve's Intercept Probability (%)", fontsize=8)
    ax.set_ylabel("QBER (%)", fontsize=8)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, max(30, max(ci_hi) + 4))
    ax.yaxis.set_minor_locator(mticker.AutoMinorLocator(2))
    ax.tick_params(which="major", top=True, right=True, length=4,
                   width=0.8, direction="in")
    ax.tick_params(which="minor", top=True, right=True, length=2,
                   width=0.5, direction="in")
    ax.grid(alpha=0.35)

    leg = ax.legend(fontsize=6, loc="upper left",
                    framealpha=0.88, edgecolor="#888888")
    leg.get_frame().set_linewidth(0.5)

    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
        print(f"  [✓] Saved → {save_path}  (300 dpi)")
    plt.show()
