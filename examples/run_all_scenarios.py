#!/usr/bin/env python3
"""
examples/run_all_scenarios.py
==============================
Run all five canonical BB84 preset scenarios and produce two plots.

Usage
-----
    python examples/run_all_scenarios.py

Output
------
  • Console comparison table
  • figures/qkd_comparison.png   - QBER bar chart
  • figures/qkd_qber_vs_eve.png  - QBER vs Eve sweep

University of Ruhuna - Dept. of Computer Engineering
MIT Licence - see LICENSE
"""

import os
import sys

# Make sure the repo root is on the path when run from any directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.makedirs("figures", exist_ok=True)

from bb84_runner import run_comparison, PRESET_SCENARIOS
from bb84_plots  import plot_comparison, plot_qber_vs_intercept_rate


def main() -> None:
    # ── 1. Run all preset scenarios and print comparison table ────────
    print("\n" + "=" * 60)
    print("  BB84 QKD Simulator - Preset Scenarios")
    print("  University of Ruhuna - Dept. of Computer Engineering")
    print("=" * 60)

    results = run_comparison(PRESET_SCENARIOS)

    # ── 2. QBER comparison bar chart ─────────────────────────────────
    plot_comparison(
        PRESET_SCENARIOS,
        results,
        save_path="figures/qkd_comparison.png",
        subtitle=(
            "BB84 QKD - QBER Comparison: Ideal, Eavesdropping, "
            "and Depolarising Noise (n = 600 qubits, seed = 42)"
        ),
    )

    # ── 3. QBER vs Eve intercept-rate sweep ───────────────────────────
    plot_qber_vs_intercept_rate(
        n_qubits=600,
        steps=10,
        sample_fraction=0.15,
        save_path="figures/qkd_qber_vs_eve.png",
        subtitle=(
            "BB84 QKD - Simulated vs Theoretical QBER "
            "as a Function of Eve's Intercept Probability"
        ),
    )

    print("\n  All done. Figures saved to figures/")


if __name__ == "__main__":
    main()
