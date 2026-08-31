from bb84_config import SimulationConfig
from bb84_zne import run_zne_analysis


def test_zne_analysis_runs_for_supported_noise_model():
    cfg = SimulationConfig(
        n_qubits=80,
        seed=7,
        noise_model="depolarizing",
        depolar_prob=0.05,
        label="ZNE test",
    )

    result = run_zne_analysis(cfg, f_scales=[1.0, 1.5], n_seeds=1, method="linear")

    assert result is not None
    assert result.f_scales == [1.0, 1.5]
    assert result.linear_intercept >= 0.0
    assert result.qber_at_f1 >= 0.0
