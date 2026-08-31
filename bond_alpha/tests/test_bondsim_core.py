import numpy as np
import pandas as pd

from bondsim.config import load_config
from bondsim.hawkes.graph import build_hawkes_graph
from bondsim.liquidity import target_rates_from_ranks
from bondsim.prices.ou import ou_step
from bondsim.scenarios import flags_for
from bondsim.schema import PUBLIC_TRADE_COLUMNS, TRUTH_COLUMNS
from bondsim.universe import build_universe
from bondsim.validation.report import validate_outputs


def test_liquidity_mapping_hits_target_quantiles() -> None:
    config = load_config("configs/base.yaml")
    bonds = pd.DataFrame({"liquidity_rank_global": np.linspace(0.001, 0.999, 500)})
    rates = target_rates_from_ranks(bonds, config.liquidity)
    assert rates.quantile(0.50) == pytest_approx(2.0, 0.08)
    assert rates.quantile(0.10) == pytest_approx(0.4, 0.08)


def test_hawkes_graph_is_stable() -> None:
    config = load_config("configs/base.yaml")
    real_bonds = pd.DataFrame(
        {
            "source_bond_id": [f"B{i}" for i in range(10)],
            "source_issuer_id": [f"I{i//5}" for i in range(10)],
            "liquidity_rank_global": np.linspace(0.1, 0.9, 10),
            "median_notional": 250000.0,
            "notional_p90": 1000000.0,
            "liquidity_bucket": "medium",
            "rating_bucket": "unknown",
            "maturity_bucket": "unknown",
        }
    )
    universe = build_universe(real_bonds, config, np.random.default_rng(1), "smoke")
    graph = build_hawkes_graph(universe, config, flags_for("controlled_all"))
    assert graph.spectral_radius < config.hawkes.maximum_spectral_radius


def test_ou_step_is_deterministic_for_seed() -> None:
    a = ou_step(1.0, 0.5, 2.0, 0.1, np.random.default_rng(123))
    b = ou_step(1.0, 0.5, 2.0, 0.1, np.random.default_rng(123))
    assert a == b


def test_public_truth_separation_validation() -> None:
    config = load_config("configs/base.yaml")
    trades = pd.DataFrame(
        [{col: "x" for col in PUBLIC_TRADE_COLUMNS}]
    )
    trades["side"] = 1
    trades["notional"] = 1.0
    trades["price"] = 100.0
    trades["is_interdealer"] = False
    trades["reporting_delay_ms"] = 0.0
    truth = pd.DataFrame([{col: "x" for col in TRUTH_COLUMNS}])
    bonds = pd.DataFrame({"synthetic_bond_id": [f"SB{i}" for i in range(config.simulation.smoke_bonds)]})
    result = validate_outputs(trades, truth, bonds, config, "controlled_all", "smoke")
    assert result["passed"]


def pytest_approx(expected: float, rel: float) -> object:
    import pytest

    return pytest.approx(expected, rel=rel)
